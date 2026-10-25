from urllib.parse import urlencode
from app.providers.contracts import ModelInfo, GenerationResult, ProviderError, model_id, number, text, safe_id
from app.providers.transport import JsonTransport

class AnthropicProvider:
    def __init__(self,transport=None):self.transport=transport or JsonTransport()
    def headers(self,key):return {'X-Api-Key':key,'anthropic-version':'2023-06-01'}
    def list_models(self,credential):
        out=[];cursor=None;seen=set()
        for _ in range(20):
            path='/v1/models?'+urlencode({'limit':100,**({'after_id':cursor} if cursor else {})})
            body=self.transport.request('anthropic','GET',path,self.headers(credential));rows=body.get('data')
            if not isinstance(rows,list) or len(rows)>100:raise ProviderError('malformed')
            for r in rows:
                if not isinstance(r,dict):raise ProviderError('malformed')
                ident=model_id(r.get('id'));cap=r.get('capabilities') or {}
                if not isinstance(cap,dict):raise ProviderError('malformed')
                structured=cap.get('structured_outputs') or {}
                if not isinstance(structured,dict):raise ProviderError('malformed')
                struct=structured.get('supported')
                out.append(ModelInfo(ident,text(r.get('display_name')) or ident,number(r.get('max_input_tokens')),
                    number(r.get('max_tokens')),True,struct if type(struct) is bool else None))
            if body.get('has_more') is False:return out
            if body.get('has_more') is not True:raise ProviderError('malformed')
            cursor=body.get('last_id')
            if not isinstance(cursor,str) or not 1<=len(cursor)<=200 or cursor in seen:raise ProviderError('catalog_incomplete')
            seen.add(cursor)
        raise ProviderError('catalog_incomplete')
    def generate(self,credential,request):
        r=self.transport.request('anthropic','POST','/v1/messages',self.headers(credential),
            {**({'system':request.instructions} if request.instructions else {}),'model':request.model,'messages':[{'role':'user','content':request.prompt}],
             'max_tokens':request.max_output_tokens,'service_tier':'standard_only',
             'output_config':{'format':{'type':'json_schema','schema':request.schema}}})
        try:
            content=[];unknown=False
            for p in r.get('content',[]):
                if p.get('type')=='text':content.append(p['text'])
                elif p.get('type') not in {'thinking','redacted_thinking'}:unknown=True
            stop=r.get('stop_reason');detail=r.get('stop_details') or {}
            finish='refused' if stop=='refusal' or detail.get('type')=='refusal' else 'truncated' if stop=='max_tokens' else 'complete' if stop=='end_turn' and not unknown else 'unexpected'
            u=r.get('usage') or {};inp=number(u.get('input_tokens'));cache=number(u.get('cache_read_input_tokens',0));created=number(u.get('cache_creation_input_tokens',0))
            supported=created==0 and not any((u.get('server_tool_use') or {}).values()) and u.get('service_tier') in {None,'standard'}
            return GenerationResult(''.join(content),safe_id(r.get('model')),safe_id(r.get('id')),finish,
                inp+cache if inp is not None and cache is not None else None,number(u.get('output_tokens')),supported)
        except (TypeError,AttributeError,KeyError):raise ProviderError('malformed',ambiguous=True) from None
