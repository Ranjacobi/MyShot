#!/usr/bin/env python3
"""MyShot automated checks.

Runs www/index.html in headless Chromium with the Android plugins and the AI/Google
services mocked, and checks the main flows. Exit code 0 means everything passed;
any failure exits with 1, so the APK build in GitHub Actions does not run.

Local run:  python3 -m pip install playwright && python3 -m playwright install chromium
            python3 tests/run_tests.py
"""
import asyncio, base64, json, sys, tempfile, time, traceback
from pathlib import Path
from playwright.async_api import async_playwright

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
from helpers import serve, new_page  # noqa: E402
from seed import SEED  # noqa: E402

PORT = 8790
URL = f"http://localhost:{PORT}/index.html"
MOCK = (HERE / "mock_storage.js").read_text(encoding="utf-8")
CAP = (HERE / "capmock.js").read_text(encoding="utf-8")
DB = {f"data/users/u123/{k}": v for k, v in SEED.items()}
PRE = "if (!localStorage.getItem('__mockdb')) localStorage.setItem('__mockdb', " + json.dumps(json.dumps(DB, ensure_ascii=False)) + ");\n"
MEAL_B64 = base64.b64encode((HERE / "assets" / "meal.jpg").read_bytes()).decode()
RECEIPT = str(HERE / "assets" / "receipt.jpg")
HTTP = """window.__http = [];
window.Capacitor.Plugins.CapacitorHttp = { request: async o => { __http.push({ m: o.method, u: o.url, model: o.data && o.data.model }); const body = o.method === 'GET' || o.method === 'DELETE' ? undefined : (typeof o.data === 'string' ? o.data : JSON.stringify(o.data)); const r = await fetch(o.url, { method: o.method, headers: o.headers, body }); const t = await r.text(); let data = null; try { data = t ? JSON.parse(t) : null; } catch (e) { data = t; } return { status: r.status, data, headers: {} }; } };"""
CAMERA = "window.__cam = []; window.Capacitor.Plugins.Camera = { getPhoto: async o => { __cam.push(o.source); return { base64String: " + json.dumps(MEAL_B64) + ", format: 'jpeg' }; } };"


def key(provider, k="test-key-1234567890abcdef"):
    return "if (!localStorage.getItem('__k')) { localStorage.setItem('mj-ai', JSON.stringify({provider:'%s', keys:{%s:'%s'}, models:{}})); localStorage.setItem('__k','1'); }\n" % (provider, provider, k)


def gem_text(obj):
    return json.dumps({"candidates": [{"content": {"parts": [{"text": json.dumps(obj, ensure_ascii=False)}]}}]}, ensure_ascii=False)


def check(cond, msg):
    if not cond:
        raise AssertionError(msg)


async def tick(page, n=6, ms=300):
    for _ in range(n):
        await page.clock.run_for(ms)


async def settle(page, real=0.4, n=4):
    """Let real async work (crypto, fetch) finish, then advance the fake clock."""
    await asyncio.sleep(real)
    await tick(page, n)


async def open_app(b, extra="", w=360, routes=(), pre=""):
    """pre runs before the storage mock loads (to change the sample data); extra runs after the plugin mocks."""
    ctx, page, errs = await new_page(b, w=w)
    await ctx.add_init_script(PRE + pre + MOCK + CAP + extra)
    for pattern, handler in routes:
        await page.route(pattern, handler)
    await page.goto(URL, wait_until="domcontentloaded")
    await page.clock.run_for(1500)
    await tick(page)
    return ctx, page, errs


async def open_reminders(page):
    await page.click('.tab[data-tab="more"]'); await tick(page, 2)
    await page.click('.row[data-k="reminders"]'); await tick(page, 2)


async def mockdb(page, doc):
    raw = await page.evaluate("localStorage.getItem('__mockdb')")
    v = json.loads(raw).get(f"data/users/u123/{doc}")
    return json.loads(v) if isinstance(v, str) else v


TESTS = []


def test(fn):
    TESTS.append(fn)
    return fn


# ---------------------------------------------------------------- tests

