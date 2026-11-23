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


// ---- coupons: each code opens a discount offer you created in Google Play (eligibility: "Developer determined") ----
const normCode = c => String(c || '').trim().toUpperCase().replace(/\s+/g, '');
const validUser = u => /^[\w$:.\-]{6,200}$/.test(u);
async function getCoupon(env, code) { const v = await env.QUOTA.get(`c:${code}`); return v ? JSON.parse(v) : null; }
function couponState(c, now = Date.now()) {
  if (!c) return 'invalid';
  if (!c.active) return 'inactive';
  if (c.expires && Date.parse(c.expires) < now) return 'expired';
  if (c.maxUses && (c.uses || 0) >= c.maxUses) return 'exhausted';
  return 'ok';
}
async function couponRoute(req, env, url) {
  if (req.method !== 'POST') return json({ error: 'method' }, 405);
  const user = (req.headers.get('x-myshot-user') || '').trim();
  if (!validUser(user)) return json({ ok: false, reason: 'no_user' }, 401);
  const body = await req.json().catch(() => ({}));
  const code = normCode(body.code), c = await getCoupon(env, code), st = couponState(c);
  if (st !== 'ok') return json({ ok: false, reason: st });
  const usedKey = `r:${code}:${user}`;
  if (await env.QUOTA.get(usedKey)) return json({ ok: false, reason: 'used' });
  if (url.pathname.endsWith('/check')) return json({ ok: true, offer: c.offer, plan: c.plan || 'any', label: c.label || '' });
  c.uses = (c.uses || 0) + 1;                      // redeem: counted after a successful purchase
  await env.QUOTA.put(`c:${code}`, JSON.stringify(c));
  await env.QUOTA.put(usedKey, new Date().toISOString());
  return json({ ok: true });
}
const isAdmin = (req, env) => !!env.ADMIN_TOKEN && (req.headers.get('authorization') || '') === `Bearer ${env.ADMIN_TOKEN}`;
async function adminRoute(req, env, url) {
  if (!isAdmin(req, env)) return json({ error: 'unauthorized' }, 401);
  if (req.method === 'GET') {
    const out = []; let cursor;
    do { const l = await env.QUOTA.list({ prefix: 'c:', cursor }); for (const k of l.keys) { const v = await env.QUOTA.get(k.name); if (v) { const c = JSON.parse(v); c.state = couponState(c); out.push(c); } } cursor = l.list_complete ? null : l.cursor; } while (cursor);
    out.sort((a, b) => String(b.created || '').localeCompare(String(a.created || '')));
    return json({ coupons: out });
  }
  if (req.method === 'POST') {
    const b = await req.json().catch(() => ({}));
    const code = normCode(b.code);
    if (!/^[A-Z0-9_-]{3,32}$/.test(code)) return json({ error: 'bad_code' }, 400);
    if (!/^[a-z0-9-]{1,40}$/.test(String(b.offer || ''))) return json({ error: 'bad_offer' }, 400);
    const old = (await getCoupon(env, code)) || { created: new Date().toISOString(), uses: 0 };
    const c = { ...old, code, offer: String(b.offer), plan: ['yearly', 'monthly', 'any'].includes(b.plan) ? b.plan : 'any', label: String(b.label || '').slice(0, 80),
      expires: b.expires ? (/^\d{4}-\d{2}-\d{2}$/.test(b.expires) ? `${b.expires}T23:59:59Z` : String(b.expires)) : null,
      maxUses: Math.max(0, parseInt(b.maxUses, 10) || 0), active: b.active !== false, note: String(b.note || '').slice(0, 200), updated: new Date().toISOString() };
    await env.QUOTA.put(`c:${code}`, JSON.stringify(c));
    return json({ coupon: c });
  }
  if (req.method === 'DELETE') { await env.QUOTA.delete(`c:${normCode(decodeURIComponent(url.pathname.split('/').pop()))}`); return json({ ok: true }); }
  return json({ error: 'method' }, 405);
}
const ADMIN_HTML = `<!doctype html><html lang="he" dir="rtl"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>MyShot · קופונים</title>
<style>body{font:15px/1.5 system-ui,Arial,sans-serif;margin:0;background:#f5f6fa;color:#18224F}main{max-width:980px;margin:0 auto;padding:20px}h1{margin:0 0 4px}.muted{color:#5b648a;font-size:13px}
.card{background:#fff;border-radius:14px;padding:16px;margin:14px 0;box-shadow:0 1px 3px rgba(0,0,0,.06)}label{display:block;font-size:13px;margin:8px 0 3px}input,select{font:inherit;padding:8px;border:1px solid #cfd3e3;border-radius:8px;width:100%;box-sizing:border-box}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:10px}button{font:inherit;border:0;border-radius:9px;padding:8px 14px;background:#18224F;color:#fff;cursor:pointer}button.sec{background:#e7e9f3;color:#18224F}button.red{background:#c0392b}
table{width:100%;border-collapse:collapse;font-size:14px}th,td{padding:8px 6px;border-bottom:1px solid #eceef5;text-align:start;vertical-align:top}.tag{display:inline-block;padding:1px 8px;border-radius:99px;font-size:12px;font-weight:600}.ok{background:#dff3e8;color:#1f6b4f}.off{background:#eee;color:#555}.bad{background:#fde3e0;color:#a23b2c}td .row{display:flex;gap:6px;flex-wrap:wrap}</style></head>
<body><main><h1>קופונים של MyShot Plus</h1><p class="muted">כל קוד פותח הצעת הנחה שיצרת ב-Google Play (זכאות: Developer determined, עם התגית rc-ignore-offer). כדי לשנות את אחוז ההנחה של קוד, מחליפים לו את ההצעה.</p>
<div class="card"><label>סיסמת ניהול</label><div style="display:flex;gap:8px"><input id="tok" type="password" autocomplete="off"><button onclick="saveTok()">כניסה</button></div></div>
<div class="card"><h3 id="ftitle" style="margin:0">קופון חדש</h3><div class="grid">
<div><label>קוד</label><input id="code" placeholder="SPRING20" style="text-transform:uppercase"></div>
<div><label>מזהה ההצעה ב-Play</label><input id="offer" placeholder="c20"></div>
<div><label>מסלול</label><select id="plan"><option value="yearly">שנתי</option><option value="monthly">חודשי</option><option value="any">כל מסלול</option></select></div>
<div><label>מה המשתמש רואה</label><input id="label" placeholder="20% הנחה בשנה הראשונה"></div>
<div><label>בתוקף עד (כולל)</label><input id="expires" type="date"></div>
<div><label>מקסימום שימושים (0 = ללא הגבלה)</label><input id="maxUses" type="number" min="0" value="0"></div>
<div><label>הערה לעצמך</label><input id="note"></div>
<div><label>פעיל</label><select id="active"><option value="1">כן</option><option value="0">לא</option></select></div></div>
<div style="display:flex;gap:8px;margin-top:12px"><button onclick="save()">שמירה</button><button class="sec" onclick="resetForm()">ניקוי</button></div><p id="msg" class="muted"></p></div>
<div class="card"><table><thead><tr><th>קוד</th><th>מה המשתמש רואה</th><th>הצעה</th><th>מסלול</th><th>תוקף</th><th>שימושים</th><th>מצב</th><th></th></tr></thead><tbody id="list"><tr><td colspan="8" class="muted">היכנסו עם סיסמת הניהול.</td></tr></tbody></table></div></main>
<script>
const $ = id => document.getElementById(id); let all = [];
const H = () => ({ 'content-type': 'application/json', authorization: 'Bearer ' + (localStorage.getItem('myshot-admin') || '') });
const ST = { ok: ['פעיל', 'ok'], inactive: ['כבוי', 'off'], expired: ['פג תוקף', 'bad'], exhausted: ['נוצל', 'bad'] };
const PL = { yearly: 'שנתי', monthly: 'חודשי', any: 'כל מסלול' };
const esc = s => String(s == null ? '' : s).replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' })[c]);
function saveTok() { localStorage.setItem('myshot-admin', $('tok').value.trim()); load(); }
async function load() {
  const r = await fetch('/admin/api/coupons', { headers: H() });
  if (r.status === 401) { $('list').innerHTML = '<tr><td colspan="8" class="muted">סיסמה שגויה.</td></tr>'; return; }
  all = (await r.json()).coupons || [];
  $('list').innerHTML = all.length ? all.map(c => '<tr><td><b>' + esc(c.code) + '</b>' + (c.note ? '<div class="muted">' + esc(c.note) + '</div>' : '') + '</td><td>' + esc(c.label) + '</td><td>' + esc(c.offer) + '</td><td>' + esc(PL[c.plan] || c.plan) + '</td><td>' + (c.expires ? esc(c.expires.slice(0, 10)) : '—') + '</td><td>' + (c.uses || 0) + (c.maxUses ? ' / ' + c.maxUses : '') + '</td><td><span class="tag ' + ST[c.state][1] + '">' + ST[c.state][0] + '</span></td><td><div class="row"><button class="sec" onclick="edit(\\'' + c.code + '\\')">עריכה</button><button class="sec" onclick="toggle(\\'' + c.code + '\\')">' + (c.active ? 'כיבוי' : 'הפעלה') + '</button><button class="red" onclick="del(\\'' + c.code + '\\')">מחיקה</button></div></td></tr>').join('') : '<tr><td colspan="8" class="muted">אין עדיין קופונים.</td></tr>';
}
function body() { return { code: $('code').value, offer: $('offer').value.trim(), plan: $('plan').value, label: $('label').value, expires: $('expires').value || null, maxUses: $('maxUses').value, note: $('note').value, active: $('active').value === '1' }; }
async function post(b) { const r = await fetch('/admin/api/coupons', { method: 'POST', headers: H(), body: JSON.stringify(b) }); const d = await r.json(); $('msg').textContent = r.ok ? 'נשמר ✓' : ({ bad_code: 'קוד לא תקין: 3 עד 32 אותיות לטיניות, ספרות, - או _', bad_offer: 'מזהה הצעה לא תקין', unauthorized: 'סיסמה שגויה' })[d.error] || 'שגיאה'; if (r.ok) { resetForm(); load(); } }
function save() { post(body()); }
function edit(code) { const c = all.find(x => x.code === code); if (!c) return; $('ftitle').textContent = 'עריכת ' + code; $('code').value = c.code; $('offer').value = c.offer; $('plan').value = c.plan; $('label').value = c.label || ''; $('expires').value = c.expires ? c.expires.slice(0, 10) : ''; $('maxUses').value = c.maxUses || 0; $('note').value = c.note || ''; $('active').value = c.active ? '1' : '0'; window.scrollTo(0, 0); }
function toggle(code) { const c = all.find(x => x.code === code); if (c) post({ ...c, expires: c.expires ? c.expires.slice(0, 10) : null, active: !c.active }); }
async function del(code) { if (!confirm('למחוק את ' + code + '? מי שכבר קנה איתו שומר את המחיר שקיבל.')) return; await fetch('/admin/api/coupons/' + encodeURIComponent(code), { method: 'DELETE', headers: H() }); load(); }
function resetForm() { $('ftitle').textContent = 'קופון חדש'; ['code', 'offer', 'label', 'expires', 'note'].forEach(k => $(k).value = ''); $('maxUses').value = 0; $('plan').value = 'yearly'; $('active').value = '1'; }
$('tok').value = localStorage.getItem('myshot-admin') || ''; if ($('tok').value) load();
</script></body></html>`;

export default {
  async fetch(req, env) {
    const url = new URL(req.url);
    if (req.method === 'OPTIONS') return new Response(null, { status: 204, headers: CORS });
    if (url.pathname === '/v1/coupon/check' || url.pathname === '/v1/coupon/redeem') return couponRoute(req, env, url);
    if (url.pathname === '/admin') return new Response(ADMIN_HTML, { headers: { 'content-type': 'text/html; charset=utf-8', 'cache-control': 'no-store' } });
    if (url.pathname.startsWith('/admin/api/coupons')) return adminRoute(req, env, url);
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
