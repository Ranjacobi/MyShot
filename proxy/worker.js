// MyShot AI: a small server for "AI included" in MyShot Plus.
// It holds your Gemini key, checks with RevenueCat whether the user has Plus,
// and counts a monthly quota per user (free: FREE_LIMIT, Plus: PLUS_LIMIT).
// The app sends a Gemini-style request body and its anonymous RevenueCat user id.

const CORS = { 'access-control-allow-origin': '*', 'access-control-allow-methods': 'POST, OPTIONS', 'access-control-allow-headers': 'content-type, x-myshot-user', 'access-control-expose-headers': 'x-myshot-remaining, x-myshot-plus' };
const json = (obj, status = 200, extra = {}) => new Response(JSON.stringify(obj), { status, headers: { 'content-type': 'application/json', ...CORS, ...extra } });

async function hasPlus(env, user) {
  const cacheKey = `p:${user}`;
  const cached = await env.QUOTA.get(cacheKey);
  if (cached !== null) return cached === '1';
  let ok = false;
  try {
    const r = await fetch(`https://api.revenuecat.com/v1/subscribers/${encodeURIComponent(user)}`, { headers: { authorization: `Bearer ${env.RC_SECRET}` } });
    if (r.ok) {
      const d = await r.json();
      const e = d && d.subscriber && d.subscriber.entitlements && d.subscriber.entitlements[env.ENTITLEMENT || 'plus'];
      ok = !!(e && (!e.expires_date || Date.parse(e.expires_date) > Date.now()));
    }
  } catch (e) { ok = false; }
  await env.QUOTA.put(cacheKey, ok ? '1' : '0', { expirationTtl: 600 });   // re-check every 10 minutes
  return ok;
}

export default {
  async fetch(req, env) {
    const url = new URL(req.url);
    if (req.method === 'OPTIONS') return new Response(null, { status: 204, headers: CORS });
    if (url.pathname !== '/v1/generate' || req.method !== 'POST') return json({ error: 'not_found' }, 404);
    const user = (req.headers.get('x-myshot-user') || '').trim();
    if (!/^[\w$:.\-]{6,200}$/.test(user)) return json({ error: 'no_user' }, 401);
    const body = await req.text();
    if (body.length > 8_000_000) return json({ error: 'too_large' }, 413);

    const plus = await hasPlus(env, user);
    const month = new Date().toISOString().slice(0, 7);
    const quotaKey = `q:${month}:${user}`;
    const used = parseInt(await env.QUOTA.get(quotaKey) || '0', 10);
    const limit = parseInt(plus ? (env.PLUS_LIMIT || '300') : (env.FREE_LIMIT || '5'), 10);
    if (used >= limit) return json({ error: plus ? 'plus_limit' : 'quota', remaining: 0, plus }, 402, { 'x-myshot-remaining': '0', 'x-myshot-plus': plus ? '1' : '0' });

    const model = env.MODEL || 'gemini-3.5-flash-lite';
    const r = await fetch(`https://generativelanguage.googleapis.com/v1beta/models/${encodeURIComponent(model)}:generateContent`, { method: 'POST', headers: { 'content-type': 'application/json', 'x-goog-api-key': env.GEMINI_API_KEY }, body });
    const text = await r.text();
    const count = r.ok ? used + 1 : used;
    if (r.ok) await env.QUOTA.put(quotaKey, String(count), { expirationTtl: 60 * 60 * 24 * 40 });
    return new Response(text, { status: r.status, headers: { 'content-type': 'application/json', ...CORS, 'x-myshot-remaining': String(Math.max(0, limit - count)), 'x-myshot-plus': plus ? '1' : '0' } });
  },
};
