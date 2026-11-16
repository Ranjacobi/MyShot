(() => {
  const KEY = '__mockdb';
  const SLOW = !!window.__MOCK_SLOW;
  let store = {};
  try { store = JSON.parse(localStorage.getItem(KEY) || '{}'); } catch (e) {}
  const persist = () => { try { localStorage.setItem(KEY, JSON.stringify(store)); } catch (e) {} };
  const listeners = {};
  const snap = p => ({ id: p.split('/').pop(), exists: p in store, data: () => (p in store ? Object.freeze(JSON.parse(JSON.stringify(store[p]))) : undefined), metadata: { fromCache: false, hasPendingWrites: false } });
  const fire = p => (listeners[p] || []).forEach(fn => setTimeout(() => fn(snap(p)), 5));
  const doc = p => {
    const n = p.split('/').length;
    if (n % 2) throw new TypeError('document path needs an even number of segments: ' + p);
    if (p.split('/').some(s => !/^[A-Za-z0-9_\-.~:@+]+$/.test(s))) throw new TypeError('bad segment: ' + p);
    return {
      id: p.split('/').pop(), path: p,
      get: async () => snap(p),
      set: async data => {
        const size = new TextEncoder().encode(JSON.stringify(data)).length;
        (window.__writes = window.__writes || []).push({ p, size });
        if (size > 262144) throw { code: 'invalid_argument', message: 'over 256 KiB' };
        store[p] = JSON.parse(JSON.stringify(data)); persist(); fire(p);
      },
      update: async data => { if (!(p in store)) throw { code: 'invalid_argument' }; Object.assign(store[p], data); persist(); fire(p); },
      delete: async () => { (window.__deletes = window.__deletes || []).push(p); delete store[p]; persist(); fire(p); },
      onSnapshot: (next, err) => { (listeners[p] = listeners[p] || []).push(next); if (!SLOW) setTimeout(() => next(snap(p)), 30); return () => { listeners[p] = (listeners[p] || []).filter(f => f !== next); }; },
      collection: c => ({ doc: id => doc(p + '/' + c + '/' + id) }),
    };
  };
  const db = Object.freeze({ doc, collection: c => ({ doc: id => doc(c + '/' + id) }) });
  const user = Object.freeze({ id: async () => 'u123', isOwner: async () => true, canEdit: async () => true, can: async () => true });
  const sample = async (input, opts) => ({ text: 'ok', truncated: false });
  sample.json = async (input, opts) => {
    window.__sampleCalls = (window.__sampleCalls || 0) + 1;
    await new Promise(r => setTimeout(r, 150));
    const P = typeof input === 'string' ? input : '';
    if (opts && opts.images) {
      if (!(opts.images[0] instanceof Blob)) throw { code: 'invalid_request', message: 'images not blobs' };
      window.__ocrBlob = { type: opts.images[0].type, size: opts.images[0].size };
      if (P.includes('nutrition facts label')) return { name: 'יוגורט חלבון', serving_g: 150, per100: { kcal: 60, p: 10, c: 4, f: 0.5, fib: null } };
      if (P.includes('plate of food')) return { items: [ { name: 'חזה עוף בגריל', qty: '120 גרם', kcal: 200, p: 36, c: 0, f: 5, fib: 0 }, { name: 'אורז לבן', qty: 'חצי כוס', kcal: 120, p: 2.5, c: 26, f: 0.3, fib: 0.4 }, { name: 'סלט ירקות', qty: 'קערה קטנה', kcal: 45, p: 1.5, c: 7, f: 2, fib: 2.5 } ] };
      return { date: '2026-11-10', amount: 512.4, vendor: 'בית מרקחת בדיקה', category: 'mj' };
    }
    if (P.includes('describes in Hebrew what they ate')) return { items: [ { name: 'ביצים מקושקשות', qty: '2 ביצים', kcal: 180, p: 13, c: 1, f: 13, fib: 0 }, { name: 'לחם מלא', qty: 'פרוסה', kcal: 80, p: 4, c: 14, f: 1, fib: 2.5 } ] };
    window.__mealPrompt = input; window.__mealOpts = opts;
    return { ideas: [ { name: 'יוגורט חלבון עם בננה', desc: 'יוגורט קר עם חצי בננה — קל לבטן ומספק חלבון.', protein: 18 }, { name: 'ביצה קשה וקרקרים', desc: 'מנה קטנה ויבשה שקל לאכול כשיש בחילה.', protein: 8 } ] };
  };
  sample.limits = async () => ({ maxPromptBytes: 262144, images: { maxCount: 4, maxInputBytes: 10000000, mediaTypes: ['image/jpeg', 'image/png', 'image/webp'] } });
  const downloads = Object.freeze({ save: async ({ filename, data }) => {
    window.__saved = { filename, len: typeof data === 'string' ? data.length : data.size, head: typeof data === 'string' ? data.slice(0, 60) : '' };
    if (data instanceof Blob) window.__savedB64 = await new Promise(r => { const fr = new FileReader(); fr.onload = () => r(String(fr.result).split(',')[1]); fr.readAsDataURL(data); });
    return { saved: true }; } });
  const caps = { db, user, sample, downloads };
  window.claude = Object.freeze({ use: name => new Promise(r => setTimeout(() => r(caps[name] || null), 60)) });
})();
