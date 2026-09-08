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
  wiredHost({ data, error }) {
    if (data) {
      this.apiHost = data;
    } else if (error) {
      // Non-fatal - link will fall back to empty host.
      this.apiHost = '';
    }
  }

  get hasResult() {
    return this.result !== undefined && this.result !== null;
  }

  get rootCause() {
    return this.extract('rootCause');
  }

  get correctiveAction() {
    return this.extract('correctiveAction');
  }

  get preventiveAction() {
    return this.extract('preventiveAction');
  }

  get riskRating() {
    return this.extract('riskRating');
  }

  get openInQmsUrl() {
    const path = this.result && this.result.data && this.result.data.ui
      ? this.result.data.ui.openDraftUrl
      : '';
    if (path) {
      return this.apiHost + path;
    }
    const recordId = this.result && this.result.data && this.result.data.record
      ? this.result.data.record.id
      : this.result && this.result.recordId;
    if (!recordId) {
      return '#';
    }
    return this.apiHost + '/capa/create?id=' + encodeURIComponent(recordId);
  }

  extract(key) {
    if (!this.result) return '';
    if (this.result[key]) return this.result[key];
    if (this.result.capa && this.result.capa[key]) return this.result.capa[key];
    if (this.result.data && this.result.data.capa && this.result.data.capa.draft) {
      return this.result.data.capa.draft[key] || '';
    }
    return '';
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
            title: 'CAPA generated',
            message: 'Draft CAPA created successfully.',
            variant: 'success'
          })
        );
      })
      .catch((err) => {
        this.loading = false;
        this.error = (err && err.body && err.body.message) ? err.body.message : String(err);
        this.dispatchEvent(
          new ShowToastEvent({
            title: 'CAPA generation failed',
            message: this.error,
            variant: 'error'
          })
        );
      });
  }
}
