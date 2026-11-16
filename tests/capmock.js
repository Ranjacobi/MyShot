window.__ln = { scheduled: [], cancels: 0, listeners: {}, channels: [], actionTypes: null, perm: window.__PERM || 'granted', exact: 'denied', requested: 0 };
window.__app = { listeners: {}, exited: 0 }; window.__fs = []; window.__share = []; window.__bars = [];
const __LN = {
  createChannel: async o => { __ln.channels.push(o.id); },
  registerActionTypes: async o => { __ln.actionTypes = o.types.map(t => t.id + ':' + t.actions.map(a => a.id).join('/')); },
  addListener: async (name, cb) => { __ln.listeners[name] = cb; return { remove() {} }; },
  checkPermissions: async () => ({ display: __ln.perm }),
  requestPermissions: async () => { __ln.requested++; __ln.perm = 'granted'; return { display: 'granted' }; },
  checkExactNotificationSetting: async () => ({ exact_alarm: __ln.exact }),
  changeExactNotificationSetting: async () => { __ln.exact = 'granted'; return { exact_alarm: 'granted' }; },
  getPending: async () => ({ notifications: __ln.scheduled.map(n => ({ id: n.id })) }),
  cancel: async o => { const ids = new Set(o.notifications.map(n => n.id)); __ln.cancels++; __ln.scheduled = __ln.scheduled.filter(n => !ids.has(n.id)); },
  schedule: async o => { const ids = new Set(); for (const n of o.notifications) { if (ids.has(n.id)) throw new Error('duplicate id ' + n.id); ids.add(n.id); if (!Number.isInteger(n.id) || n.id > 2147483647) throw new Error('bad id'); } __ln.scheduled.push(...o.notifications.map(n => ({ id: n.id, title: n.title, body: n.body, at: new Date(n.schedule.at).toISOString(), ch: n.channelId, action: n.actionTypeId || '', kind: (n.extra || {}).kind, extra: n.extra }))); return { notifications: o.notifications.map(n => ({ id: n.id })) }; },
};
window.Capacitor = { isNativePlatform: () => true, getPlatform: () => 'android', Plugins: {
  LocalNotifications: __LN,
  App: { addListener: async (n, cb) => { __app.listeners[n] = cb; return { remove() {} }; }, exitApp: async () => { __app.exited++; } },
  SystemBars: { setStyle: async o => { __bars.push(o.style); } },
  Filesystem: { writeFile: async o => { __fs.push({ path: o.path, len: o.data.length, dir: o.directory }); return { uri: 'file:///data/cache/' + o.path }; } },
  Share: { share: async o => { __share.push({ title: o.title, files: o.files }); return {}; } },
} };