@test
async def versions_in_sync(b):
    html = (ROOT / "www" / "index.html").read_text(encoding="utf-8")
    pkg = json.loads((ROOT / "package.json").read_text())
    v = html.split("const APP_VERSION = '")[1].split("'")[0]
    check(v == pkg["version"], f"APP_VERSION {v} != package.json {pkg['version']}")
    check(f"['{v}'," in html, "the changelog has no entry for the current version")
    cfg = json.loads((ROOT / "capacitor.config.json").read_text())
    check(cfg.get("plugins", {}).get("SocialLogin", {}).get("providers", {}).get("facebook") is False, "Facebook SDK must stay disabled")


@test
async def boots_without_errors(b):
    ctx, page, errs = await open_app(b)
    try:
        check(await page.locator('.tab[data-tab="home"]').count() == 1, "tab bar missing")
        check(await page.locator('#app .hero, #app .dial, #app svg').count() > 0, "home screen did not render")
        check(not errs, f"JS errors: {errs}")
    finally:
        await ctx.close()


@test
async def reminders_are_discreet_by_default(b):
    ctx, page, errs = await open_app(b)
    try:
        dose = await page.evaluate("__ln.scheduled.filter(n => n.kind === 'dose')")
        check(dose, "no dose reminder scheduled")
        check(dose[0]["title"] == "MyShot" and "מונג" not in dose[0]["body"], f"lock-screen text not discreet: {dose[0]['title']} / {dose[0]['body']}")
        check(dose[0]["ch"] == "meds2", f"dose reminder on channel {dose[0]['ch']}, expected the private meds2")
        await open_reminders(page)
        await page.click('.sw[data-k="discreet"]'); await tick(page, 4)
        dose = await page.evaluate("__ln.scheduled.filter(n => n.kind === 'dose')")
        check(dose and dose[0]["title"] != "MyShot", "turning discreet mode off did not bring the details back")
        check(not errs, f"JS errors: {errs}")
    finally:
        await ctx.close()


@test
async def dose_logged_from_notification(b):
    # The sample data has an injection yesterday; drop it so a dose is due today.
    due = "if (!localStorage.getItem('__d')) { const db = JSON.parse(localStorage.getItem('__mockdb')), k = 'data/users/u123/injections'; let v = db[k]; const str = typeof v === 'string'; if (str) v = JSON.parse(v); v.items = v.items.filter(x => x.at < '2026-11-12'); db[k] = str ? JSON.stringify(v) : v; localStorage.setItem('__mockdb', JSON.stringify(db)); localStorage.setItem('__d', '1'); }\n"
    ctx, page, errs = await open_app(b, pre=due)
    try:
        before = len((await mockdb(page, "injections"))["items"])
        taken = "__ln.listeners.localNotificationActionPerformed({actionId:'taken', notification:{extra:{kind:'dose'}}})"
        await page.evaluate(taken); await tick(page, 10)
        after = len((await mockdb(page, "injections"))["items"])
        check(after == before + 1, f"injections {before} -> {after}, expected one more")
        await page.evaluate(taken); await tick(page, 10)
        check(len((await mockdb(page, "injections"))["items"]) == after, "a second tap logged a duplicate dose")
        check("כבר תועדה" in await page.inner_text("#toast"), "no warning on the duplicate tap")
        check(not errs, f"JS errors: {errs}")
    finally:
        await ctx.close()


@test
async def back_button_closes_then_exits(b):
    ctx, page, errs = await open_app(b)
    try:
        await page.click('[data-act="settings"]'); await tick(page, 2)
        check(await page.locator('#sheet.open').count() == 1, "settings did not open")
        await page.evaluate("__app.listeners.backButton({canGoBack:false})"); await tick(page, 2)
        check(await page.locator('#sheet.open').count() == 0, "back did not close the sheet")
        await page.evaluate("__app.listeners.backButton({canGoBack:false})"); await tick(page, 2)
        check(await page.evaluate("__app.exited") == 1, "back on the home screen did not exit")
    finally:
        await ctx.close()


