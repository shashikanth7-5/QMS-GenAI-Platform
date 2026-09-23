/**
 * QmsGenAiClient - Apex client for the QMS GenAI REST API.
 */
public with sharing class QmsGenAiClient {

  private static final String NAMED_CRED = 'callout:QMS_GenAI';
  private static final Integer MAX_RCA_FILES = 15;
  private static final Integer MAX_FILE_SNIPPET_CHARS = 2500;

  @AuraEnabled(cacheable=false)
  public static Map<String, Object> getCaseContext(Id caseId) {
    SObject sourceRec = loadSourceRecord(caseId);
    return new Map<String, Object>{
      'record' => sourceRecordToQmsRecord(sourceRec, true),
      'relatedCapas' => listRelatedCapas(caseId),
      'apiHost' => getApiHost()
    };
  }

  @AuraEnabled(cacheable=false)
  public static Map<String, Object> generateCapa(Id caseId) {
    SObject sourceRec = loadSourceRecord(caseId);
    HttpRequest req = baseRequest('/api/v1/capa/generate', 'POST', 'sf-capa-generate-' + sourceRec.Id);
    req.setBody(JSON.serialize(new Map<String, Object>{ 'record' => sourceRecordToQmsRecord(sourceRec, true) }));
    return sendJson(req, 'QMS /api/v1/capa/generate failed');
  }

  @AuraEnabled(cacheable=false)
  public static Map<String, Object> generateCapaFromRca(Id caseId, String rcaJson) {
    SObject sourceRec = loadSourceRecord(caseId);
    Map<String, Object> record = sourceRecordToQmsRecord(sourceRec, true);
    Map<String, Object> rca = parseMap(rcaJson);
    record.put('rca', rca);
    record.put('rootCause', value(rca, 'rootCause'));

    HttpRequest req = baseRequest('/api/v1/capa/generate', 'POST', 'sf-capa-generate-rca-' + sourceRec.Id + '-' + DateTime.now().getTime());
    req.setBody(JSON.serialize(new Map<String, Object>{ 'record' => record }));
    return sendJson(req, 'QMS /api/v1/capa/generate failed');
  }

  @AuraEnabled(cacheable=false)
  public static Map<String, Object> runRca(Id caseId, String method) {
    SObject sourceRec = loadSourceRecord(caseId);
    String selectedMethod = String.isBlank(method) ? 'fishbone' : method;
    HttpRequest req = baseRequest('/api/v1/rca/analyze', 'POST', 'sf-rca-' + selectedMethod + '-' + sourceRec.Id + '-' + DateTime.now().getTime());
    req.setBody(JSON.serialize(new Map<String, Object>{
      'record' => sourceRecordToQmsRecord(sourceRec, true),
      'method' => selectedMethod
    }));
    return sendJson(req, 'QMS /api/v1/rca/analyze failed');
  }

  @AuraEnabled(cacheable=false)
  public static Map<String, Object> reassessRca(Id caseId, String method, String rcaJson) {
    String selectedMethod = String.isBlank(method) ? 'fishbone' : method;
    HttpRequest req = baseRequest('/api/v1/rca/assess', 'POST', 'sf-rca-assess-' + caseId + '-' + DateTime.now().getTime());
    req.setBody(JSON.serialize(new Map<String, Object>{
      'method' => selectedMethod,
      'rca_data' => parseMap(rcaJson)
    }));
    return sendJson(req, 'QMS /api/v1/rca/assess failed');
  }

  @AuraEnabled(cacheable=false)
  public static Map<String, Object> proposeRcaModels(Id caseId, String method) {
    SObject sourceRec = loadSourceRecord(caseId);
    String selectedMethod = String.isBlank(method) ? 'fishbone' : method;
    HttpRequest req = baseRequest('/api/v1/rca/propose', 'POST', 'sf-rca-models-' + selectedMethod + '-' + sourceRec.Id + '-' + DateTime.now().getTime());
    req.setBody(JSON.serialize(new Map<String, Object>{
      'record' => sourceRecordToQmsRecord(sourceRec, true),
      'method' => selectedMethod
    }));
    return sendJson(req, 'QMS /api/v1/rca/propose failed');
  }

  @AuraEnabled(cacheable=false)
  public static Map<String, Object> runAgentPipeline(Id caseId, Boolean saveDraft) {
    SObject sourceRec = loadSourceRecord(caseId);
    HttpRequest req = baseRequest('/api/v1/integrations/quality-event/capa', 'POST', 'sf-agent-' + sourceRec.Id);
    req.setTimeout(120000);
    req.setBody(JSON.serialize(new Map<String, Object>{
      'record' => sourceRecordToQmsRecord(sourceRec, true),
      'options' => new Map<String, Object>{'saveDraft' => saveDraft}
    }));
    return sendJson(req, 'QMS /api/v1/integrations failed');
  }

  @AuraEnabled(cacheable=false)
  public static Map<String, Object> saveCapaDraft(Id caseId, String draftJson) {
    SObject sourceRec = loadSourceRecord(caseId);
    Map<String, Object> draft = parseMap(draftJson);
    Map<String, Object> record = sourceRecordToQmsRecord(sourceRec, false);
    String qmsRecordId = String.valueOf(record.get('id'));

    Map<String, Object> body = new Map<String, Object>{
      'sourceRecordId' => qmsRecordId,
      'sourceRecordType' => record.get('type'),
      'sourceRecordTitle' => record.get('title'),
      'sector' => record.get('sector'),
      'priority' => record.get('priority'),
      'site' => record.get('site'),
      'rootCause' => value(draft, 'rootCause'),
      'immediateAction' => value(draft, 'immediateAction'),
      'correctiveAction' => value(draft, 'correctiveAction'),
      'preventiveAction' => value(draft, 'preventiveAction'),
      'capaOwner' => firstValue(draft, new List<String>{'capaOwner', 'proposedOwner'}),
      'effectivenessCheck' => value(draft, 'effectivenessCheck'),
      'riskRating' => valueOr(draft, 'riskRating', String.valueOf(record.get('priority'))),
      'regulatoryRef' => normalizedRegulatoryRefs(draft),
      'estimatedClosureDays' => closureDaysValue(draft.get('estimatedClosureDays')),
      'rcaQualityScore' => draft.get('rcaQualityScore'),
      'llmProvider' => value(draft, '_provider'),
      'llmModel' => value(draft, '_model'),
      'impactScope' => value(draft, 'impactScope'),
      'repeatEvent' => value(draft, 'repeatEvent'),
      'supplierRelated' => value(draft, 'supplierRelated'),
      'authorityNotificationRequired' => value(draft, 'authorityNotificationRequired'),
      'effectivenessCheckRequired' => value(draft, 'effectivenessCheckRequired'),
      'affectedFunctions' => value(draft, 'affectedFunctions'),
      'impactAssessmentDetail' => value(draft, 'impactAssessmentDetail'),
      'supportingDocuments' => value(draft, 'supportingDocuments'),
      'additionalNotes' => firstValue(draft, new List<String>{'additionalNotes', 'notes'}),
      'targetClosureDate' => value(draft, 'targetClosureDate'),
      'agentSummary' => value(draft, 'agentSummary'),
      'createdBy' => UserInfo.getName(),
      'createdByUsername' => UserInfo.getUserName(),
      'createdByRole' => 'salesforce'
    };

    HttpRequest req = baseRequest('/api/v1/capa/save', 'POST', 'sf-capa-save-' + sourceRec.Id + '-' + DateTime.now().getTime());
    req.setBody(JSON.serialize(body));
    Map<String, Object> saveResult = sendJson(req, 'QMS /api/v1/capa/save failed');

    Map<String, Object> data = resultData(saveResult);
    String qmsCapaId = String.valueOf(data.get('capaId'));
    if (String.isBlank(qmsCapaId) || qmsCapaId == 'null') {
      qmsCapaId = firstValue(draft, new List<String>{'capaId', 'id'});
    }

    QMS_CAPA__c shadow = new QMS_CAPA__c();
    if (sourceRec.getSObjectType() == Case.SObjectType) {
      shadow.Source_Case__c = sourceRec.Id;
    } else if (sourceRec.getSObjectType().getDescribe().getName() == 'Complaint__c') {
      shadow.Source_Complaint__c = sourceRec.Id;
    }
    shadow.QMS_CAPA_ID__c = qmsCapaId;
    shadow.Status__c = String.isBlank(value(data, 'status')) ? 'Under Review' : value(data, 'status');
    shadow.Source_Record_ID__c = truncate(valueOr(draft, 'sourceRecordId', qmsRecordId), 80);
    shadow.Source_Record_Type__c = truncate(valueOr(draft, 'sourceRecordType', String.valueOf(record.get('type'))), 80);
    shadow.Source_Record_Title__c = truncate(valueOr(draft, 'sourceTitle', String.valueOf(record.get('title'))), 255);
    shadow.Source_Priority__c = truncate(valueOr(draft, 'sourcePriority', String.valueOf(record.get('priority'))), 40);
    shadow.Site__c = truncate(valueOr(draft, 'sourceSite', String.valueOf(record.get('site'))), 120);
    shadow.Sector__c = truncate(valueOr(draft, 'sector', String.valueOf(record.get('sector'))), 80);
    shadow.Risk_Rating__c = truncate(valueOr(draft, 'riskRating', String.valueOf(record.get('priority'))), 40);
    shadow.CAPA_Owner__c = truncate(firstValue(draft, new List<String>{'capaOwner', 'proposedOwner'}), 120);
    shadow.Estimated_Closure_Days__c = closureDaysValue(draft.get('estimatedClosureDays'));
    shadow.Target_Closure_Date__c = targetClosureDate(draft);
    shadow.Root_Cause__c = value(draft, 'rootCause');
    shadow.Immediate_Action__c = value(draft, 'immediateAction');
    shadow.Corrective_Action__c = value(draft, 'correctiveAction');
    shadow.Preventive_Action__c = value(draft, 'preventiveAction');
    shadow.Effectiveness_Check__c = value(draft, 'effectivenessCheck');
    shadow.Effectiveness_Check_Required__c = truncate(value(draft, 'effectivenessCheckRequired'), 20);
    shadow.Regulatory_References__c = regulatoryRefsText(draft);
    shadow.Supporting_Documents__c = valueOr(draft, 'supportingDocuments', attachmentSummary(recordFileContext(sourceRec.Id)));
    shadow.Additional_Notes__c = firstValue(draft, new List<String>{'additionalNotes', 'notes'});
    shadow.LLM_Provider__c = truncate(value(draft, '_provider'), 80);
    shadow.LLM_Model__c = truncate(value(draft, '_model'), 160);
    shadow.Impact_Scope__c = truncate(value(draft, 'impactScope'), 120);
    shadow.Repeat_Event__c = truncate(value(draft, 'repeatEvent'), 20);
    shadow.Supplier_Related__c = truncate(value(draft, 'supplierRelated'), 20);
    shadow.Authority_Notification_Required__c = truncate(value(draft, 'authorityNotificationRequired'), 20);
    shadow.Affected_Functions__c = truncate(value(draft, 'affectedFunctions'), 255);
    shadow.Impact_Assessment_Detail__c = value(draft, 'impactAssessmentDetail');
    shadow.Agent_Summary__c = value(draft, 'agentSummary');
    shadow.QMS_URL__c = qmsCapaUrl(qmsRecordId, qmsCapaId);
    insert shadow;

    return new Map<String, Object>{
      'qms' => saveResult,
      'salesforceCapaId' => shadow.Id,
      'qmsCapaId' => qmsCapaId,
      'relatedCapas' => listRelatedCapas(caseId)
    };
  }

  @AuraEnabled(cacheable=false)
  public static List<Map<String, Object>> listRelatedCapas(Id caseId) {
    List<Map<String, Object>> rows = new List<Map<String, Object>>();
    String recordIdText = String.valueOf(caseId);
    List<QMS_CAPA__c> related = [
      SELECT Id, Name, QMS_CAPA_ID__c, Status__c, Risk_Rating__c, CAPA_Owner__c,
             Estimated_Closure_Days__c, QMS_URL__c, LLM_Provider__c, LLM_Model__c,
             Impact_Scope__c, Agent_Summary__c, Root_Cause__c, Immediate_Action__c,
             Corrective_Action__c, Preventive_Action__c, Target_Closure_Date__c, CreatedDate,
             Source_Record_ID__c, Source_Record_Type__c, Source_Record_Title__c,
             Source_Priority__c, Sector__c, Site__c, Repeat_Event__c, Supplier_Related__c,
             Authority_Notification_Required__c, Effectiveness_Check_Required__c,
             Affected_Functions__c, Impact_Assessment_Detail__c, Effectiveness_Check__c,
             Regulatory_References__c, Supporting_Documents__c, Additional_Notes__c
      FROM QMS_CAPA__c
      WHERE Source_Case__c = :caseId OR Source_Complaint__c = :caseId OR Source_Record_ID__c = :recordIdText
      ORDER BY CreatedDate DESC
      LIMIT 10
    ];
    for (QMS_CAPA__c row : related) {
      rows.add(new Map<String, Object>{
        'id' => row.Id,
        'name' => row.Name,
        'qmsCapaId' => row.QMS_CAPA_ID__c,
        'status' => row.Status__c,
        'risk' => row.Risk_Rating__c,
        'owner' => row.CAPA_Owner__c,
        'closureDays' => row.Estimated_Closure_Days__c,
        'qmsUrl' => row.QMS_URL__c,
        'llmProvider' => row.LLM_Provider__c,
        'llmModel' => row.LLM_Model__c,
        'impactScope' => row.Impact_Scope__c,
        'agentSummary' => row.Agent_Summary__c,
        'rootCause' => row.Root_Cause__c,
        'immediateAction' => row.Immediate_Action__c,
        'correctiveAction' => row.Corrective_Action__c,
        'preventiveAction' => row.Preventive_Action__c,
        'effectivenessCheck' => row.Effectiveness_Check__c,
        'regulatoryReferences' => row.Regulatory_References__c,
        'supportingDocuments' => row.Supporting_Documents__c,
        'additionalNotes' => row.Additional_Notes__c,
        'sourceRecordId' => row.Source_Record_ID__c,
        'sourceRecordType' => row.Source_Record_Type__c,
        'sourceRecordTitle' => row.Source_Record_Title__c,
        'sourcePriority' => row.Source_Priority__c,
        'sector' => row.Sector__c,
        'site' => row.Site__c,
        'repeatEvent' => row.Repeat_Event__c,
        'supplierRelated' => row.Supplier_Related__c,
        'authorityNotificationRequired' => row.Authority_Notification_Required__c,
        'effectivenessCheckRequired' => row.Effectiveness_Check_Required__c,
        'affectedFunctions' => row.Affected_Functions__c,
        'impactAssessmentDetail' => row.Impact_Assessment_Detail__c,
        'targetClosureDate' => row.Target_Closure_Date__c,
        'createdDate' => row.CreatedDate
      });
    }
    return rows;
  }

  @AuraEnabled(cacheable=false)
  public static Map<String, Object> submitCapaForApproval(Id caseId, Id salesforceCapaId) {
    String recordIdText = String.valueOf(caseId);
    QMS_CAPA__c row = [SELECT Id, Status__c FROM QMS_CAPA__c WHERE Id = :salesforceCapaId AND (Source_Case__c = :caseId OR Source_Complaint__c = :caseId OR Source_Record_ID__c = :recordIdText) LIMIT 1];
    if (row.Status__c != 'Under Review') throw new QmsCalloutException('Only CAPAs with status Under Review can be submitted for approval.');
    Approval.ProcessSubmitRequest request = new Approval.ProcessSubmitRequest();
    request.setObjectId(row.Id);
    request.setProcessDefinitionNameOrId('QMS_CAPA_Quality_Approval');
    request.setComments('Submitted from the QMS GenAI Salesforce record panel.');
    Approval.ProcessResult result = Approval.process(request);
    if (!result.isSuccess()) {
      Database.Error[] errors = result.getErrors();
      String message = errors.isEmpty() ? 'Unknown approval process error.' : errors[0].getMessage();
      throw new QmsCalloutException('Salesforce approval submission failed: ' + message);
    }
    return new Map<String, Object>{ 'approvalInstanceId' => result.getInstanceId(), 'relatedCapas' => listRelatedCapas(caseId) };
  }

  public class CapaApprovalSyncRequest {
    @InvocableVariable(required=true) public Id salesforceCapaId;
  }

  @InvocableMethod(label='Sync QMS CAPA approval outcome' callout=true)
  public static void syncApprovalOutcome(List<CapaApprovalSyncRequest> requests) {
    Set<Id> ids = new Set<Id>();
    for (CapaApprovalSyncRequest request : requests) if (request != null && request.salesforceCapaId != null) ids.add(request.salesforceCapaId);
    for (QMS_CAPA__c row : [SELECT Id, QMS_CAPA_ID__c, Status__c FROM QMS_CAPA__c WHERE Id IN :ids AND Status__c IN ('Approved', 'Pending Correction')]) {
      if (String.isBlank(row.QMS_CAPA_ID__c)) continue;
      HttpRequest req = baseRequest('/api/v1/capas/' + EncodingUtil.urlEncode(row.QMS_CAPA_ID__c, 'UTF-8') + '/status', 'PATCH', 'sf-approval-sync-' + row.Id + '-' + DateTime.now().getTime());
      req.setBody(JSON.serialize(new Map<String, Object>{ 'status' => row.Status__c, 'approvalSource' => 'salesforce', 'approvalDecision' => row.Status__c == 'Approved' ? 'Approved' : 'Rejected', 'reviewerUsername' => UserInfo.getUserName(), 'reviewerName' => UserInfo.getName(), 'meaning' => 'Salesforce Approval Process decision', 'comment' => 'Synchronized from Salesforce Approval Process.' }));
      sendJson(req, 'QMS Salesforce approval sync failed');
    }
  }
  @AuraEnabled(cacheable=false)
  public static Map<String, Object> updateCapaStatus(Id caseId, Id salesforceCapaId, String status, String signerUsername, String signerPassword, String meaning, String comment) {
    String recordIdText = String.valueOf(caseId);
    QMS_CAPA__c row = [
      SELECT Id, QMS_CAPA_ID__c
      FROM QMS_CAPA__c
      WHERE Id = :salesforceCapaId AND (Source_Case__c = :caseId OR Source_Complaint__c = :caseId OR Source_Record_ID__c = :recordIdText)
      LIMIT 1
    ];

    HttpRequest req = baseRequest('/api/v1/capas/' + EncodingUtil.urlEncode(row.QMS_CAPA_ID__c, 'UTF-8') + '/status', 'PATCH', 'sf-capa-status-' + row.Id + '-' + DateTime.now().getTime());
    req.setBody(JSON.serialize(new Map<String, Object>{
      'status' => status,
      'comment' => comment,
      'eSignature' => new Map<String, Object>{
        'signedBy' => signerUsername,
        'password' => signerPassword,
        'meaning' => meaning
      }
    }));
    Map<String, Object> apiResult = sendJson(req, 'QMS /api/v1/capas/status failed');
    Map<String, Object> data = resultData(apiResult);
    String newStatus = valueOr(data, 'status', status == 'Rejected' ? 'Pending Correction' : status);
    row.Status__c = newStatus;
    update row;

    return new Map<String, Object>{
      'qms' => apiResult,
      'status' => newStatus,
      'relatedCapas' => listRelatedCapas(caseId)
    };
  }

  @AuraEnabled(cacheable=true)
  public static String getApiHost() {
    QmsSettings__c settings = QmsSettings__c.getOrgDefaults();
    if (settings != null && String.isNotBlank(settings.Api_Host__c)) {
      String host = settings.Api_Host__c;
      return host.endsWith('/') ? host.substring(0, host.length() - 1) : host;
    }
    return 'https://qms-web-ovn9.onrender.com';
  }

  @TestVisible
  private static String sfPriorityToQms(String sfPriority) {
    if (sfPriority == null) return 'Medium';
    String p = sfPriority.toLowerCase();
    if (p.contains('high') || p == 'critical') return 'High';
    if (p.contains('low')) return 'Low';
    return 'Medium';
  }

  private static SObject loadSourceRecord(Id recordId) {
    Schema.SObjectType sourceType = recordId.getSObjectType();
    Schema.DescribeSObjectResult describe = sourceType.getDescribe();
    Map<String, Schema.SObjectField> fields = describe.fields.getMap();
    Set<String> selected = new Set<String>{'Id'};
    for (String fieldName : new List<String>{
      'CaseNumber', 'Subject', 'Name', 'Description', 'Priority', 'Priority__c', 'Origin',
      'AccountId', 'Status', 'Status__c', 'Type', 'Type__c', 'Site__c', 'Sector__c', 'Risk_Level__c',
      'Risk_Rating__c', 'Complaint_Number__c', 'Title__c', 'Issue_Title__c',
      'Summary__c', 'Product__c', 'Product_Family__c'
    }) {
      if (fields.containsKey(fieldName)) {
        selected.add(fieldName);
      }
    }
    String soql = 'SELECT ' + String.join(new List<String>(selected), ',') +
      ' FROM ' + describe.getName() + ' WHERE Id = :recordId LIMIT 1';
    return Database.query(soql);
  }

  private static Map<String, Object> sourceRecordToQmsRecord(SObject sourceRec, Boolean includeFiles) {
    String objectApiName = sourceRec.getSObjectType().getDescribe().getName();
    String sourceType = objectApiName == 'Case' ? 'complaint' : firstField(sourceRec, new List<String>{'Type__c', 'Type'});
    if (String.isBlank(sourceType)) sourceType = objectApiName == 'Complaint__c' ? 'complaint' : objectApiName;
    String sourceNumber = firstField(sourceRec, new List<String>{'CaseNumber', 'Complaint_Number__c', 'Name'});
    String title = firstField(sourceRec, new List<String>{'Subject', 'Issue_Title__c', 'Title__c', 'Name'});
    String description = firstField(sourceRec, new List<String>{'Description', 'Summary__c'});
    String priority = firstField(sourceRec, new List<String>{'Priority', 'Priority__c', 'Risk_Level__c', 'Risk_Rating__c'});
    String sector = firstField(sourceRec, new List<String>{'Sector__c', 'Product_Family__c', 'Origin'});
    String site = firstField(sourceRec, new List<String>{'Site__c', 'AccountId'});
    String status = firstField(sourceRec, new List<String>{'Status', 'Status__c'});

    Map<String, Object> record = new Map<String, Object>{
      'id' => String.valueOf(sourceRec.Id),
      'externalId' => String.valueOf(sourceRec.Id),
      'caseNumber' => sourceNumber,
      'salesforceObject' => objectApiName,
      'type' => sourceType,
      'sector' => String.isBlank(sector) ? 'BioPharma' : (sector == 'Medical Device' ? 'Medical Device' : sector),
      'priority' => sfPriorityToQms(priority),
      'title' => title,
      'description' => description,
      'status' => status,
      'site' => site,
      'owner' => UserInfo.getUserName(),
      'regulatoryRef' => new List<String>{'21 CFR 820.100', 'ISO 13485:2016'}
    };
    if (includeFiles) {
      List<Map<String, Object>> files = recordFileContext(sourceRec.Id);
      record.put('attachments', files);
      record.put('attachmentCount', files.size());
      if (!files.isEmpty()) {
        record.put('attachmentSummary', attachmentSummary(files));
      }
    }
    return record;
  }

  private static String firstField(SObject sourceRec, List<String> names) {
    Map<String, Schema.SObjectField> fields = sourceRec.getSObjectType().getDescribe().fields.getMap();
    for (String name : names) {
      if (fields.containsKey(name)) {
        Object raw = sourceRec.get(name);
        if (raw != null && !String.isBlank(String.valueOf(raw))) {
          return String.valueOf(raw);
        }
      }
    }
    return '';
  }

  private static List<Map<String, Object>> recordFileContext(Id recordId) {
    List<ContentDocumentLink> links = [
      SELECT ContentDocument.LatestPublishedVersionId
      FROM ContentDocumentLink
      WHERE LinkedEntityId = :recordId
      ORDER BY SystemModstamp DESC
      LIMIT :MAX_RCA_FILES
    ];
    Set<Id> versionIds = new Set<Id>();
    for (ContentDocumentLink link : links) {
      if (link.ContentDocument.LatestPublishedVersionId != null) {
        versionIds.add(link.ContentDocument.LatestPublishedVersionId);
      }
    }
    if (versionIds.isEmpty()) {
      return new List<Map<String, Object>>();
    }

    List<Map<String, Object>> files = new List<Map<String, Object>>();
    for (ContentVersion version : [
      SELECT Id, Title, FileExtension, FileType, ContentSize, VersionData
      FROM ContentVersion
      WHERE Id IN :versionIds
      ORDER BY CreatedDate DESC
    ]) {
      Map<String, Object> file = new Map<String, Object>{
        'id' => String.valueOf(version.Id),
        'title' => version.Title,
        'extension' => version.FileExtension,
        'fileType' => version.FileType,
        'sizeBytes' => version.ContentSize
      };
      String snippet = safeTextSnippet(version);
      if (!String.isBlank(snippet)) {
        file.put('textSnippet', snippet);
      }
      files.add(file);
    }
    return files;
  }

  private static String safeTextSnippet(ContentVersion version) {
    String ext = String.isBlank(version.FileExtension) ? '' : version.FileExtension.toLowerCase();
    if (!(ext == 'txt' || ext == 'csv' || ext == 'json' || ext == 'xml' || ext == 'log')) {
      return '';
    }
    try {
      String raw = version.VersionData == null ? '' : version.VersionData.toString();
      return truncate(raw, MAX_FILE_SNIPPET_CHARS);
    } catch (Exception e) {
      return '';
    }
  }

  private static String attachmentSummary(List<Map<String, Object>> files) {
    List<String> parts = new List<String>();
    for (Map<String, Object> file : files) {
      String line = value(file, 'title') + ' (' + value(file, 'fileType') + ', ' + value(file, 'sizeBytes') + ' bytes)';
      String snippet = value(file, 'textSnippet');
      if (!String.isBlank(snippet)) {
        line += ': ' + snippet;
      }
      parts.add(line);
    }
    return String.join(parts, '\n');
  }

  private static HttpRequest baseRequest(String path, String method, String idempotencyKey) {
    HttpRequest req = new HttpRequest();
    req.setEndpoint(NAMED_CRED + path);
    req.setMethod(method);
    req.setHeader('Content-Type', 'application/json');
    req.setHeader('X-API-Key', '{!$Credential.Password}');
    req.setHeader('X-Tenant-Id', 'sf-sandbox');
    req.setHeader('Idempotency-Key', idempotencyKey);
    req.setTimeout(60000);
    return req;
  }

  private static Map<String, Object> sendJson(HttpRequest req, String failurePrefix) {
    HttpResponse resp = new Http().send(req);
    if (resp.getStatusCode() < 200 || resp.getStatusCode() >= 300) {
      throw new QmsCalloutException(failurePrefix + ' ' + resp.getStatusCode() + ': ' + resp.getBody());
    }
    return (Map<String, Object>) JSON.deserializeUntyped(resp.getBody());
  }

  private static Map<String, Object> parseMap(String rawJson) {
    if (String.isBlank(rawJson)) {
      return new Map<String, Object>();
    }
    return (Map<String, Object>) JSON.deserializeUntyped(rawJson);
  }

  private static Map<String, Object> resultData(Map<String, Object> result) {
    if (result != null && result.get('data') != null) {
      return (Map<String, Object>) result.get('data');
    }
    return result == null ? new Map<String, Object>() : result;
  }

  private static String value(Map<String, Object> source, String key) {
    Object raw = source == null ? null : source.get(key);
    return raw == null ? '' : String.valueOf(raw);
  }

  private static String valueOr(Map<String, Object> source, String key, String fallback) {
    String raw = value(source, key);
    return String.isBlank(raw) ? fallback : raw;
  }

  private static String firstValue(Map<String, Object> source, List<String> keys) {
    for (String key : keys) {
      String raw = value(source, key);
      if (!String.isBlank(raw)) return raw;
    }
    return '';
  }

  private static Decimal decimalValue(Object raw) {
    if (raw == null) return null;
    try {
      return Decimal.valueOf(String.valueOf(raw));
    } catch (Exception e) {
      return null;
    }
  }

  private static Integer closureDaysValue(Object raw) {
    if (raw == null || String.isBlank(String.valueOf(raw))) return 30;
    try {
      Integer days = Integer.valueOf(String.valueOf(raw));
      if (days < 1) return 30;
      if (days > 365) return 365;
      return days;
    } catch (Exception e) {
      return 30;
    }
  }

  private static Date targetClosureDate(Map<String, Object> draft) {
    String raw = value(draft, 'targetClosureDate');
    if (!String.isBlank(raw)) {
      try {
        return Date.valueOf(raw);
      } catch (Exception e) {
        // Fall through to closure-days derived date.
      }
    }
    return Date.today().addDays(closureDaysValue(draft == null ? null : draft.get('estimatedClosureDays')));
  }

  private static Object normalizedRegulatoryRefs(Map<String, Object> draft) {
    Object raw = draft == null ? null : draft.get('regulatoryRef');
    if (raw == null || String.isBlank(String.valueOf(raw))) {
      return new List<String>{'21 CFR 820.100', 'ISO 13485:2016'};
    }
    return raw;
  }

  private static String regulatoryRefsText(Map<String, Object> draft) {
    Object raw = normalizedRegulatoryRefs(draft);
    List<String> values = new List<String>();
    if (raw instanceof List<String>) {
      for (String item : (List<String>) raw) {
        if (!String.isBlank(item)) values.add(item);
      }
      return String.join(values, ', ');
    }
    if (raw instanceof List<Object>) {
      for (Object item : (List<Object>) raw) {
        if (item != null && !String.isBlank(String.valueOf(item))) values.add(String.valueOf(item));
      }
      return String.join(values, ', ');
    }
    return String.valueOf(raw);
  }

  private static String truncate(String raw, Integer maxLen) {
    if (raw == null || raw.length() <= maxLen) return raw;
    return raw.substring(0, maxLen);
  }

  private static String qmsCapaUrl(String recordId, String capaId) {
    String url = getApiHost() + '/capa/create?id=' + EncodingUtil.urlEncode(recordId, 'UTF-8');
    if (!String.isBlank(capaId)) {
      url += '&capaId=' + EncodingUtil.urlEncode(capaId, 'UTF-8');
    }
    return url;
  }

  public class QmsCalloutException extends Exception {}
}
