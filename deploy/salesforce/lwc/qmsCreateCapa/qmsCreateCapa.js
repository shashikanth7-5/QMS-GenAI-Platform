import { LightningElement, api, track } from 'lwc';
import { ShowToastEvent } from 'lightning/platformShowToastEvent';
import getCaseContext from '@salesforce/apex/QmsGenAiClient.getCaseContext';
import generateCapaFromRca from '@salesforce/apex/QmsGenAiClient.generateCapaFromRca';
import runRca from '@salesforce/apex/QmsGenAiClient.runRca';
import reassessRca from '@salesforce/apex/QmsGenAiClient.reassessRca';
import proposeRcaModels from '@salesforce/apex/QmsGenAiClient.proposeRcaModels';
import runAgentPipeline from '@salesforce/apex/QmsGenAiClient.runAgentPipeline';
import saveCapaDraft from '@salesforce/apex/QmsGenAiClient.saveCapaDraft';
import listRelatedCapas from '@salesforce/apex/QmsGenAiClient.listRelatedCapas';

export default class QmsCreateCapa extends LightningElement {
  @api recordId;

  @track loading = false;
  @track loadingMessage = '';
  @track error;
  @track record = {};
  @track draft = {};
  @track rca = {};
  @track rcaModels = [];
  @track relatedCapas = [];
  @track apiHost = '';
  @track selectedMethod = 'fishbone';
  @track lastSave;
  @track approvalRequested = false;

  connectedCallback() {
    this.loadContext();
  }

  get isBusy() {
    return this.loading;
  }

  get hasModels() {
    return this.rcaModels.length > 0;
  }

  get hasRelatedCapas() {
    return this.relatedCapas.length > 0;
  }

  get modelLabel() {
    const provider = this.draft._provider || this.rca._provider;
    const model = this.draft._model || this.rca._model;
    return provider ? `${provider} / ${model || 'model'}` : 'Ready for live QMS LLM';
  }

  get recordMeta() {
    return [this.record.caseNumber || this.record.id, this.record.type, this.record.sector, this.record.priority]
      .filter(Boolean)
      .join(' | ');
  }

  get capaStatus() {
    return this.lastSave && this.lastSave.qmsCapaId ? 'Under Review' : this.draft.rootCause ? 'Draft prepared' : 'Not triggered';
  }

  get rootCauseText() {
    if (this.draft.rootCause) {
      return this.draft.rootCause;
    }
    if (this.rca.rootCause) {
      return this.rca.rootCause;
    }
    if (this.rca.chain && this.rca.chain.length) {
      const last = this.rca.chain[this.rca.chain.length - 1];
      return last.answer || last.why || '';
    }
    return '';
  }

  get rcaScore() {
    if (this.draft.rcaQualityScore !== undefined && this.draft.rcaQualityScore !== null) {
      return `${this.draft.rcaQualityScore}%`;
    }
    if (this.rca.overall_score !== undefined && this.rca.overall_score !== null) {
      return `${this.rca.overall_score}%`;
    }
    return 'Not scored';
  }

  get methodOptions() {
    return [
      { label: 'Fishbone', value: 'fishbone' },
      { label: '5-Why', value: '5why' }
    ];
  }

  get closureDays() {
    return this.draft.estimatedClosureDays || '';
  }

  get qmsOpenUrl() {
    const capaId = this.lastSave && this.lastSave.qmsCapaId ? `&capaId=${encodeURIComponent(this.lastSave.qmsCapaId)}` : '';
    return this.apiHost && this.record.id ? `${this.apiHost}/capa/create?id=${encodeURIComponent(this.record.id)}${capaId}` : '';
  }

  get timeSavedLabel() {
    return this.draft.rootCause ? '11h 52m saved per event' : 'Awaiting AI processing';
  }

  get attachmentLabel() {
    const count = this.record.attachmentCount || 0;
    return `${count}/15 files available for RCA context`;
  }

  loadContext() {
    this.setBusy('Loading QMS context...');
    getCaseContext({ caseId: this.recordId })
      .then((res) => {
        this.record = res.record || {};
        this.relatedCapas = res.relatedCapas || [];
        this.apiHost = (res.apiHost || '').replace(/\/$/, '');
        this.clearBusy();
      })
      .catch((err) => this.handleError('Unable to load QMS context', err));
  }

  handleMethodChange(event) {
    this.selectedMethod = event.detail.value;
  }

  handleDraftChange(event) {
    const field = event.target.dataset.field;
    this.draft = { ...this.draft, [field]: event.target.value };
  }

  buildRcaPayload() {
    return {
      ...this.rca,
      rootCause: this.rootCauseText,
      method: this.selectedMethod,
      _provider: this.draft._provider || this.rca._provider,
      _model: this.draft._model || this.rca._model
    };
  }

  handleRunRca() {
    this.setBusy('Running RCA against QMS LLM...');
    runRca({ caseId: this.recordId, method: this.selectedMethod })
      .then((res) => {
        const data = res.data || res;
        this.rca = data.rca || {};
        this.draft = { ...this.draft, rootCause: this.rootCauseText };
        this.toast('RCA completed', this.modelLabel, 'success');
        this.clearBusy();
      })
      .catch((err) => this.handleError('RCA failed', err));
  }