@test
async def backup_round_trip(b):
    grab = "window.__file = null; const __w = window.Capacitor.Plugins.Filesystem.writeFile; window.Capacitor.Plugins.Filesystem.writeFile = async o => { window.__file = o.data; return __w(o); };"
    ctx, page, errs = await open_app(b, grab)
    try:
        await page.click('[data-act="settings"]'); await tick(page, 2)
        await page.click('[data-act="backup-drive"]'); await settle(page)
        data = await page.evaluate("window.__file")
        check(data, "the backup file was not written")
        if not data.lstrip().startswith("{"):
            data = base64.b64decode(data).decode("utf-8")
        doc = json.loads(data)
        check(doc.get("app") == "mounjaro-journal" and "core" in doc["docs"] and "train" in doc["docs"], "backup is missing documents")
        check(await page.evaluate("__share.length") == 1, "the share sheet did not open")
        await page.keyboard.press("Escape"); await tick(page, 2)
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as f:
            f.write(data)
        await page.click('[data-act="settings"]'); await tick(page, 2)
        await page.set_input_files('#sheet input[data-file="import"]', f.name); await settle(page)
        await page.click('.confirm [data-c="1"]'); await settle(page, 0.5, 6)
        check("הגיבוי יובא" in await page.inner_text("#toast"), "restore did not finish")
        check(not errs, f"JS errors: {errs}")
    finally:
        await ctx.close()


@test
async def chatgpt_reads_a_receipt(b):
    async def openai(route):
        if route.request.method == "GET":
            return await route.fulfill(status=200, content_type="application/json", body=json.dumps({"data": [{"id": "gpt-6-luna", "created": 1758499200}, {"id": "gpt-6-sol", "created": 1758500000}]}))
        await route.fulfill(status=200, content_type="application/json", body=json.dumps({"choices": [{"message": {"content": json.dumps({"date": "2026-11-12", "amount": 77.5, "vendor": "סופר-פארם", "category": "supps"}, ensure_ascii=False)}}]}, ensure_ascii=False))
    ctx, page, errs = await open_app(b, key("openai") + HTTP, routes=[("https://api.openai.com/**", openai)])
    try:
        await page.click('.tab[data-tab="more"]'); await tick(page, 2)
        if await page.locator('.row[data-act="more-go"][data-k="receipts"]').count():
            await page.click('.row[data-act="more-go"][data-k="receipts"]'); await tick(page, 2)
        await page.click('[data-act="add-receipt"]'); await tick(page, 2)
        await page.set_input_files('.sheet input[data-file="receipt"]:not([capture])', RECEIPT); await settle(page, 0.6, 10)
        check(await page.input_value("#f-amt") == "77.5", "the amount was not filled from the receipt")
        models = await page.evaluate("__http.filter(c => c.m === 'POST').map(c => c.model)")
        check(models and models[-1] == "gpt-6-luna", f"expected the cheap image model, got {models}")
        check(not errs, f"JS errors: {errs}")
    finally:
        await ctx.close()


@test
async def gemini_moves_to_the_next_model_on_a_limit(b):
    calls = []

    async def gemini(route):
        if route.request.method == "GET":
            return await route.fulfill(status=200, content_type="application/json", body=json.dumps({"models": [
                {"name": "models/gemini-3.5-flash-lite", "displayName": "Gemini 3.5 Flash-Lite", "supportedGenerationMethods": ["generateContent"]},
                {"name": "models/gemini-3.1-flash-lite", "displayName": "Gemini 3.1 Flash-Lite", "supportedGenerationMethods": ["generateContent"]},
                {"name": "models/gemini-3.8-flash", "displayName": "Gemini 3.8 Flash", "supportedGenerationMethods": ["generateContent"]},
                {"name": "models/gemini-embedding-001", "displayName": "Embedding", "supportedGenerationMethods": ["embedContent"]}]}))
        model = route.request.url.split("/models/")[1].split(":")[0]
        calls.append(model)
        if len(calls) == 1:
            return await route.fulfill(status=429, content_type="application/json", body=json.dumps({"error": {"code": 429, "message": "Resource has been exhausted (e.g. check quota).", "status": "RESOURCE_EXHAUSTED"}}))
        await route.fulfill(status=200, content_type="application/json", body=gem_text({"date": "2026-11-12", "amount": 129.9, "vendor": "סופר-פארם", "category": "supps"}))
    ctx, page, errs = await open_app(b, key("gemini") + HTTP, routes=[("https://generativelanguage.googleapis.com/**", gemini)])
    try:
        await page.click('[data-act="settings"]'); await settle(page, 0.3, 3)
        chips = await page.evaluate("Array.from(document.querySelectorAll('#f-aiblock [data-pick=aiModel]')).map(b => b.dataset.val)")
        check(chips == ["", "gemini-3.5-flash-lite", "gemini-3.1-flash-lite"], f"model list not filtered to the cheap image models: {chips}")
        await page.keyboard.press("Escape"); await tick(page, 2)
        await page.click('.tab[data-tab="more"]'); await tick(page, 2)
        if await page.locator('.row[data-act="more-go"][data-k="receipts"]').count():
            await page.click('.row[data-act="more-go"][data-k="receipts"]'); await tick(page, 2)
        await page.click('[data-act="add-receipt"]'); await tick(page, 2)
        await page.set_input_files('.sheet input[data-file="receipt"]:not([capture])', RECEIPT); await settle(page, 0.6, 10)
        check(calls[:2] == ["gemini-3.5-flash-lite", "gemini-3.1-flash-lite"], f"no fallback to the next model: {calls}")
        check(await page.input_value("#f-amt") == "129.9", "the amount was not filled after the fallback")
        check(not [e for e in errs if "429" not in e], f"JS errors: {errs}")
    finally:
        await ctx.close()


