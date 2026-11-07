'use strict';
const http = require('node:http');
const crypto = require('node:crypto');
const fs = require('node:fs');
const ID = '1082729605';
const random = () => crypto.randomBytes(32).toString('base64url');
const hash = value => crypto.createHash('sha256').update(value).digest('base64url');
const valid = value => typeof value === 'string' && /^[A-Za-z0-9_-]{43}$/.test(value);

function createGateway(config, {exchange, now = Date.now} = {}) {
  const {client, origin, upstream, key} = config;
  const authority = 'https://babysharks.fyi/api/private-apps/' + client;
  const cookieName = `${client.replace(/-/g, '_')}_session`;
  const flowName = `${cookieName}_flow`;
  const sessions = new Map(), flows = new Map();
  const cookie = (name, value, age) => `${name}=${value}; Path=/; HttpOnly; SameSite=Lax; Max-Age=${age}${origin.startsWith('https:') ? '; Secure' : ''}`;
  function prune() {
    for (const map of [sessions, flows]) for (const [id, item] of map) if (item.expires <= now()) map.delete(id);
  }
  async function defaultExchange(body) {
    const response = await fetch(authority + '/exchange', {method:'POST', headers:{'Content-Type':'application/json', 'x-app-signature':crypto.createHmac('sha256', Buffer.from(key,'hex')).update(body).digest('hex')}, body, signal:AbortSignal.timeout(10000), redirect:'error'});
    if (!response.ok) throw Error('Login exchange rejected');
    return response.json();
  }
  const server = http.createServer(async (req, res) => {
    res.setHeader('Cache-Control', 'no-store');
    res.setHeader('Referrer-Policy', 'no-referrer');
    res.setHeader('X-Content-Type-Options', 'nosniff');
    res.setHeader('X-Frame-Options', 'DENY');
    const reply = (status, message) => { res.writeHead(status, {'Content-Type':'text/plain; charset=utf-8'}); res.end(message); };
    const redirect = location => { res.writeHead(302, {Location:location}); res.end(); };
    try {
      const url = new URL(req.url, origin);
      if (url.pathname === '/api/health' && req.method === 'GET') return reply(200, 'OK');
      if (req.headers.host !== new URL(origin).host) return redirect(origin);
      prune();
      const cookies = Object.fromEntries((req.headers.cookie || '').split(';').map(part => part.trim().split('=')));
      if (!['GET','HEAD'].includes(req.method) && req.headers.origin !== origin) return reply(403, 'Invalid request origin');
      if (url.pathname === '/auth/login' && req.method === 'GET') {
        if (flows.size >= 1000) return reply(429, 'Try again later');
        const state = random(), verifier = random(), binding = random();
        flows.set(state, {verifier, binding, expires:now()+300000});
        res.setHeader('Set-Cookie', cookie(flowName, binding, 300));
        return redirect(`${authority}/authorize?state=${state}&challenge=${hash(verifier)}`);
      }
      if (url.pathname === '/auth/callback' && req.method === 'GET') {
        const state = url.searchParams.get('state'), code = url.searchParams.get('code');
        const flow = flows.get(state);
        if (!valid(state) || !valid(code) || !flow || cookies[flowName] !== flow.binding) return reply(401, 'Login expired or invalid. Start sign-in again.');
        flows.delete(state);
        const identity = await (exchange || defaultExchange)(JSON.stringify({code, state, verifier:flow.verifier}));
        if (String(identity.telegram_id) !== ID) return reply(403, 'Access is restricted to @invidtiv.');
        if (sessions.size >= 1000) return reply(429, 'Try again later');
        const handle = random();
        sessions.set(handle, {expires:now()+3600000});
        res.setHeader('Set-Cookie', [cookie(cookieName, handle, 3600), cookie(flowName, '', 0)]);
        return redirect('/');
      }
      if (url.pathname === '/auth/logout' && req.method === 'POST') {
        sessions.delete(cookies[cookieName]);
        res.setHeader('Set-Cookie', cookie(cookieName, '', 0));
        return redirect('/');
      }
      if (!sessions.has(cookies[cookieName])) {
        if (url.pathname.startsWith('/api/') || !['GET','HEAD'].includes(req.method)) return reply(401, 'Sign in with Telegram at /auth/login');
        res.writeHead(200, {'Content-Type':'text/html; charset=utf-8', 'Content-Security-Policy':"default-src 'none'; style-src 'unsafe-inline'; frame-ancestors 'none'"});
        return res.end('<!doctype html><meta name="viewport" content="width=device-width"><title>Sign in</title><style>body{font:18px system-ui;background:#111827;color:#fff;max-width:480px;margin:15vh auto;padding:24px}a{display:inline-block;background:#2481cc;color:white;padding:14px 20px;border-radius:8px;text-decoration:none}</style><h1>Sign in with Telegram</h1><p>Access is restricted to @invidtiv.</p><a href="/auth/login">Continue with Bshome</a>');
      }
      const target = new URL(upstream);
      const headers = {...req.headers, host:target.host};
      // Authentication belongs to this gateway; never forward credentials or spoofed identities.
      for (const name of Object.keys(headers)) if (name === 'cookie' || name === 'authorization' || name.startsWith('x-forwarded-') || name.startsWith('x-auth-')) delete headers[name];
      const proxy = http.request({hostname:target.hostname, port:target.port, path:req.url, method:req.method, headers}, response => {
        const responseHeaders = {...response.headers, 'cache-control':'no-store'};
        delete responseHeaders['set-cookie'];
        res.writeHead(response.statusCode, responseHeaders);
        response.pipe(res);
      });
      proxy.setTimeout(300000, () => proxy.destroy());
      proxy.on('error', () => { if (!res.headersSent) reply(502, 'Application unavailable'); else res.destroy(); });
      req.on('aborted', () => proxy.destroy());
      req.pipe(proxy);
    } catch { if (!res.headersSent) reply(503, 'Sign-in unavailable. Please try again.'); else res.destroy(); }
  });
  return server;
}
if (require.main === module) {
  const config = JSON.parse(fs.readFileSync(process.env.AUTH_CONFIG_FILE, 'utf8'));
  createGateway(config).listen(8080, '0.0.0.0');
}
module.exports = {createGateway};
