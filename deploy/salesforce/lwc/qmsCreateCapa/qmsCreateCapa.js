import { LightningElement, api, wire, track } from 'lwc';
import { ShowToastEvent } from 'lightning/platformShowToastEvent';
import runAgentPipeline from '@salesforce/apex/QmsGenAiClient.runAgentPipeline';
import getApiHost from '@salesforce/apex/QmsGenAiClient.getApiHost';

export default class QmsCreateCapa extends LightningElement {
  @api recordId;

  @track loading = false;
  @track result;
  @track error;
  @track apiHost = '';

  @wire(getApiHost)
  wiredHost({ data }) {
    if (data) {
      this.apiHost = data.replace(/\/$/, '');
    }
  }

  get hasResult() {
    return Boolean(this.result);
  }

  get data() {
    return this.result && this.result.data ? this.result.data : {};
  }

  get draft() {
    return this.data.capa && this.data.capa.draft ? this.data.capa.draft : {};
  }

  get record() {
    return this.data.record || {};
  }

  get ui() {
    return this.data.ui || {};
  }

  get connectionLabel() {
    return this.hasResult ? 'Connected' : 'Ready';
  }

  get connectionClass() {
    return this.hasResult ? 'badge badge-ok' : 'badge';
  }

  get modelLabel() {
    const provider = this.draft._provider;
    const model = this.draft._model;
    return provider ? `LLM: ${provider} / ${model || 'model'}` : 'QMS GenAI pipeline';
  }

  get recordTitle() {
    return this.record.title || 'Salesforce Case';
  }

  get recordMeta() {
    const parts = [this.record.id, this.record.type, this.record.sector, this.record.priority]
      .filter(Boolean);
    return parts.join(' | ');
  }

  get capaId() {
    return this.data.capa && this.data.capa.id ? this.data.capa.id : '';
  }

  get reviewState() {
    return this.data.capa && this.data.capa.reviewState ? this.data.capa.reviewState : 'Under Review';
  }

  get rootCause() {
    return this.draft.rootCause || '';
  }

  get immediateAction() {
    return this.draft.immediateAction || '';
  }

  get correctiveAction() {
    return this.draft.correctiveAction || '';
  }

  get preventiveAction() {
    return this.draft.preventiveAction || '';
  }

  get effectivenessCheck() {
    return this.draft.effectivenessCheck || '';
  }

  get riskRating() {
    return this.draft.riskRating || '';
  }

  get owner() {
    return this.draft.proposedOwner || this.draft.capaOwner || '';
  }

  get closureDays() {
    return this.draft.estimatedClosureDays ? `${this.draft.estimatedClosureDays} days` : '';
  }

  get rcaQualityScore() {
    return this.draft.rcaQualityScore === undefined ? 'Not scored' : `${this.draft.rcaQualityScore}%`;
  }

  get openInQmsUrl() {
    if (this.ui.openDraftUrl) {
      return this.apiHost + this.ui.openDraftUrl;
    }
    if (this.record.id) {
      return `${this.apiHost}/capa/create?id=${encodeURIComponent(this.record.id)}`;
    }
    return '';
  }

  get hasQmsUrl() {
    return Boolean(this.openInQmsUrl);
  }

  handleGenerate() {
    this.loading = true;
    this.result = undefined;
    this.error = undefined;

    runAgentPipeline({ caseId: this.recordId, saveDraft: true })
      .then((response) => {
        this.result = response;
        this.loading = false;
        this.dispatchEvent(
          new ShowToastEvent({
            title: 'CAPA draft created',
            message: this.capaId ? `${this.capaId} is ready for QMS review.` : 'QMS draft is ready for review.',
            variant: 'success'
          })
        );
      })
      .catch((err) => {
        this.loading = false;
        this.error = err && err.body && err.body.message ? err.body.message : String(err);
        this.dispatchEvent(
          new ShowToastEvent({
            title: 'CAPA generation failed',
            message: this.error,
            variant: 'error'
          })
        );
      });
  }

  openInQms() {
    window.open(this.openInQmsUrl, '_blank', 'noopener');
  }
}