@test
async def meal_photo_and_retake(b):
    n = {"meal": 0}
    meals = [{"items": [{"name": "אורז לבן", "qty": "כוס", "kcal": 205, "p": 4.3, "c": 45, "f": 0.4, "fib": 0.6}]},
             {"items": [{"name": "שקשוקה", "qty": "מנה", "kcal": 300, "p": 18, "c": 12, "f": 20, "fib": 3}]}]

    async def gemini(route):
        if route.request.method == "GET":
            return await route.fulfill(status=200, content_type="application/json", body=json.dumps({"models": []}))
        i = min(n["meal"], 1); n["meal"] += 1
        await route.fulfill(status=200, content_type="application/json", body=gem_text(meals[i]))
    ctx, page, errs = await open_app(b, key("gemini") + HTTP + CAMERA, routes=[("https://generativelanguage.googleapis.com/**", gemini)])
    try:
        await page.click('[data-act="quick"]'); await tick(page, 2)
        await page.click('.qa [data-act="log-meal"][data-mode="photo"]'); await settle(page, 0.5, 10)
        names = await page.evaluate("Array.from(document.querySelectorAll('#sheet .item-name, #sheet .it-name, #sheet [data-act=\"it-edit\"] .row-title')).map(e => e.textContent.trim())")
        body = await page.inner_text("#sheet .sheet-body")
        check("אורז לבן" in body, "the photographed meal was not recognised")
        check((await page.evaluate("__cam"))[0] == "CAMERA", "the native camera was not used")
        await page.click('[data-act="meal-rephoto"]'); await settle(page, 0.5, 10)
        body = await page.inner_text("#sheet .sheet-body")
        check("שקשוקה" in body and "אורז לבן" not in body, f"retake did not replace the last result (names: {names})")
        check(not errs, f"JS errors: {errs}")
    finally:
        await ctx.close()


SUPP = {
    "vitd": {"isSupplement": True, "name": "ויטמין D3 2000", "brand": "Solgar", "form": "capsule", "amount": "2000 IU", "ingredients": [{"name": "ויטמין D3", "amount": "2000 IU"}], "labelDose": "כמוסה אחת ביום עם ארוחה", "qty": 1, "food": "fat", "slots": ["noon"], "benefit": "עצם ושריר.", "fit": "קל לפספס עם תיאבון קטן.", "timing": "עם ארוחת הצהריים.", "spacing": [], "verdict": "ok", "cautions": [], "confidence": "high"},
    "burner": {"isSupplement": True, "name": "Green Tea Fat Burner", "brand": "Slim+", "form": "capsule", "amount": "500 mg", "ingredients": [{"name": "תמצית תה ירוק", "amount": "400 mg"}, {"name": "קפאין", "amount": "100 mg"}], "labelDose": "2 כמוסות ביום", "qty": 1, "food": "with", "slots": ["morning"], "benefit": "", "fit": "", "timing": "", "spacing": [], "verdict": "ok", "cautions": [], "confidence": "high"},
}


