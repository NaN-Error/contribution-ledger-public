/** Local static frontend and same-origin API proxy. No npm runtime dependencies. */
import { createServer, request as httpRequest } from 'node:http';
import { createReadStream } from 'node:fs';
import { stat } from 'node:fs/promises';
import { dirname, extname, resolve, sep } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
const mime = { '.html': 'text/html; charset=utf-8', '.js': 'text/javascript; charset=utf-8',
  '.css': 'text/css; charset=utf-8', '.json': 'application/json', '.svg': 'image/svg+xml',
  '.png': 'image/png', '.ico': 'image/x-icon', '.woff2': 'font/woff2' };
const uploadRoute = /^\/api\/v1\/workspaces\/[0-9a-f-]{36}\/projects\/[0-9a-f-]{36}\/work-packages\/[0-9a-f-]{36}\/evidence(?:\/[0-9a-f-]{36}\/revisions)?$/;
const financeUploadRoute = /^\/api\/v1\/workspaces\/[0-9a-f-]{36}\/projects\/[0-9a-f-]{36}\/finance\/periods\/[0-9a-f-]{36}\/documents$/;
const uploadBodyLimit = 4 * Math.ceil((2 * 1024 * 1024) / 3) + 65536;
const securityHeaders = {
  'Content-Security-Policy': "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; font-src 'self'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'",
  'X-Content-Type-Options': 'nosniff', 'Referrer-Policy': 'no-referrer', 'X-Frame-Options': 'DENY',
  'Permissions-Policy': 'camera=(), microphone=(), geolocation=()',
};

function json(response, status, code, message) {
  if (response.headersSent || response.destroyed) return;
  response.writeHead(status, { ...securityHeaders, 'Content-Type': 'application/json', 'Cache-Control': 'no-store' });
  response.end(JSON.stringify({ error: { code, message } }));
}

