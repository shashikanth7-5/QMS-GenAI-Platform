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
  @track showModelModal = false;

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

  get hasRca() {
    return Boolean(this.rootCauseText);
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

  get yesNoOptions() {
    return [
      { label: 'No', value: 'No' },
      { label: 'Yes', value: 'Yes' }
    ];
  }

  get impactOptions() {
    return [
      { label: 'Product impact', value: 'Product impact' },
      { label: 'Process impact', value: 'Process impact' },
      { label: 'System impact', value: 'System impact' },
      { label: 'Patient / user impact', value: 'Patient / user impact' },
      { label: 'Regulatory impact', value: 'Regulatory impact' }
    ];
  }

  get riskOptions() {
    return [
      { label: 'Low', value: 'Low' },
      { label: 'Medium', value: 'Medium' },
      { label: 'High', value: 'High' },
      { label: 'Critical', value: 'Critical' }
    ];
  }

  loadContext() {
    this.setBusy('Loading QMS context...');
    getCaseContext({ caseId: this.recordId })
      .then((res) => {
        this.record = res.record || {};
        this.relatedCapas = res.relatedCapas || [];
        this.apiHost = (res.apiHost || '').replace(/\/$/, '');
        this.draft = this.buildDefaultDraft();
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

  buildDefaultDraft() {
    return {
      sourceRecordId: this.record.id || this.record.caseNumber || '',
      sourceRecordType: this.record.type || 'complaint',
      sourcePriority: this.record.priority || 'Medium',
      sourceSite: this.record.site || '',
      sourceTitle: this.record.title || '',
      sector: this.record.sector || '',
      impactScope: 'Product impact',
      riskRating: this.record.priority === 'High' ? 'High' : this.record.priority === 'Low' ? 'Low' : 'Medium',
      repeatEvent: 'No',
      supplierRelated: 'No',
      authorityNotificationRequired: 'No',
      effectivenessCheckRequired: 'Yes',
      affectedFunctions: 'QA, manufacturing, supplier contact, patient/user if applicable',
      impactAssessmentDetail: 'CAPA eligibility will be confirmed by QMS agents using this Salesforce Case and attached evidence.',
      regulatoryRef: '21 CFR 820.100; ISO 13485:2016',
      supportingDocuments: this.attachmentLabel,
      additionalNotes: ''
    };
  }

  mergeGeneratedDraft(capa) {
    return {
      ...this.draft,
      ...capa,
      sourceRecordId: capa.sourceRecordId || this.draft.sourceRecordId || this.record.id || this.record.caseNumber,
      sourceRecordType: capa.sourceRecordType || this.draft.sourceRecordType || this.record.type || 'complaint',
      sourcePriority: capa.sourcePriority || this.draft.sourcePriority || this.record.priority || 'Medium',
      sourceSite: capa.sourceSite || capa.site || this.draft.sourceSite || this.record.site || '',
      sourceTitle: capa.sourceTitle || capa.title || this.draft.sourceTitle || this.record.title || '',
      sector: capa.sector || this.draft.sector || this.record.sector || '',
      rootCause: capa.rootCause || this.rootCauseText,
      capaOwner: capa.capaOwner || capa.proposedOwner || this.draft.capaOwner || 'Quality Assurance Manager',
      riskRating: capa.riskRating || this.draft.riskRating || 'Medium',
      impactScope: capa.impactScope || this.draft.impactScope || 'Product impact',
      repeatEvent: capa.repeatEvent || this.draft.repeatEvent || 'No',
      supplierRelated: capa.supplierRelated || this.draft.supplierRelated || 'No',
      authorityNotificationRequired: capa.authorityNotificationRequired || this.draft.authorityNotificationRequired || 'No',
      effectivenessCheckRequired: capa.effectivenessCheckRequired || this.draft.effectivenessCheckRequired || 'Yes',
      affectedFunctions:
        capa.affectedFunctions ||
        this.draft.affectedFunctions ||
        'QA, manufacturing, supplier contact, patient/user if applicable',
      impactAssessmentDetail:
        capa.impactAssessmentDetail ||
        this.draft.impactAssessmentDetail ||
        'CAPA eligible: risk/impact conditions support draft creation and quality review.',
      regulatoryRef: capa.regulatoryRef || this.draft.regulatoryRef || '21 CFR 820.100; ISO 13485:2016',
      supportingDocuments: capa.supportingDocuments || this.draft.supportingDocuments || this.attachmentLabel,
      additionalNotes: capa.additionalNotes || this.draft.additionalNotes || ''
    };
  }

  requiredDraftMissingFields() {
    const checks = [
      ['impactScope', 'Impact Scope'],
      ['riskRating', 'Risk Level'],
      ['impactAssessmentDetail', 'Impact Assessment Detail'],
      ['rootCause', 'Root Cause Statement'],
      ['immediateAction', 'Immediate / Containment Action'],
      ['correctiveAction', 'Corrective Action'],
      ['preventiveAction', 'Preventive Action'],
      ['capaOwner', 'CAPA Owner'],
      ['effectivenessCheck', 'Effectiveness Check'],
      ['regulatoryRef', 'Regulatory References']
    ];
    return checks
      .filter(([field]) => !String(this.draft[field] || '').trim())
      .map(([, label]) => label);
  }

  validateDraftForSave() {
    const missing = this.requiredDraftMissingFields();
    if (!missing.length) {
      return true;
    }
    const message = `Complete these required CAPA fields before saving:\n\n${missing.join('\n')}`;
    this.error = message;
    window.alert(message);
    this.toast('CAPA draft incomplete', `${missing.length} required field(s) need review.`, 'warning');
    return false;
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
        return this.scoreAndSuggestModels();
      })
      .then(() => this.clearBusy())
      .catch((err) => this.handleError('RCA failed', err));
  }

  handleLoadModels() {
    this.setBusy('Loading RCA model options...');
    this.loadModels()
      .then((res) => {
        this.showModelModal = true;
        this.toast('RCA models loaded', `${this.rcaModels.length} model options available.`, 'success');
        this.clearBusy();
      })
      .catch((err) => this.handleError('Error loading models', err));
  }

  handleReassessRca() {
    this.setBusy('Reassessing RCA score...');
    this.scoreAndSuggestModels()
      .then(() => this.clearBusy())
      .catch((err) => this.handleError('RCA reassessment failed', err));
  }

  scoreAndSuggestModels() {
    return reassessRca({
      caseId: this.recordId,
      method: this.selectedMethod,
      rcaJson: JSON.stringify(this.buildRcaPayload())
    })
      .then((res) => {
        const data = res.data || res;
        this.rca = { ...this.rca, ...data };
        this.draft = { ...this.draft, rcaQualityScore: data.overall_score };
        return this.loadModels();
      })
      .then(() => {
        this.showModelModal = this.rcaModels.length > 0;
        this.toast('RCA scored', `${this.rcaScore}. Select an AI model if you want to improve the RCA.`, 'success');
      });
  }

  loadModels() {
    return proposeRcaModels({ caseId: this.recordId, method: this.selectedMethod })
      .then((res) => {
        const data = res.data || res;
        this.rcaModels = (data.models || []).map((model, index) => ({
          ...model,
          index,
          label: model.name || `Model ${index + 1}`,
          summary: model.rootCause || model.description || 'LLM-generated RCA option',
          meta: `${model._provider || data.provider || 'LLM'} / ${model._model || data.model || 'model'}`
        }));
        return data;
      });
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
    this.showModelModal = false;
    this.toast('RCA model applied', selected.label, 'success');
  }

  closeModelModal() {
    this.showModelModal = false;
  }

  handleGenerateDraft() {
    if (!this.rootCauseText) {
      const message = 'Run RCA Analysis first so the CAPA draft is based on this Salesforce Case and its attachments.';
      this.error = message;
      window.alert(message);
      this.toast('RCA required', message, 'warning');
      return;
    }
    this.setBusy('Generating CAPA draft...');
    generateCapaFromRca({ caseId: this.recordId, rcaJson: JSON.stringify(this.buildRcaPayload()) })
      .then((res) => {
        const data = res.data || res;
        const capa = data.capa || {};
        this.draft = this.mergeGeneratedDraft(capa);
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
        if (data.integrationStatus === 'skipped') {
          const reason =
            data.reason ||
            (data.ui && data.ui.showMessage) ||
            'This record is not eligible for CAPA creation based on the QMS decision rules.';
          const message = `Not eligible to create CAPA:\n\n${reason}`;
          this.error = message;
          window.alert(message);
          this.toast('CAPA not eligible', reason, 'warning');
          this.clearBusy();
          return;
        }
        const capa = data.capa || {};
        const draft = capa.draft || {};
        const steps = data.agentRun && data.agentRun.steps ? data.agentRun.steps : [];
        this.draft = this.mergeGeneratedDraft({
          ...draft,
          agentSummary: steps.map((step) => `${step.agent}: ${step.event} -> ${step.status}`).join('\n')
        });
        this.toast('Agent workflow completed', data.integrationStatus || 'completed', 'success');
        this.clearBusy();
      })
      .catch((err) => this.handleError('Agent workflow failed', err));
  }

  handleSaveDraft() {
    if (!this.validateDraftForSave()) {
      return;
    }
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