def supp_route(which):
    async def gemini(route):
        if route.request.method == "GET":
            return await route.fulfill(status=200, content_type="application/json", body=json.dumps({"models": []}))
        text = json.loads(route.request.post_data)["contents"][0]["parts"][-1]["text"]
        out = SUPP[which["k"]] if "dietary supplement" in text else {"items": [{"name": "אורז לבן", "qty": "כוס", "kcal": 205, "p": 4.3, "c": 45, "f": 0.4, "fib": 0.6}]}
        await route.fulfill(status=200, content_type="application/json", body=gem_text(out))
    return gemini


async def scan(page, which, k):
    which["k"] = k
    await page.click('#app label.btn:has-text("צילום תוסף")'); await settle(page, 0.5, 10)
    return await page.inner_text("#f-scan")


@test
async def supplement_scan_applies_safety_rules(b):
    which = {"k": "burner"}
    ctx, page, errs = await open_app(b, key("gemini") + HTTP + CAMERA, routes=[("https://generativelanguage.googleapis.com/**", supp_route(which))])
    try:
        await page.click('.tab[data-tab="food"]'); await tick(page, 2)
        await page.click('[data-act="seg"][data-k="supps"]'); await tick(page, 2)
        text = await scan(page, which, "burner")
        check("כדאי לבדוק עם הרופא או הרוקח" in text and "תוסף להרזיה או ממריץ" in text, "the fat-burner rule did not override the AI's 'ok'")
        await page.click('[data-act="scan-save"]'); await tick(page, 4)
        check("⚠️" in await page.inner_text("#app"), "the caution mark is missing from the list")
        check(not errs, f"JS errors: {errs}")
    finally:
        await ctx.close()


@test
async def logging_a_meal_prompts_for_supplements(b):
    which = {"k": "vitd"}
    ctx, page, errs = await open_app(b, key("gemini") + HTTP + CAMERA, routes=[("https://generativelanguage.googleapis.com/**", supp_route(which))])
    try:
        await page.click('.tab[data-tab="food"]'); await tick(page, 2)
        await page.click('[data-act="seg"][data-k="supps"]'); await tick(page, 2)
        await scan(page, which, "vitd")
        await page.click('[data-act="scan-save"]'); await tick(page, 4)
        await page.clock.fast_forward("02:00:00")  # 12:30, lunch time
        await page.click('[data-act="quick"]'); await tick(page, 2)
        await page.click('.qa [data-act="log-meal"][data-mode="photo"]'); await settle(page, 0.5, 10)
        await page.click('#sheet [data-act="meal-save"]'); await tick(page, 4)
        check(await page.locator('#sheet.open').count() == 1 and "הזמן לתוספים" in await page.inner_text("#sheet .sheet-title"), "no supplement prompt after the meal")
        check("מעט שומן" in await page.inner_text("#sheet .sheet-body"), "the low-fat note is missing")
        await page.click('[data-act="ms-take"]'); await tick(page, 6)
        today = await page.evaluate("new Date().toISOString().slice(0, 10)")
        left = await page.evaluate(f"__ln.scheduled.filter(n => n.kind === 'supps' && n.extra.slot === 'noon' && n.extra.date === '{today}').length")
        check(left == 0, "the noon reminder was not cleared after taking the supplements")
        check(not errs, f"JS errors: {errs}")
    finally:
        await ctx.close()


@test
async def water_reminders_follow_settings(b):
    ctx, page, errs = await open_app(b)
    try:
        await open_reminders(page)
        await page.click('.sw[data-k="water"]'); await tick(page, 4)
        times = await page.evaluate("__ln.scheduled.filter(n => n.kind === 'water').map(n => new Date(n.at)).filter(d => d.getDate() === 14).map(d => d.getHours())")
        check(times == [10, 13, 16, 19], f"water reminders for tomorrow: {times}")
        check(not errs, f"JS errors: {errs}")
    finally:
        await ctx.close()


@test
async def theme_toggle(b):
    ctx, page, errs = await open_app(b)
    try:
        before = await page.evaluate("document.documentElement.dataset.theme || 'auto'")
        await page.click('[data-act="theme-toggle"]'); await tick(page, 4)
        after = await page.evaluate("document.documentElement.dataset.theme || 'auto'")
        check(after != before, f"theme did not change ({before} -> {after})")
        check(not errs, f"JS errors: {errs}")
    finally:
        await ctx.close()


