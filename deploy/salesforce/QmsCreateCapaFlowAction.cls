/**
 * Invocable wrapper so Salesforce Flow can call the QMS GenAI pipeline.
 */
public with sharing class QmsCreateCapaFlowAction {

  public class Request {
    @InvocableVariable(required=true)
    public Id caseId;
  }

  public class Response {
    @InvocableVariable
    public String status;

    @InvocableVariable
    public String message;

    @InvocableVariable
    public String capaId;

    @InvocableVariable
    public String qmsUrl;
  }

  @InvocableMethod(
    label='Create CAPA with AI'
    description='Calls QMS GenAI to create a CAPA draft from a Salesforce Case.'
  )
  public static List<Response> createCapa(List<Request> requests) {
    List<Response> responses = new List<Response>();

    for (Request reqItem : requests) {
      Response res = new Response();
      try {
        Map<String, Object> result = QmsGenAiClient.runAgentPipeline(reqItem.caseId, true);
        Map<String, Object> data = (Map<String, Object>) result.get('data');
        Map<String, Object> capa = data == null ? null : (Map<String, Object>) data.get('capa');
        Map<String, Object> ui = data == null ? null : (Map<String, Object>) data.get('ui');

        res.status = String.valueOf(result.get('status'));
        res.capaId = capa == null ? '' : String.valueOf(capa.get('id'));
        String path = ui == null ? '' : String.valueOf(ui.get('openDraftUrl'));
        res.qmsUrl = String.isBlank(path) ? QmsGenAiClient.getApiHost() : QmsGenAiClient.getApiHost() + path;
        res.message = 'CAPA draft ' + res.capaId + ' created in QMS for Case ' + String.valueOf(reqItem.caseId);
      } catch (Exception e) {
        res.status = 'error';
        res.message = e.getMessage();
        res.capaId = '';
        res.qmsUrl = '';
      }
      responses.add(res);
    }

    return responses;
  }
}
