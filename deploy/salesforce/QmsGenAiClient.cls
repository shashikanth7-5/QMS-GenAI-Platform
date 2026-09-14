/**
 * QmsGenAiClient - Apex client for the QMS GenAI REST API.
 */
public with sharing class QmsGenAiClient {

  private static final String NAMED_CRED = 'callout:QMS_GenAI';
  private static final Integer MAX_RCA_FILES = 15;
  private static final Integer MAX_FILE_SNIPPET_CHARS = 2500;

  @AuraEnabled(cacheable=false)
  public static Map<String, Object> getCaseContext(Id caseId) {
    Case caseRec = loadCase(caseId);
    return new Map<String, Object>{
      'record' => caseToQmsRecord(caseRec, true),
      'relatedCapas' => listRelatedCapas(caseId),
      'apiHost' => getApiHost()
    };
  }

  @AuraEnabled(cacheable=false)
  public static Map<String, Object> generateCapa(Id caseId) {
    Case caseRec = loadCase(caseId);
    HttpRequest req = baseRequest('/api/v1/capa/generate', 'POST', 'sf-capa-generate-' + caseRec.Id);
    req.setBody(JSON.serialize(new Map<String, Object>{ 'record' => caseToQmsRecord(caseRec, true) }));
    return sendJson(req, 'QMS /api/v1/capa/generate failed');
  }

  @AuraEnabled(cacheable=false)
  public static Map<String, Object> generateCapaFromRca(Id caseId, String rcaJson) {
    Case caseRec = loadCase(caseId);
    Map<String, Object> record = caseToQmsRecord(caseRec, true);
    Map<String, Object> rca = parseMap(rcaJson);
    record.put('rca', rca);
    record.put('rootCause', value(rca, 'rootCause'));

    HttpRequest req = baseRequest('/api/v1/capa/generate', 'POST', 'sf-capa-generate-rca-' + caseRec.Id + '-' + DateTime.now().getTime());
    req.setBody(JSON.serialize(new Map<String, Object>{ 'record' => record }));
    return sendJson(req, 'QMS /api/v1/capa/generate failed');
  }

  @AuraEnabled(cacheable=false)
  public static Map<String, Object> runRca(Id caseId, String method) {
    Case caseRec = loadCase(caseId);
    String selectedMethod = String.isBlank(method) ? 'fishbone' : method;
    HttpRequest req = baseRequest('/api/v1/rca/analyze', 'POST', 'sf-rca-' + selectedMethod + '-' + caseRec.Id + '-' + DateTime.now().getTime());
    req.setBody(JSON.serialize(new Map<String, Object>{
      'record' => caseToQmsRecord(caseRec, true),
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
    Case caseRec = loadCase(caseId);
    String selectedMethod = String.isBlank(method) ? 'fishbone' : method;
    HttpRequest req = baseRequest('/api/v1/rca/propose', 'POST', 'sf-rca-models-' + selectedMethod + '-' + caseRec.Id + '-' + DateTime.now().getTime());
    req.setBody(JSON.serialize(new Map<String, Object>{
      'record' => caseToQmsRecord(caseRec, true),
      'method' => selectedMethod
    }));
    return sendJson(req, 'QMS /api/v1/rca/propose failed');
  }

  @AuraEnabled(cacheable=false)
  public static Map<String, Object> runAgentPipeline(Id caseId, Boolean saveDraft) {
    Case caseRec = loadCase(caseId);
    HttpRequest req = baseRequest('/api/v1/integrations/quality-event/capa', 'POST', 'sf-agent-' + caseRec.Id);
    req.setTimeout(120000);
    req.setBody(JSON.serialize(new Map<String, Object>{
      'record' => caseToQmsRecord(caseRec, true),
      'options' => new Map<String, Object>{'saveDraft' => saveDraft}
    }));
    return sendJson(req, 'QMS /api/v1/integrations failed');
  }

  @AuraEnabled(cacheable=false)
  public static Map<String, Object> saveCapaDraft(Id caseId, String draftJson) {
    Case caseRec = loadCase(caseId);
    Map<String, Object> draft = parseMap(draftJson);
    Map<String, Object> record = caseToQmsRecord(caseRec, false);
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
      'agentSummary' => value(draft, 'agentSummary'),
      'createdBy' => UserInfo.getName(),
      'createdByUsername' => UserInfo.getUserName(),
      'createdByRole' => 'salesforce'
    };

    HttpRequest req = baseRequest('/api/v1/capa/save', 'POST', 'sf-capa-save-' + caseRec.Id + '-' + DateTime.now().getTime());
    req.setBody(JSON.serialize(body));
    Map<String, Object> saveResult = sendJson(req, 'QMS /api/v1/capa/save failed');

    Map<String, Object> data = resultData(saveResult);
    String qmsCapaId = String.valueOf(data.get('capaId'));
    if (String.isBlank(qmsCapaId) || qmsCapaId == 'null') {
      qmsCapaId = firstValue(draft, new List<String>{'capaId', 'id'});
    }

    QMS_CAPA__c shadow = new QMS_CAPA__c();
    shadow.Source_Case__c = caseRec.Id;
    shadow.QMS_CAPA_ID__c = qmsCapaId;
    shadow.Status__c = String.isBlank(value(data, 'status')) ? 'Under Review' : value(data, 'status');
    shadow.Source_Record_ID__c = truncate(qmsRecordId, 80);
    shadow.Source_Record_Type__c = truncate(String.valueOf(record.get('type')), 80);
    shadow.Source_Record_Title__c = truncate(String.valueOf(record.get('title')), 255);
    shadow.Source_Priority__c = truncate(String.valueOf(record.get('priority')), 40);
    shadow.Site__c = truncate(String.valueOf(record.get('site')), 120);
    shadow.Sector__c = truncate(String.valueOf(record.get('sector')), 80);
    shadow.Risk_Rating__c = truncate(valueOr(draft, 'riskRating', String.valueOf(record.get('priority'))), 40);
    shadow.CAPA_Owner__c = truncate(firstValue(draft, new List<String>{'capaOwner', 'proposedOwner'}), 120);
    shadow.Estimated_Closure_Days__c = closureDaysValue(draft.get('estimatedClosureDays'));
    shadow.Target_Closure_Date__c = Date.today().addDays(closureDaysValue(draft.get('estimatedClosureDays')));
    shadow.Root_Cause__c = value(draft, 'rootCause');
    shadow.Immediate_Action__c = value(draft, 'immediateAction');
    shadow.Corrective_Action__c = value(draft, 'correctiveAction');
    shadow.Preventive_Action__c = value(draft, 'preventiveAction');
    shadow.Effectiveness_Check__c = value(draft, 'effectivenessCheck');
    shadow.Effectiveness_Check_Required__c = truncate(value(draft, 'effectivenessCheckRequired'), 20);
    shadow.Regulatory_References__c = regulatoryRefsText(draft);
    shadow.Supporting_Documents__c = attachmentSummary(caseFileContext(caseRec.Id));
    shadow.Additional_Notes__c = value(draft, 'notes');
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
    for (QMS_CAPA__c row : [
      SELECT Id, Name, QMS_CAPA_ID__c, Status__c, Risk_Rating__c, CAPA_Owner__c,
             Estimated_Closure_Days__c, QMS_URL__c, LLM_Provider__c, LLM_Model__c,
             Impact_Scope__c, Agent_Summary__c, Root_Cause__c, Immediate_Action__c,
             Corrective_Action__c, Preventive_Action__c, Target_Closure_Date__c, CreatedDate
      FROM QMS_CAPA__c
      WHERE Source_Case__c = :caseId
      ORDER BY CreatedDate DESC
      LIMIT 10
    ]) {
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
        'targetClosureDate' => row.Target_Closure_Date__c,
        'createdDate' => row.CreatedDate
      });
    }
    return rows;
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

  private static Case loadCase(Id caseId) {
    return [
      SELECT Id, CaseNumber, Subject, Description, Priority, Origin, AccountId, Status, Type
      FROM Case
      WHERE Id = :caseId
      LIMIT 1
    ];
  }

  private static Map<String, Object> caseToQmsRecord(Case caseRec, Boolean includeFiles) {
    Map<String, Object> record = new Map<String, Object>{
      'id' => String.valueOf(caseRec.Id),
      'externalId' => String.valueOf(caseRec.Id),
      'caseNumber' => caseRec.CaseNumber,
      'type' => 'complaint',
      'sector' => (caseRec.Origin == 'Medical Device') ? 'Medical Device' : 'BioPharma',
      'priority' => sfPriorityToQms(caseRec.Priority),
      'title' => caseRec.Subject,
      'description' => caseRec.Description,
      'status' => caseRec.Status,
      'site' => String.valueOf(caseRec.AccountId),
      'owner' => UserInfo.getUserName(),
      'regulatoryRef' => new List<String>{'21 CFR 820.100', 'ISO 13485:2016'}
    };
    if (includeFiles) {
      List<Map<String, Object>> files = caseFileContext(caseRec.Id);
      record.put('attachments', files);
      record.put('attachmentCount', files.size());
      if (!files.isEmpty()) {
        record.put('attachmentSummary', attachmentSummary(files));
      }
    }
    return record;
  }

  private static List<Map<String, Object>> caseFileContext(Id caseId) {
    List<ContentDocumentLink> links = [
      SELECT ContentDocument.LatestPublishedVersionId
      FROM ContentDocumentLink
      WHERE LinkedEntityId = :caseId
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