@test
async def app_lock_with_pin(b):
    ctx, page, errs = await open_app(b)
    try:
        await page.click('[data-act="settings"]'); await tick(page, 2)
        await page.click('[data-act="lock-toggle"]'); await tick(page, 3)
        await page.fill("#f-pin", "2468"); await page.click('[data-act="pin-next"]'); await tick(page, 2)
        await page.fill("#f-pin", "2468"); await page.click('[data-act="pin-next"]'); await settle(page, 1.0, 6)
        cfg = json.loads(await page.evaluate("localStorage.getItem('mj-lock')"))
        check(cfg["on"] and cfg["len"] == 4 and "2468" not in json.dumps(cfg), "PIN not saved as a hash")
        await page.keyboard.press("Escape"); await tick(page, 2)
        await page.evaluate("__app.listeners.appStateChange({ isActive: false })"); await tick(page, 1)
        await page.evaluate("__app.listeners.appStateChange({ isActive: true })"); await tick(page, 3)
        check(await page.evaluate("!document.getElementById('lock').hidden"), "the app did not lock on return")
        await page.evaluate("__ln.listeners.localNotificationActionPerformed({actionId:'tap', notification:{extra:{kind:'weigh'}}})"); await tick(page, 3)
        check(await page.locator('#sheet.open').count() == 0, "a notification opened a screen behind the lock")
        for d in "1111":
            await page.click(f'#lock [data-lock="{d}"]'); await tick(page, 1, 100)
        await settle(page, 1.0, 3)
        check("קוד שגוי" in await page.inner_text("#lock-msg"), "a wrong PIN was not rejected")
        for d in "2468":
            await page.click(f'#lock [data-lock="{d}"]'); await tick(page, 1, 100)
        await settle(page, 1.0, 4)
        check(await page.evaluate("document.getElementById('lock').hidden"), "the right PIN did not unlock")
        check(await page.locator('#sheet.open').count() == 1, "the waiting notification action did not run after unlocking")
        check(not errs, f"JS errors: {errs}")
    finally:
        await ctx.close()


@test
async def training_and_steps(b):
    ctx, page, errs = await open_app(b)
    try:
        await page.click('.tab[data-tab="track"]'); await tick(page, 2)
        await page.click('[data-act="seg"][data-k="train"]'); await tick(page, 2)
        await page.click('[data-act="log-train"]'); await tick(page, 3)
        await page.fill("#f-tm", "40"); await page.click('[data-act="train-save"]'); await tick(page, 4)
        await page.click('[data-act="steps-edit"]'); await tick(page, 2)
        await page.fill("#f-steps", "6500"); await page.click('[data-act="steps-save"]'); await tick(page, 4)
        week = await page.inner_text('.h-section:text("השבוע") + .group')
        check("1 מתוך 2" in week and "40" in week and "6,500" in week, f"weekly summary wrong: {week}")
        await open_reminders(page)
        await page.click('.sw[data-k="train"]'); await tick(page, 4)
        days = await page.evaluate("__ln.scheduled.filter(n => n.kind === 'train').map(n => new Date(n.at).getDay())")
        check(days and set(days) <= {0, 2, 4}, f"workout reminders on the wrong days: {days}")
        check(not errs, f"JS errors: {errs}")
    finally:
        await ctx.close()


GOOGLE = """window.MYSHOT_GOOGLE_WEB_CLIENT_ID = '123-web.apps.googleusercontent.com';
window.__sl = []; window.Capacitor.Plugins.SocialLogin = {
  initialize: async o => { __sl.push('init'); },
  login: async o => { __sl.push(JSON.stringify(o.options)); return { provider: 'google', result: { accessToken: { token: 'tok', expires: new Date(Date.now() + 3600e3).toISOString() }, profile: { email: 'user@example.com' } } }; },
  logout: async () => { __sl.push('logout'); } };"""


