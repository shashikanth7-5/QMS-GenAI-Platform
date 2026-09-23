/**
 * QmsGenAiClientTest - unit tests for QmsGenAiClient callouts.
 *
 * Uses HttpCalloutMock; no live HTTP is issued. Targets >75% coverage.
 */
@isTest
private class QmsGenAiClientTest {

  /** Mock returning HTTP 200 with a canned CAPA payload. */
  private class QmsMock200 implements HttpCalloutMock {
    public HttpResponse respond(HttpRequest req) {
      HttpResponse resp = new HttpResponse();
      resp.setStatusCode(200);
      resp.setHeader('Content-Type', 'application/json');
      if (req.getEndpoint().contains('/capa/save')) {
        resp.setBody('{"status":"success","data":{"capaId":"CAPA-TEST-001","status":"Under Review"}}');
      } else if (req.getEndpoint().contains('/status')) {
        resp.setBody('{"status":"success","data":{"capaId":"CAPA-TEST-001","status":"Approved","requestedStatus":"Approved"}}');
      } else if (req.getEndpoint().contains('/rca/assess')) {
        resp.setBody('{"status":"success","data":{"overall_score":82,"verdict_msg":"Strong RCA"}}');
      } else if (req.getEndpoint().contains('/rca/propose')) {
        resp.setBody('{"status":"success","data":{"models":[{"name":"Model A","rootCause":"seal fatigue","_provider":"groq","_model":"test"}],"provider":"groq","model":"test"}}');
      } else if (req.getEndpoint().contains('/rca/analyze')) {
        resp.setBody('{"status":"success","data":{"rca":{"rootCause":"seal fatigue","_provider":"groq","_model":"test"},"method":"fishbone"}}');
      } else {
        resp.setBody(
          '{"success":true,"data":{"capa":{"rootCause":"seal fatigue",' +
          '"correctiveAction":"replace seals","preventiveAction":"pm schedule",' +
          '"riskRating":"High"}},"recordId":"QR-2024-0001"}'
        );
      }
      return resp;
    }
  }

  /** Mock returning HTTP 500 for negative-path tests. */
  private class QmsMock500 implements HttpCalloutMock {
    public HttpResponse respond(HttpRequest req) {
      HttpResponse resp = new HttpResponse();
      resp.setStatusCode(500);
      resp.setBody('{"error":"boom"}');
      return resp;
    }
  }

  private static Case newCase() {
    Case c = new Case(
      Subject = 'Pump seal leak',
      Priority = 'High',
      Description = 'Observed leakage during CIP cycle.',
      Origin = 'Medical Device'
    );
    insert c;
    return c;
  }

  private static Complaint__c newComplaint() {
    Complaint__c complaint = new Complaint__c(
      Issue_Title__c = 'ECG battery complaint',
      Summary__c = 'Battery failed during incoming inspection.',
      Priority__c = 'High',
      Risk_Level__c = 'Critical',
      Sector__c = 'Medical Device',
      Site__c = 'Cognizant ECG Plant',
      Type__c = 'complaint',
      Status__c = 'New',
      Product__c = 'ECG Machine'
    );
    insert complaint;
    return complaint;
  }

  @isTest
  static void testGenerateCapaSuccess() {
    Case c = newCase();
    Test.setMock(HttpCalloutMock.class, new QmsMock200());

    Test.startTest();
    Map<String, Object> result = QmsGenAiClient.generateCapa(c.Id);
    Test.stopTest();

    System.assertNotEquals(null, result, 'result should not be null');
    System.assertEquals(true, result.get('success'), 'success flag should be true');
    System.assertEquals('QR-2024-0001', String.valueOf(result.get('recordId')));
  }

  @isTest
  static void testRunAgentPipelineSuccess() {
    Case c = newCase();
    Test.setMock(HttpCalloutMock.class, new QmsMock200());

    Test.startTest();
    Map<String, Object> result = QmsGenAiClient.runAgentPipeline(c.Id, true);
    Test.stopTest();

    System.assertNotEquals(null, result);
    System.assertEquals('QR-2024-0001', String.valueOf(result.get('recordId')));
  }

  @isTest
  static void testRcaAndModelMethodsSuccess() {
    Case c = newCase();
    Test.setMock(HttpCalloutMock.class, new QmsMock200());

    Test.startTest();
    Map<String, Object> rca = QmsGenAiClient.runRca(c.Id, 'fishbone');
    Map<String, Object> models = QmsGenAiClient.proposeRcaModels(c.Id, 'fishbone');
    Map<String, Object> score = QmsGenAiClient.reassessRca(c.Id, 'fishbone', '{"rootCause":"seal fatigue"}');
    Test.stopTest();

    System.assertNotEquals(null, rca);
    System.assertNotEquals(null, models);
    System.assertNotEquals(null, score);
  }

