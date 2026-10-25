from app.providers.contracts import ModelInfo, GenerationResult, ProviderError, model_id, number, text, safe_id
from app.providers.transport import JsonTransport

class OpenAIProvider:
    def __init__(self,transport=None):self.transport=transport or JsonTransport()
    def headers(self,key):return {'Authorization':f'Bearer {key}'}
    def list_models(self,credential):
        body=self.transport.request('openai','GET','/v1/models',self.headers(credential))
        rows=body.get('data')
        if not isinstance(rows,list) or len(rows)>2000 or body.get('has_more'):
            raise ProviderError('catalog_incomplete')
        result=[]
        for row in rows:
            if not isinstance(row,dict):raise ProviderError('malformed')
            ident=model_id(row.get('id'))
            # Basic listing has no reliable universal modality/token/pricing schema.
            result.append(ModelInfo(ident,ident,metadata={'owned_by':text(row.get('owned_by')),
                'shutdown_date':text(row.get('shutdown_date'),40)}))
        return result
    def generate(self,credential,request):
        r=self.transport.request('openai','POST','/v1/responses',self.headers(credential),
            {**({'instructions':request.instructions} if request.instructions else {}),'model':request.model,'input':[{'role':'user','content':request.prompt}],
             'max_output_tokens':request.max_output_tokens,'store':False,'service_tier':'default',
             'text':{'format':{'type':'json_schema','name':'ledger_result','strict':True,'schema':request.schema}}})
        try:
            content=[];refusal=False;unknown=False
            for item in r.get('output',[]):
                if item.get('type')=='reasoning':continue # do not save private reasoning
                if item.get('type')!='message':unknown=True;continue
                for part in item.get('content',[]):
                    if part.get('type')=='refusal':refusal=True
                    elif part.get('type')=='output_text':content.append(part['text'])
                    else:unknown=True
            status=r.get('status');why=(r.get('incomplete_details') or {}).get('reason')
            finish='refused' if refusal or why=='content_filter' else 'truncated' if status=='incomplete' and why=='max_output_tokens' else 'complete' if status=='completed' and not unknown else 'unexpected'
            u=r.get('usage') or {}
            return GenerationResult(''.join(content),safe_id(r.get('model')),safe_id(r.get('id')),finish,
                number(u.get('input_tokens')),number(u.get('output_tokens')),
                r.get('service_tier') in {None,'default'})
        except (TypeError,AttributeError,KeyError):raise ProviderError('malformed',ambiguous=True) from None