@test
async def drive_backup_keeps_14(b):
    st = {"files": {}, "folder": None, "deleted": [], "uploads": 0}

    async def drive(route):
        r = route.request; u = r.url.replace("%20", " ").replace("%27", "'").replace("%3D", "=")
        j = lambda o: route.fulfill(status=200, content_type="application/json", body=json.dumps(o))
        if r.method == "GET" and "vnd.google-apps.folder" in u:
            return await j({"files": [{"id": st["folder"]}] if st["folder"] else []})
        if r.method == "GET" and "name='myshot-backup" in u:
            return await j({"files": []})
        if r.method == "GET":
            old = [{"id": f"old{i}", "name": f"myshot-backup-2026-10-{i:02d}.json", "createdTime": f"2026-10-{i:02d}T20:00:00Z"} for i in range(15, 0, -1)]
            return await j({"files": [{"id": "f1", "name": "myshot-backup-2026-11-13.json", "createdTime": "2026-11-13T10:30:00Z"}] + old})
        if r.method == "POST":
            body = json.loads(r.post_data)
            if body.get("mimeType", "").endswith("folder"):
                st["folder"] = "fold"; return await j({"id": "fold"})
            return await j({"id": "f1"})
        if r.method == "PATCH":
            st["uploads"] += 1; json.loads(r.post_data); return await j({"id": "f1"})
        if r.method == "DELETE":
            st["deleted"].append(r.url.rsplit("/", 1)[1]); return await route.fulfill(status=204, body="")
    ctx, page, errs = await open_app(b, HTTP + GOOGLE, routes=[("https://www.googleapis.com/**", drive)])
    try:
        await page.click('[data-act="settings"]'); await tick(page, 2)
        await page.click('[data-act="gd-connect"]'); await settle(page, 0.6, 10)
        check("נשמר ב-Drive" in await page.inner_text("#toast"), "the first Drive backup did not finish")
        check(st["uploads"] == 1, f"expected one upload, got {st['uploads']}")
        check(sorted(st["deleted"]) == ["old1", "old2"], f"retention should delete the 2 oldest of 16: {st['deleted']}")
        check(not errs, f"JS errors: {errs}")
    finally:
        await ctx.close()


@test
async def drive_hidden_without_client_id(b):
    ctx, page, errs = await open_app(b)
    try:
        await page.click('[data-act="settings"]'); await tick(page, 2)
        check(await page.locator('[data-act="gd-connect"]').count() == 0, "the Drive block appears without a client ID")
        check(await page.locator('[data-act="backup-drive"]').count() == 1, "the share-sheet backup is missing")
    finally:
        await ctx.close()


@test
async def no_horizontal_overflow_at_360px(b):
    ctx, page, errs = await open_app(b, w=360)
    try:
        bad = []
        async def probe(name):
            r = await page.evaluate("({sw: document.documentElement.scrollWidth, cw: document.documentElement.clientWidth})")
            if r["sw"] > r["cw"]:
                bad.append(f"{name}: {r['sw']}>{r['cw']}")
        for tab in ["home", "shots", "food", "track", "more"]:
            await page.click(f'.tab[data-tab="{tab}"]'); await tick(page, 2); await probe(tab)
        await page.click('.tab[data-tab="food"]'); await tick(page, 1)
        await page.click('[data-act="seg"][data-k="supps"]'); await tick(page, 2); await probe("supplements")
        await page.click('.tab[data-tab="track"]'); await tick(page, 1)
        for seg in ["symptoms", "body", "train"]:
            await page.click(f'[data-act="seg"][data-k="{seg}"]'); await tick(page, 2); await probe(f"track/{seg}")
        check(not bad, f"horizontal overflow: {bad}")
        check(not errs, f"JS errors: {errs}")
    finally:
        await ctx.close()


# ---------------------------------------------------------------- runner

async def main():
    only = set(sys.argv[1:])
    serve(port=PORT, root=str(ROOT / "www"))
    results = []
    async with async_playwright() as p:
        b = await p.chromium.launch()
        for t in TESTS:
            if only and t.__name__ not in only:
                continue
            t0 = time.time()
            try:
                await asyncio.wait_for(t(b), timeout=120)
                results.append((t.__name__, None)); print(f"PASS  {t.__name__}  ({time.time() - t0:.1f}s)", flush=True)
            except Exception as e:
                results.append((t.__name__, e)); print(f"FAIL  {t.__name__}: {e}", flush=True)
                if not isinstance(e, AssertionError):
                    traceback.print_exc()
        await b.close()
    failed = [n for n, e in results if e]
    print(f"\n{len(results) - len(failed)}/{len(results)} passed" + (f" — failed: {', '.join(failed)}" if failed else ""))
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    asyncio.run(main())
