const {test} = require('node:test');
const assert = require('node:assert/strict');
const http = require('node:http');
const {createGateway} = require('./gateway.cjs');
const random = () => require('node:crypto').randomBytes(32).toString('base64url');

test('gateway starts with its production exchange implementation', () => {
  const server = createGateway({client:'tgsecrets',origin:'http://127.0.0.1:7999',upstream:'http://127.0.0.1:8000',key:'ab'.repeat(32)});
  server.close();
});

test('gateway blocks data, validates browser state and identity, expires and logs out sessions', async t => {
  let clock = Date.now(), identity = '1082729605', calls = 0;
  const backend = http.createServer((req,res) => { calls++; res.end('private data'); });
  await new Promise(resolve => backend.listen(0,'127.0.0.1',resolve));
  const reservation = http.createServer();
  await new Promise(resolve => reservation.listen(0,'127.0.0.1',resolve));
  const port = reservation.address().port;
  await new Promise(resolve => reservation.close(resolve));
  const config = {client:'tgsecrets', origin:`http://127.0.0.1:${port}`, upstream:`http://127.0.0.1:${backend.address().port}`, key:'ab'.repeat(32)};
  const gateway = createGateway(config, {now:()=>clock, exchange:async()=>({telegram_id:identity})});
  await new Promise(resolve => gateway.listen(port,'127.0.0.1',resolve));
  const base = config.origin;
  const request = (path, options={}) => fetch(base+path, {...options,redirect:'manual'});
  t.after(()=>{gateway.closeAllConnections(); gateway.close(); backend.closeAllConnections(); backend.close();});
  assert.equal((await request('/api/registry')).status,401);
  assert.equal((await request('/docs')).status,200);
  assert.equal((await request('/api/scan',{method:'POST',headers:{origin:'http://evil.test'}})).status,403);
  assert.equal(calls,0);
  const start = await request('/auth/login');
  const state = new URL(start.headers.get('location')).searchParams.get('state');
  const binding = start.headers.get('set-cookie').split(';')[0];
  assert.equal((await request(`/auth/callback?state=${state}&code=${random()}`)).status,401);
  identity = '999';
  assert.equal((await request(`/auth/callback?state=${state}&code=${random()}`,{headers:{cookie:binding}})).status,403);
  identity = '1082729605';
  const login = await request('/auth/login');
  const loginState = new URL(login.headers.get('location')).searchParams.get('state');
  const callback = await request(`/auth/callback?state=${loginState}&code=${random()}`,{headers:{cookie:login.headers.get('set-cookie').split(';')[0]}});
  assert.equal(callback.status,302);
  const session = callback.headers.getSetCookie()[0].split(';')[0];
  assert.match(callback.headers.getSetCookie()[0],/HttpOnly; SameSite=Lax/);
  assert.equal(await (await request('/api/registry',{headers:{cookie:session}})).text(),'private data');
  assert.equal((await request(`/auth/callback?state=${loginState}&code=${random()}`,{headers:{cookie:binding}})).status,401);
  clock += 3600001;
  assert.equal((await request('/api/registry',{headers:{cookie:session}})).status,401);
  assert.equal((await request('/auth/logout',{method:'POST',headers:{origin:base,cookie:session}})).status,302);
});