  @isTest
  static void testGenerateFromRcaAndSaveShadowCapa() {
    Case c = newCase();
    Test.setMock(HttpCalloutMock.class, new QmsMock200());

    Test.startTest();
    Map<String, Object> generated = QmsGenAiClient.generateCapaFromRca(c.Id, '{"rootCause":"seal fatigue"}');
    Map<String, Object> saved = QmsGenAiClient.saveCapaDraft(
      c.Id,
      '{"rootCause":"seal fatigue","immediateAction":"quarantine","correctiveAction":"replace seals","preventiveAction":"pm schedule","effectivenessCheck":"verify next lots","riskRating":"High","estimatedClosureDays":30,"_provider":"groq","_model":"test"}'
    );
    Test.stopTest();

    System.assertNotEquals(null, generated);
    System.assertEquals('CAPA-TEST-001', String.valueOf(saved.get('qmsCapaId')));
    System.assertEquals(1, [SELECT COUNT() FROM QMS_CAPA__c WHERE Source_Case__c = :c.Id]);
  }

  @isTest
  static void testSaveShadowCapaFromComplaint() {
    Complaint__c complaint = newComplaint();
    Test.setMock(HttpCalloutMock.class, new QmsMock200());

    Test.startTest();
    Map<String, Object> saved = QmsGenAiClient.saveCapaDraft(
      complaint.Id,
      '{"rootCause":"battery supplier variation","immediateAction":"segregate inventory","correctiveAction":"supplier investigation","preventiveAction":"incoming battery screening","effectivenessCheck":"verify three lots","riskRating":"Critical","estimatedClosureDays":45,"impactScope":"Product impact","_provider":"groq","_model":"test"}'
    );
    Test.stopTest();

    System.assertEquals('CAPA-TEST-001', String.valueOf(saved.get('qmsCapaId')));
    System.assertEquals(1, [SELECT COUNT() FROM QMS_CAPA__c WHERE Source_Complaint__c = :complaint.Id]);
  }

  @isTest
  static void testUpdateCapaStatusFromCasePanel() {
    Case c = newCase();
    QMS_CAPA__c capa = new QMS_CAPA__c(
      Source_Case__c = c.Id,
      QMS_CAPA_ID__c = 'CAPA-TEST-001',
      Status__c = 'Under Review',
      Root_Cause__c = 'seal fatigue'
    );
    insert capa;
    Test.setMock(HttpCalloutMock.class, new QmsMock200());

    Test.startTest();
    Map<String, Object> result = QmsGenAiClient.updateCapaStatus(
      c.Id,
      capa.Id,
      'Approved',
      'admin',
      'password',
      'I approve this CAPA after quality review.',
      'Looks complete'
    );
    Test.stopTest();

    System.assertEquals('Approved', String.valueOf(result.get('status')));
    System.assertEquals('Approved', [SELECT Status__c FROM QMS_CAPA__c WHERE Id = :capa.Id].Status__c);
  }

  @isTest
  static void testGenerateCapaFailureThrows() {
    Case c = newCase();
    Test.setMock(HttpCalloutMock.class, new QmsMock500());

    Boolean thrown = false;
    Test.startTest();
    try {
      QmsGenAiClient.generateCapa(c.Id);
    } catch (QmsGenAiClient.QmsCalloutException e) {
      thrown = true;
    }
    Test.stopTest();

    System.assert(thrown, 'QmsCalloutException should be thrown on non-2xx');
  }

  @isTest
  static void testRunAgentPipelineFailureThrows() {
    Case c = newCase();
    Test.setMock(HttpCalloutMock.class, new QmsMock500());

    Boolean thrown = false;
    Test.startTest();
    try {
      QmsGenAiClient.runAgentPipeline(c.Id, false);
    } catch (QmsGenAiClient.QmsCalloutException e) {
      thrown = true;
    }
    Test.stopTest();

    System.assert(thrown, 'QmsCalloutException should be thrown on non-2xx');
  }

  @isTest
  static void testGetApiHost() {
    Test.startTest();
    String host = QmsGenAiClient.getApiHost();
    Test.stopTest();
    System.assert(host != null && host.startsWith('https://'), 'API host should be https URL');
  }

  @isTest
  static void testSfPriorityMapping() {
    System.assertEquals('High',   QmsGenAiClient.sfPriorityToQms('High'));
    System.assertEquals('High',   QmsGenAiClient.sfPriorityToQms('Critical'));
    System.assertEquals('Low',    QmsGenAiClient.sfPriorityToQms('Low'));
    System.assertEquals('Medium', QmsGenAiClient.sfPriorityToQms('Medium'));
    System.assertEquals('Medium', QmsGenAiClient.sfPriorityToQms(null));
  }
}