export function createWebServer({ distDir = resolve(here, 'dist'),
  apiTarget = 'http://127.0.0.1:8000', allowedHosts = ['localhost', '127.0.0.1', '[::1]', 'web'] } = {}) {
  const upstream = new URL(apiTarget);
  if (upstream.protocol !== 'http:' || upstream.username || upstream.password || upstream.pathname !== '/' || upstream.search || upstream.hash) {
    throw new Error('The operator API target must be a plain internal HTTP origin.');
  }
  const root = resolve(distDir);
  const server = createServer(async (request, response) => {
    try {
      const host = request.headers.host ?? '';
      let hostName;
      try { hostName = new URL(`http://${host}`).hostname; } catch { hostName = ''; }
      if (host.includes('@') || !allowedHosts.includes(hostName)) {
        return json(response, 400, 'invalid_host', 'This host is not allowed.');
      }
      // Reject ambiguous/traversal paths before URL normalization can erase them.
      let rawPath;
      try { rawPath = decodeURIComponent((request.url ?? '/').split('?')[0]); }
      catch { return json(response, 400, 'invalid_path', 'Invalid request path.'); }
      if (!rawPath.startsWith('/') || rawPath.startsWith('//') || rawPath.includes('\\')
        || rawPath.includes('\0') || rawPath.split('/').some(part => part === '..' || part === '.')) {
        return json(response, 400, 'invalid_path', 'Invalid request path.');
      }
      const apiRoute = rawPath.startsWith('/api/') || rawPath.startsWith('/health/');
      const allowedMethods = apiRoute ? ['GET', 'HEAD', 'POST', 'PATCH', 'PUT', 'DELETE', 'OPTIONS'] : ['GET', 'HEAD'];
      if (!allowedMethods.includes(request.method)) {
        response.setHeader('Allow', allowedMethods.join(', '));
        return json(response, 405, 'method_not_allowed', 'This method is not allowed for this route.');
      }
      if (rawPath === '/web-health') {
        response.writeHead(200, { ...securityHeaders, 'Content-Type': 'application/json', 'Cache-Control': 'no-store' });
        return response.end(JSON.stringify({ status: 'ok', service: 'contribution-ledger-web' }));
      }
      if (rawPath.startsWith('/api/') || rawPath.startsWith('/health/')) {
        const unsafe = !['GET', 'HEAD', 'OPTIONS'].includes(request.method);
        let body = Buffer.alloc(0);
        if (unsafe) {
          const encoding = request.headers['content-encoding'];
          if (encoding && encoding !== 'identity') return json(response, 415, 'unsupported_encoding', 'Compressed request bodies are not accepted.');
          const limit = request.method === 'POST' && (uploadRoute.test(rawPath) || financeUploadRoute.test(rawPath)) ? uploadBodyLimit : 65536;
          const declared = request.headers['content-length'];
          if (declared && (!/^\d+$/.test(declared) || Number(declared) > limit)) {
            request.resume();
            return json(response, 413, 'request_too_large', 'This request exceeds the allowed size.');
          }
          // Bounded buffering; no secret request body is logged or stored.
          const buffered = await new Promise((resolveBody, rejectBody) => {
            let chunks = [], size = 0, oversized = false;
            request.on('data', chunk => {
              size += chunk.length;
              if (size > limit) { oversized = true; chunks = []; resolveBody(null); }
              else if (!oversized) chunks.push(chunk);
            });
            request.on('end', () => resolveBody(oversized ? null : Buffer.concat(chunks)));
            request.on('error', rejectBody); request.on('aborted', () => rejectBody(new Error('aborted')));
          });
          if (buffered === null) return json(response, 413, 'request_too_large', 'This request exceeds the allowed size.');
          body = buffered;
        }
        // Do not trust browser-supplied forwarding or authorization headers.
        const forwarded = { host, accept: 'application/json' };
        for (const name of ['cookie', 'origin', 'x-csrf-token', 'content-type', 'x-request-id', 'sec-fetch-site']) {
          if (request.headers[name]) forwarded[name] = request.headers[name];
        }
        if (unsafe) forwarded['content-length'] = String(body.length);
        const proxy = httpRequest({ hostname: upstream.hostname, port: upstream.port || 80,
          method: request.method, path: request.url, headers: forwarded,
          timeout: rawPath === '/api/v1/github/callback' && request.method === 'POST' ? 90000 : 8000 }, incoming => {
          const headers = { ...securityHeaders, 'Content-Type': incoming.headers['content-type'] || 'application/json', 'Cache-Control': 'no-store' };
          if (incoming.headers['x-request-id']) headers['X-Request-ID'] = incoming.headers['x-request-id'];
          if (incoming.headers['set-cookie']) headers['Set-Cookie'] = incoming.headers['set-cookie'];
          if (incoming.headers['x-content-sha256']) headers['X-Content-SHA256'] = incoming.headers['x-content-sha256'];
          if (incoming.headers['retry-after']) headers['Retry-After'] = incoming.headers['retry-after'];
          if (incoming.headers['content-disposition']) headers['Content-Disposition'] = incoming.headers['content-disposition'];
          // Only stricter sandbox policy for artifact responses, never relax the static app CSP.
          if (/\/evidence\/.+\/(image|download)$/.test(rawPath) || /\/finance\/.+\/(download|export)$/.test(rawPath)) {
            headers['Content-Security-Policy'] = "default-src 'none'; sandbox; frame-ancestors 'none'";
            headers['Vary'] = 'Cookie';
          }
          response.writeHead(incoming.statusCode || 502, headers);
          incoming.on('error', () => response.destroy());
          incoming.pipe(response);
        });
        proxy.on('timeout', () => proxy.destroy(new Error('timeout')));
        proxy.on('error', () => json(response, 502, 'api_unavailable', 'The local API is unavailable.'));
        response.on('close', () => proxy.destroy());
        proxy.end(body);
        return;
      }
      if (rawPath.split('/').some(part => part.startsWith('.'))) {
        return json(response, 404, 'not_found', 'This file is not available.');
      }
      // Only this explicit OAuth return path serves the SPA; never echo its query.
      const relative = rawPath === '/' || rawPath === '/github/callback' ? 'index.html' : rawPath.slice(1);
      const filename = resolve(root, relative);
      if (!filename.startsWith(root + sep)) return json(response, 404, 'not_found', 'This file is not available.');
      let info;
      try { info = await stat(filename); } catch { return json(response, 404, 'not_found', 'This file is not available.'); }
      if (!info.isFile()) return json(response, 404, 'not_found', 'This file is not available.');
      response.writeHead(200, { ...securityHeaders, 'Content-Type': mime[extname(filename)] || 'application/octet-stream',
        'Content-Length': info.size, 'Cache-Control': rawPath.startsWith('/assets/') ? 'public, max-age=31536000, immutable' : 'no-store' });
      if (request.method === 'HEAD') return response.end();
      const stream = createReadStream(filename);
      stream.on('error', () => response.destroy());
      response.on('close', () => stream.destroy());
      stream.pipe(response);
    } catch {
      json(response, 500, 'web_error', 'The web request could not be completed.');
    }
  });
  server.requestTimeout = 15000;
  server.headersTimeout = 10000;
  server.keepAliveTimeout = 5000;
  return server;
}

if (process.argv[1] && import.meta.url === pathToFileURL(resolve(process.argv[1])).href) {
  const port = Number(process.env.CL_WEB_INTERNAL_PORT ?? '5173');
  if (!Number.isInteger(port) || port < 1 || port > 65535) throw new Error('Invalid local web port.');
  const allowedHosts = process.env.CL_WEB_ALLOWED_HOSTS ? JSON.parse(process.env.CL_WEB_ALLOWED_HOSTS) : ['localhost','127.0.0.1','[::1]'];
  if (!Array.isArray(allowedHosts) || !allowedHosts.length || allowedHosts.some(host => typeof host !== 'string' || !host || host.includes('*') || /[\s/\\]/.test(host))) throw new Error('Invalid explicit web hosts.');
  const server = createWebServer({ apiTarget: process.env.CL_API_TARGET ?? 'http://127.0.0.1:8000', allowedHosts });
  server.listen(port, process.env.CL_BIND_HOST ?? '127.0.0.1', () => console.log(`Local web service listening on port ${port}.`));
  for (const signal of ['SIGTERM', 'SIGINT']) process.on(signal, () => {
    server.close(() => process.exit(0));
    setTimeout(() => process.exit(1), 9000).unref();
  });
}