  handleLoadModels() {
    this.setBusy('Loading RCA model options...');
    proposeRcaModels({ caseId: this.recordId, method: this.selectedMethod })
      .then((res) => {
        const data = res.data || res;
        this.rcaModels = (data.models || []).map((model, index) => ({
          ...model,
          index,
          label: model.name || `Model ${index + 1}`,
          summary: model.rootCause || model.description || 'LLM-generated RCA option',
          meta: `${model._provider || data.provider || 'LLM'} / ${model._model || data.model || 'model'}`
        }));
        this.toast('RCA models loaded', `${this.rcaModels.length} model options available.`, 'success');
        this.clearBusy();
      })
      .catch((err) => this.handleError('Error loading models', err));
  }

  handleReassessRca() {
    this.setBusy('Reassessing RCA score...');
    reassessRca({
      caseId: this.recordId,
      method: this.selectedMethod,
      rcaJson: JSON.stringify(this.buildRcaPayload())
    })
      .then((res) => {
        const data = res.data || res;
        this.rca = { ...this.rca, ...data };
        this.draft = { ...this.draft, rcaQualityScore: data.overall_score };
        this.toast('RCA reassessed', data.verdict_msg || this.rcaScore, 'success');
        this.clearBusy();
      })
      .catch((err) => this.handleError('RCA reassessment failed', err));
  }

  handleSelectModel(event) {
    const index = Number(event.currentTarget.dataset.index);
    const selected = this.rcaModels[index];
    if (!selected) {
      return;
    }
    this.rca = selected;
    this.draft = {
      ...this.draft,
      rootCause: selected.rootCause || selected.summary || '',
      _provider: selected._provider,
      _model: selected._model
    };
    this.toast('RCA model applied', selected.label, 'success');
  }

  handleGenerateDraft() {
    this.setBusy('Generating CAPA draft...');
    generateCapaFromRca({ caseId: this.recordId, rcaJson: JSON.stringify(this.buildRcaPayload()) })
      .then((res) => {
        const data = res.data || res;
        const capa = data.capa || {};
        this.draft = {
          ...capa,
          rootCause: capa.rootCause || this.rootCauseText,
          capaOwner: capa.capaOwner || capa.proposedOwner || 'Quality Assurance Manager'
        };
        this.toast('CAPA draft generated', this.modelLabel, 'success');
        this.clearBusy();
      })
      .catch((err) => this.handleError('CAPA generation failed', err));
  }

  handleRunAgents() {
    this.setBusy('Running QMS agent workflow...');
    runAgentPipeline({ caseId: this.recordId, saveDraft: false })
      .then((res) => {
        const data = res.data || res;
        const capa = data.capa || {};
        const draft = capa.draft || {};
        this.draft = { ...this.draft, ...draft };
        this.toast('Agent workflow completed', data.integrationStatus || 'completed', 'success');
        this.clearBusy();
      })
      .catch((err) => this.handleError('Agent workflow failed', err));
  }

  handleSaveDraft() {
    this.setBusy('Saving CAPA to QMS and Salesforce...');
    saveCapaDraft({ caseId: this.recordId, draftJson: JSON.stringify(this.draft) })
      .then((res) => {
        this.lastSave = res;
        this.relatedCapas = res.relatedCapas || [];
        this.approvalRequested = window.confirm('CAPA draft saved under this Salesforce Case. Do you want to open the QMS approval/review page now?');
        if (this.approvalRequested) {
          this.openInQms();
        }
        this.toast('CAPA saved', `${res.qmsCapaId || 'Draft'} is linked to this Case.`, 'success');
        this.clearBusy();
      })
      .catch((err) => this.handleError('CAPA save failed', err));
  }

  handleRefreshRelated() {
    listRelatedCapas({ caseId: this.recordId })
      .then((rows) => {
        this.relatedCapas = rows || [];
      })
      .catch((err) => this.handleError('Related CAPA refresh failed', err));
  }

  handleUploadFinished(event) {
    const count = event.detail.files.length;
    this.toast('Attachment added', `${count} Salesforce file(s) attached to the Case. Refresh context before RCA.`, 'success');
    this.loadContext();
  }

  openInQms() {
    if (this.qmsOpenUrl) {
      window.open(this.qmsOpenUrl, '_blank', 'noopener');
    }
  }

  openSalesforceCapa(event) {
    const id = event.currentTarget.dataset.id;
    if (id) {
      window.open(`/${id}`, '_blank', 'noopener');
    }
  }

  setBusy(message) {
    this.loading = true;
    this.loadingMessage = message;
    this.error = undefined;
  }

  clearBusy() {
    this.loading = false;
    this.loadingMessage = '';
  }

  handleError(title, err) {
    this.loading = false;
    this.error = err && err.body && err.body.message ? err.body.message : String(err);
    this.toast(title, this.error, 'error');
  }

  toast(title, message, variant) {
    this.dispatchEvent(new ShowToastEvent({ title, message, variant }));
  }
}
