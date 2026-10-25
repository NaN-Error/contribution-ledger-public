"""TLS-only fixed-host requests, bounded JSON and no redirects/proxies/automatic retries."""
import http.client
import json
import re
import socket
import ssl
import time
from urllib.parse import urlsplit
from app.providers.contracts import ProviderError, parse_json

HOSTS={'openai':'api.openai.com','anthropic':'api.anthropic.com','gemini':'generativelanguage.googleapis.com'}

class JsonTransport:
    def __init__(self, connection_factory=http.client.HTTPSConnection):
        self.connection_factory=connection_factory
    def request(self, provider, method, path, headers, body=None):
        if provider not in HOSTS or method not in {'GET','POST'} or not path.startswith('/') or path.startswith('//'):
            raise ProviderError('incompatible')
        p=urlsplit(path)
        if p.scheme or p.netloc or p.fragment or '\\' in path or any(ord(c)<32 for c in path):
            raise ProviderError('incompatible')
        raw=None if body is None else json.dumps(body,allow_nan=False,separators=(',',':')).encode()
        if raw is not None and len(raw)>98304:raise ProviderError('incompatible')
        conn=None;started=False
        try:
            conn=self.connection_factory(HOSTS[provider],timeout=20,context=ssl.create_default_context())
            # Validate/connect TLS before the possibly-billed boundary.
            conn.connect()
            started=True
            conn.request(method,path,body=raw,headers={**headers,'Accept':'application/json','Content-Type':'application/json',
                'Accept-Encoding':'identity','User-Agent':'ContributionLedger/0.10 provider-foundation'})
            res=conn.getresponse()
            if res.status!=200:
                status=res.status
                retry=res.getheader('Retry-After','60')
                delay=int(retry) if re.fullmatch(r'[0-9]{1,8}',str(retry)) else 60
                code={400:'incompatible',401:'authentication',403:'permission',404:'model_unavailable',429:'rate_limited'}.get(status,'provider_failure')
                # Do not read or log error bodies (may echo credentials or input).
                raise ProviderError(code,ambiguous=method=='POST' and status not in {400,401,403,404,429},retry_after=delay)
            if res.getheader('Content-Encoding','identity').lower() not in {'identity',''}:
                raise ProviderError('malformed',ambiguous=method=='POST')
            content_type=res.getheader('Content-Type','').split(';')[0].strip().lower()
            if content_type!='application/json':raise ProviderError('malformed',ambiguous=method=='POST')
            length=res.getheader('Content-Length')
            if length and (not length.isdigit() or int(length)>4*1024*1024):
                raise ProviderError('malformed',ambiguous=method=='POST')
            chunks=[];size=0;deadline=time.monotonic()+25
            while True:
                if time.monotonic()>deadline:raise ProviderError('timeout',ambiguous=method=='POST')
                chunk=res.read(65536)
                if not chunk:break
                size+=len(chunk)
                if size>4*1024*1024:raise ProviderError('malformed',ambiguous=method=='POST')
                chunks.append(chunk)
            value=parse_json(b''.join(chunks).decode('utf-8'))
            if not isinstance(value,dict):raise ValueError('Object expected')
            return value
        except ProviderError: raise
        except (TimeoutError,socket.timeout):raise ProviderError('timeout',ambiguous=started and method=='POST') from None
        except (UnicodeError,ValueError,RecursionError):raise ProviderError('malformed',ambiguous=started and method=='POST') from None
        except (OSError,http.client.HTTPException):raise ProviderError('transport',ambiguous=started and method=='POST') from None
        finally:
            if conn is not None:conn.close()
