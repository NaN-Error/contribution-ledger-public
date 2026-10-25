/** Narrow local webhook ingress. Never proxies the ledger UI, login or evidence.
 * The backend verifies the HMAC over the bytes collected here, unchanged.
 * TLS and public rate limiting belong to a deliberately configured external edge.
 */
import http from 'node:http';
import {pathToFileURL} from 'node:url';
export const WEBHOOK_PATH='/api/v1/github/webhook';
export const MAX_BYTES=1048576;
const FORWARDED=new Set(['x-hub-signature-256','x-github-delivery','x-github-event']);
const CHECKED=new Set([...FORWARDED,'content-type','content-length','content-encoding']);
export function validateUpstream(value) {
  const url=new URL(value);
  if(url.protocol!=='http:'||!['api','127.0.0.1'].includes(url.hostname)||url.username||url.password||url.pathname!=='/'||url.search||url.hash)
    throw new Error('Webhook upstream must be the fixed local API origin.');
  return url;
}
export function createGateway({upstream='http://api:8000',timeout=5000}={}) {
  const target=validateUpstream(upstream);
  const server=http.createServer({maxHeaderSize:8192,requestTimeout:8000,headersTimeout:8000},(req,res)=>{
    const reply=(status,code)=>{if(res.writableEnded)return;res.writeHead(status,{'content-type':'application/json','cache-control':'no-store','x-content-type-options':'nosniff','connection':'close'});res.end(JSON.stringify({error:{code}}));};
    if(req.method!=='POST'||req.url!==WEBHOOK_PATH){req.resume();reply(404,'not_found');return;}
    const seen=new Set();
    for(let i=0;i<req.rawHeaders.length;i+=2){const name=req.rawHeaders[i].toLowerCase();if(CHECKED.has(name)&&seen.has(name)){req.resume();reply(400,'ambiguous_headers');return;}seen.add(name);}
    if(!String(req.headers['content-type']||'').toLowerCase().match(/^application\/json(?:;\s*charset=utf-8)?$/)||req.headers['content-encoding']){req.resume();reply(415,'unsupported_encoding');return;}
    if([...FORWARDED].some(h=>typeof req.headers[h]!=='string')){req.resume();reply(401,'signature_headers_required');return;}
    const declared=req.headers['content-length'];
    if(declared!==undefined&&(!/^\d+$/.test(declared)||Number(declared)>MAX_BYTES)){req.resume();reply(413,'body_too_large');return;}
    const chunks=[];let size=0,ended=false;
    req.setTimeout(8000,()=>{reply(408,'request_timeout');req.destroy();});
    req.on('data',chunk=>{if(ended)return;size+=chunk.length;if(size>MAX_BYTES){ended=true;chunks.length=0;reply(413,'body_too_large');return;}chunks.push(chunk);});
    req.on('error',()=>{ended=true;reply(400,'request_failed');});
    req.on('end',()=>{
      if(ended||res.writableEnded)return;ended=true;
      const raw=Buffer.concat(chunks);const headers={'content-type':'application/json','content-length':String(raw.length),'host':target.host};
      for(const name of FORWARDED)headers[name]=req.headers[name];
      // Cookies, authorization, origin, forwarding headers and arbitrary paths are stripped.
      const upstreamRequest=http.request(new URL(WEBHOOK_PATH,target),{method:'POST',headers,timeout},response=>{
        const parts=[];let bytes=0;response.on('data',chunk=>{bytes+=chunk.length;if(bytes>16384){response.destroy();reply(502,'upstream_response_limit');return;}parts.push(chunk);});
        response.on('error',()=>reply(502,'upstream_failed'));
        response.on('end',()=>{if(res.writableEnded)return;res.writeHead(response.statusCode||502,{'content-type':'application/json','cache-control':'no-store','x-content-type-options':'nosniff','connection':'close'});res.end(Buffer.concat(parts));});
      });
      upstreamRequest.on('timeout',()=>upstreamRequest.destroy(new Error('timeout')));
      upstreamRequest.on('error',()=>reply(503,'upstream_unavailable'));
      res.on('close',()=>{if(!res.writableFinished)upstreamRequest.destroy();});
      upstreamRequest.end(raw);
    });
  });
  server.maxHeadersCount=30;
  server.on('upgrade',(req,socket)=>{socket.end('HTTP/1.1 404 Not Found\r\nConnection: close\r\n\r\n');});
  server.on('connect',(req,socket)=>{socket.end('HTTP/1.1 405 Method Not Allowed\r\nConnection: close\r\n\r\n');});
  return server;
}
if(process.argv[1]&&import.meta.url===pathToFileURL(process.argv[1]).href) {
  const host=process.env.HOST||'127.0.0.1';const port=Number(process.env.PORT||8010);
  if(!['127.0.0.1','0.0.0.0'].includes(host)||!Number.isInteger(port)||port<1||port>65535)throw new Error('Invalid gateway binding.');
  createGateway({upstream:process.env.API_UPSTREAM||'http://api:8000'}).listen(port,host);
}
