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


async def settings_page(page, p):
    await page.click('[data-act="settings"]'); await tick(page, 2)
    await page.click(f'[data-act="set-go"][data-p="{p}"]'); await tick(page, 2)


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
        await tick(page, 3)
        check(await page.locator('#sheet.open').count() == 0, "an existing user got a first-launch screen")
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
        await settings_page(page, "privacy")
        await page.click('[data-act="discreet-tog"]'); await tick(page, 4)
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
        await settings_page(page, "med")
        check(await page.locator('#sheet.open').count() == 1, "settings page did not open")
        await page.evaluate("__app.listeners.backButton({canGoBack:false})"); await tick(page, 2)
        check(await page.locator('[data-act="set-go"]').count() > 0, "back from a settings page did not return to the settings list")
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
        await settings_page(page, "backup")
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
        await settings_page(page, "backup")
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
        await settings_page(page, "ai"); await settle(page, 0.3, 3)
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
        await settings_page(page, "privacy")
        await page.click('[data-act="lock-method"][data-v="pin"]'); await tick(page, 3)
        await page.fill("#f-pin", "2468"); await page.click('[data-act="pin-next"]'); await tick(page, 2)
        await page.fill("#f-pin", "2468"); await page.click('[data-act="pin-next"]'); await settle(page, 1.0, 6)
        cfg = json.loads(await page.evaluate("localStorage.getItem('mj-lock')"))
        check(cfg["on"] and cfg["method"] == "pin" and cfg["len"] == 4 and "2468" not in json.dumps(cfg), "PIN not saved as a hash")
        check(await page.locator('[data-act="lock-method"][data-v="pin"][aria-pressed="true"]').count() == 1, "the privacy page does not show the PIN method")
        await page.keyboard.press("Escape"); await tick(page, 2)
        await page.evaluate("__app.listeners.appStateChange({ isActive: false })"); await tick(page, 1)
        await page.evaluate("__app.listeners.appStateChange({ isActive: true })"); await tick(page, 3)
        check(await page.evaluate("!document.getElementById('lock').hidden"), "the app did not lock on return")
        check(await page.locator('#lock .lock-bio-btn').count() == 0, "the PIN lock also offers fingerprint")
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


BIO = """window.__bio = []; window.__bioFail = null;
window.Capacitor.Plugins.BiometricAuthNative = { checkBiometry: async () => ({ isAvailable: true, deviceIsSecure: true }),
  internalAuthenticate: async o => { __bio.push(o.reason);
    // like a real phone: the prompt sends the app to the background and back
    // (the return to the app arrives just after the prompt finishes, the order that used to re-lock)
    const L = __app.listeners.appStateChange; if (L) L({ isActive: false });
    await new Promise(r => setTimeout(r, 50)); setTimeout(() => { if (L) L({ isActive: true }); }, 30);
    if (window.__bioFail) throw { code: window.__bioFail }; } };"""


@test
async def app_lock_with_fingerprint(b):
    ctx, page, errs = await open_app(b, BIO)
    try:
        await settings_page(page, "privacy")
        await page.click('[data-act="lock-method"][data-v="bio"]'); await settle(page, 0.3, 4)
        cfg = json.loads(await page.evaluate("localStorage.getItem('mj-lock')"))
        check(cfg["on"] and cfg["method"] == "bio" and "hash" not in cfg, f"fingerprint lock not saved on its own: {cfg}")
        check("טביעת אצבע פועלת" in await page.inner_text("#toast"), "no confirmation after enabling fingerprint")
        await page.keyboard.press("Escape"); await tick(page, 2)
        n = await page.evaluate("__bio.length")
        await page.evaluate("__app.listeners.appStateChange({ isActive: false })"); await tick(page, 1)
        await page.evaluate("__app.listeners.appStateChange({ isActive: true })"); await settle(page, 0.3, 6)
        check(await page.locator('#lock .lock-keys').count() == 0, "the fingerprint lock also shows a PIN keypad")
        check(await page.evaluate("document.getElementById('lock').hidden"), "fingerprint did not unlock (or the prompt re-locked the app)")
        await settle(page, 0.3, 8)
        check(await page.evaluate("__bio.length") == n + 1, f"expected exactly one prompt, got {await page.evaluate('__bio.length') - n}")
        check(await page.evaluate("document.getElementById('lock').hidden"), "the app locked again after unlocking")
        # our own share sheet is not "leaving the app"
        await settings_page(page, "backup")
        await page.click('[data-act="backup-drive"]'); await settle(page)
        await page.evaluate("__app.listeners.appStateChange({ isActive: false })"); await tick(page, 1)
        await page.evaluate("__app.listeners.appStateChange({ isActive: true })"); await tick(page, 3)
        check(await page.evaluate("!document.getElementById('lock') || document.getElementById('lock').hidden"), "returning from the share sheet locked the app")
        await page.keyboard.press("Escape"); await tick(page, 2)
        # a cancelled prompt leaves the lock with a retry button; retry works
        await page.evaluate("window.__bioFail = 'userCancel'")
        await page.evaluate("__app.listeners.appStateChange({ isActive: false })"); await tick(page, 1)
        await page.evaluate("__app.listeners.appStateChange({ isActive: true })"); await settle(page, 0.3, 6)
        check(await page.evaluate("!document.getElementById('lock').hidden"), "a cancelled prompt unlocked the app")
        check("לחצו" in await page.inner_text("#lock-msg"), "no retry hint after a cancelled prompt")
        await page.evaluate("window.__bioFail = null")
        await page.click('#lock [data-lock="bio"]'); await settle(page, 0.3, 6)
        check(await page.evaluate("document.getElementById('lock').hidden"), "retrying the fingerprint did not unlock")
        check(not errs, f"JS errors: {errs}")
    finally:
        await ctx.close()


@test
async def settings_list_and_pages(b):
    ctx, page, errs = await open_app(b)
    try:
        await page.click('[data-act="settings"]'); await tick(page, 2)
        rows = await page.evaluate("Array.from(document.querySelectorAll('#sheet [data-act=set-go]')).map(b => b.dataset.p)")
        check(rows == ["med", "goals", "privacy", "backup"] or rows == ["med", "goals", "ai", "privacy", "backup"], f"settings rows: {rows}")
        check(await page.locator('#sheet [data-act="rem-page"]').count() == 1 and await page.locator('#sheet [data-pick="theme"]').count() == 3, "reminders row or theme buttons missing")
        check(await page.locator('#sheet input').count() == 0, "the settings list should have no form fields")
        await page.click('[data-act="set-go"][data-p="goals"]'); await tick(page, 2)
        await page.fill("#f-water", "10"); await page.click('#sheet [data-pick="tg"][data-val="3"]'); await page.click('[data-act="set-save"]'); await tick(page, 4)
        check("היעדים נשמרו" in await page.inner_text("#toast"), "goals were not saved")
        core = await mockdb(page, "core")
        check(core["settings"]["water"] == 10 and core["settings"]["trainGoal"] == 3, f"goals not stored: water {core['settings'].get('water')}, training {core['settings'].get('trainGoal')}")
        check(await page.locator('[data-act="set-go"]').count() > 0, "saving a page did not return to the settings list")
        await page.click('[data-act="set-go"][data-p="med"]'); await tick(page, 2)
        check(await page.locator('#sheet [data-pick="med"]').count() > 3, "the medication page has no medication choices")
        await page.click('[data-act="set-back"]'); await tick(page, 2)
        check(await page.locator('[data-act="set-go"]').count() > 0, "the back link did not return to the settings list")
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
        await settings_page(page, "backup")
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
        await settings_page(page, "backup")
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


FRESH = "if (!localStorage.getItem('__fresh')) { localStorage.setItem('__mockdb', '{}'); localStorage.setItem('__fresh', '1'); }\n"
BACKUP = json.dumps({"app": "mounjaro-journal", "v": 2, "appVersion": "1.6.1", "exported": "2026-11-12T20:00:00Z", "docs": SEED, "images": {}, "photos": {}}, ensure_ascii=False)


def drive_with(files):
    async def drive(route):
        r = route.request; u = r.url.replace("%20", " ").replace("%27", "'").replace("%3D", "=")
        if r.method == "GET" and "alt=media" in u:
            return await route.fulfill(status=200, content_type="application/json", body=BACKUP)
        if r.method == "GET" and "name contains 'myshot-backup-'" in u:
            return await route.fulfill(status=200, content_type="application/json", body=json.dumps({"files": files}))
        await route.fulfill(status=200, content_type="application/json", body=json.dumps({"files": []}))
    return drive


async def welcome_choices(page):
    await tick(page, 3)
    check(await page.locator('#sheet.open').count() == 1 and "ברוכים הבאים" in await page.inner_text("#sheet .sheet-title"), "no welcome screen on a new install")
    acts = await page.evaluate("Array.from(document.querySelectorAll('#f-welcome [data-act], #f-welcome input[type=file]')).map(e => e.dataset.act || e.dataset.file)")
    check(acts == ["welcome-drive", "welcome-import", "welcome-new"], f"welcome options: {acts}")


@test
async def first_run_start_fresh_then_lock_offer(b):
    ctx, page, errs = await open_app(b, BIO, pre=FRESH)
    try:
        await welcome_choices(page)
        await page.click('[data-act="welcome-new"]'); await tick(page, 3)
        check(await page.locator('#sheet [data-pick="med"]').count() > 3, "'start fresh' did not open the setup")
        await page.click('.sheet [data-pick="day"][data-val="4"]'); await page.click('[data-act="onb-save"]'); await settle(page, 0.3, 8)
        check(await page.locator('#sheet.open').count() == 1 and "לנעול" in await page.inner_text("#sheet .sheet-title"), "no lock offer after the first setup")
        check(await page.locator('#offer-bio').count() == 1 and await page.locator('[data-act="offer-pin"]').count() == 1, "the lock offer should give fingerprint and code")
        await page.click('[data-act="offer-pin"]'); await tick(page, 2)
        await page.fill("#f-pin", "1357"); await page.click('[data-act="pin-next"]'); await tick(page, 2)
        await page.fill("#f-pin", "1357"); await page.click('[data-act="pin-next"]'); await settle(page, 1.0, 6)
        cfg = json.loads(await page.evaluate("localStorage.getItem('mj-lock')"))
        check(cfg["method"] == "pin", f"lock not set from the offer: {cfg}")
        check(await page.locator('#sheet.open').count() == 0, "the offer did not close after choosing a code")
        check(await page.evaluate("localStorage.getItem('mj-lock-offer')") == "1", "the offer will be shown again")
        check(not errs, f"JS errors: {errs}")
    finally:
        await ctx.close()


@test
async def first_run_restores_from_drive(b):
    files = [{"id": "b2", "name": "myshot-backup-2026-11-12.json", "modifiedTime": "2026-11-12T20:00:00Z", "size": "40960"},
             {"id": "b1", "name": "myshot-backup-2026-11-11.json", "modifiedTime": "2026-11-11T20:00:00Z", "size": "40000"},
             {"id": "x9", "name": "myshot-backup-notes.txt", "modifiedTime": "2026-11-10T20:00:00Z"}]
    ctx, page, errs = await open_app(b, HTTP + GOOGLE + BIO, pre=FRESH, routes=[("https://www.googleapis.com/**", drive_with(files))])
    try:
        await welcome_choices(page)
        await page.click('[data-act="welcome-drive"]'); await settle(page, 0.5, 6)
        body = await page.inner_text("#f-welcome")
        check("נמצא גיבוי" in body and "12.11" in body, f"the latest Drive backup was not found: {body[:120]}")
        check(await page.locator('#f-welcome [data-act="welcome-restore"]').count() == 2, "expected the latest backup plus one earlier one (not the .txt)")
        await page.click('#f-welcome .btn[data-act="welcome-restore"]'); await settle(page, 0.6, 8)
        check(await page.locator(".confirm").count() == 0, "a new install should not ask to replace data")
        inj = (await mockdb(page, "injections")) or {"items": []}
        check(len(inj["items"]) == len(SEED["injections"]["items"]), f"restored {len(inj['items'])} injections, expected {len(SEED['injections']['items'])}")
        check(await page.locator('#sheet.open').count() == 1 and "לנעול" in await page.inner_text("#sheet .sheet-title"), "no lock offer after restoring")
        await page.click('[data-act="offer-skip"]'); await tick(page, 2)
        check(await page.locator('#sheet.open').count() == 0, "'not now' did not close the offer")
        check(json.loads(await page.evaluate("localStorage.getItem('mj-gdrive')") or "{}").get("connected"), "Drive should stay connected for the daily backup")
        check(not errs, f"JS errors: {errs}")
    finally:
        await ctx.close()


@test
async def first_run_drive_has_no_backup(b):
    ctx, page, errs = await open_app(b, HTTP + GOOGLE, pre=FRESH, routes=[("https://www.googleapis.com/**", drive_with([]))])
    try:
        await welcome_choices(page)
        await page.click('[data-act="welcome-drive"]'); await settle(page, 0.5, 6)
        body = await page.inner_text("#f-welcome")
        check("לא נמצא ב-Drive גיבוי" in body, "no message when Drive has no backup")
        check(await page.locator('#f-welcome input[data-file="welcome-import"]').count() == 1 and await page.locator('#f-welcome [data-act="welcome-new"]').count() == 1, "the other options disappeared")
        check(not errs, f"JS errors: {errs}")
    finally:
        await ctx.close()


@test
async def first_run_restores_from_a_file(b):
    ctx, page, errs = await open_app(b, BIO, pre=FRESH)
    try:
        await welcome_choices(page)
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as f:
            f.write(BACKUP)
        await page.set_input_files('#f-welcome input[data-file="welcome-import"]', f.name); await settle(page, 0.6, 8)
        check("שוחזר" in await page.inner_text("#toast"), "the backup file was not restored")
        core = await mockdb(page, "core")
        check(core and core["settings"].get("setup"), "settings not restored")
        check(await page.locator('#sheet.open').count() == 1 and "לנעול" in await page.inner_text("#sheet .sheet-title"), "no lock offer after restoring from a file")
        check(not errs, f"JS errors: {errs}")
    finally:
        await ctx.close()


EN_PRE = "if (!localStorage.getItem('__lang')) { localStorage.setItem('mj-lang', 'en'); localStorage.setItem('__lang', '1'); }\n"


async def hebrew_on_screen(page):
    """Visible text with Hebrew letters (the app's own text; the medical guide is stage 2)."""
    return await page.evaluate("""() => {
      const out = new Set(), walk = n => { for (const c of n.childNodes) {
        if (c.nodeType === 3) { const t = c.nodeValue.trim(); if (/[\\u0590-\\u05FF]/.test(t) && c.parentElement && c.parentElement.offsetParent !== null) out.add(t.slice(0, 60)); }
        else if (c.nodeType === 1 && !/^(SCRIPT|STYLE)$/.test(c.nodeName) && !c.hidden) walk(c); } };
      walk(document.body);
      document.querySelectorAll('[aria-label],[placeholder]').forEach(e => { for (const a of ['aria-label', 'placeholder']) { const v = e.getAttribute(a); if (v && /[\\u0590-\\u05FF]/.test(v) && !/Language/.test(v)) out.add(a + ': ' + v.slice(0, 50)); } });
      return [...out].filter(t => !/^(עברית|שפה · Language)$/.test(t));
    }""")


@test
async def english_interface_end_to_end(b):
    ctx, page, errs = await open_app(b, BIO, pre=FRESH + EN_PRE)
    try:
        await tick(page, 3)
        check(await page.evaluate("document.documentElement.dir") == "ltr" and await page.evaluate("document.documentElement.lang") == "en", "the page is not left-to-right English")
        check("Welcome" in await page.inner_text("#sheet .sheet-title"), "the welcome screen is not in English")
        found = {}
        found["welcome"] = await hebrew_on_screen(page)
        await page.click('[data-act="welcome-new"]'); await tick(page, 3)
        found["setup"] = await hebrew_on_screen(page)
        await page.click('.sheet [data-pick="day"][data-val="4"]'); await page.click('[data-act="onb-save"]'); await settle(page, 0.3, 8)
        found["lock offer"] = await hebrew_on_screen(page)
        await page.click('[data-act="offer-skip"]'); await tick(page, 4)
        if await page.locator('#paywall.open').count():
            found['plus offer'] = await hebrew_on_screen(page); await page.click('#paywall [data-act="pw-close"]'); await tick(page, 2)
        for tab in ["home", "shots", "food", "track", "more"]:
            await page.click(f'.tab[data-tab="{tab}"]'); await tick(page, 2); found[tab] = await hebrew_on_screen(page)
        await page.click('.tab[data-tab="food"]'); await tick(page, 1); await page.click('[data-act="seg"][data-k="supps"]'); await tick(page, 2); found["supplements"] = await hebrew_on_screen(page)
        await page.click('.tab[data-tab="track"]'); await tick(page, 1)
        for seg in ["symptoms", "body", "train"]:
            await page.click(f'[data-act="seg"][data-k="{seg}"]'); await tick(page, 2); found["track/" + seg] = await hebrew_on_screen(page)
        await open_reminders(page); found["reminders"] = await hebrew_on_screen(page)
        await page.click('[data-act="settings"]'); await tick(page, 2); found["settings"] = await hebrew_on_screen(page)
        for p in ["med", "goals", "privacy", "backup"]:
            await page.click(f'[data-act="set-go"][data-p="{p}"]'); await tick(page, 2); found["settings/" + p] = await hebrew_on_screen(page)
            await page.click('[data-act="set-back"]'); await tick(page, 2)
        # medical texts still waiting for stage 2 are listed in i18n_pending.json; everything else must be English
        pending = [__import__('re').sub(r'<[^>]*>', ' ', k) for k in json.loads((HERE / "i18n_pending.json").read_text(encoding="utf-8"))]
        def is_pending(t):
            m = __import__('re').search('[\u0590-\u05FF]', t); frag = t[m.start():m.start() + 14] if m else t
            return any(frag in k for k in pending)
        bad = {k: [t for t in v if not is_pending(t)] for k, v in found.items()}
        bad = {k: v for k, v in bad.items() if v}
        check(not bad, f"Hebrew left on English screens: {bad}")
        titles = await page.evaluate("__ln.scheduled.map(n => n.title + ' ' + n.body)")
        check(titles and not [t for t in titles if __import__('re').search('[\u0590-\u05FF]', t)], f"notifications not in English: {titles[:3]}")
        check(not errs, f"JS errors: {errs}")
    finally:
        await ctx.close()


@test
async def english_lock_screen_and_units(b):
    ctx, page, errs = await open_app(b, BIO + EN_PRE)
    try:
        await settings_page(page, "privacy")
        await page.click('[data-act="lock-method"][data-v="bio"]'); await settle(page, 0.3, 4)
        check("Fingerprint lock is on" in await page.inner_text("#toast"), "lock confirmation not in English")
        await page.keyboard.press("Escape"); await tick(page, 2)
        await page.evaluate("window.__bioFail = 'userCancel'")
        await page.evaluate("__app.listeners.appStateChange({ isActive: false })"); await tick(page, 1)
        await page.evaluate("__app.listeners.appStateChange({ isActive: true })"); await settle(page, 0.3, 6)
        lock = await page.inner_text("#lock")
        check("MyShot is locked" in lock and "Unlock with fingerprint" in lock, f"lock screen not in English: {lock[:80]}")
        await page.evaluate("window.__bioFail = null"); await page.click('#lock [data-lock="bio"]'); await settle(page, 0.3, 6)
        await page.click('.tab[data-tab="food"]'); await tick(page, 1); await page.click('[data-act="seg"][data-k="supps"]'); await tick(page, 2)
        txt = await page.inner_text("#app")
        check(__import__('re').search(r"\b1 (capsule|pill|tablet)\b", txt) or "2 " in txt, f"quantities not in English word order: {txt[:200]}")
        check(not errs, f"JS errors: {errs}")
    finally:
        await ctx.close()


@test
async def language_follows_the_phone_on_a_new_install(b):
    ctx = await b.new_context(viewport={"width": 390, "height": 844}, locale="en-US", timezone_id="Asia/Jerusalem", reduced_motion="reduce")
    page = await ctx.new_page(); errs = []
    page.on("pageerror", lambda e: errs.append(str(e)))
    await page.clock.install(time=__import__('datetime').datetime(2026, 11, 13, 10, 30))
    await page.route("**/fonts.g*/**", lambda r: r.abort())
    await ctx.add_init_script(PRE + FRESH + MOCK + CAP)
    try:
        await page.goto(URL, wait_until="domcontentloaded"); await page.clock.run_for(1500); await tick(page, 8); await settle(page, 0.5, 6)
        check(await page.evaluate("localStorage.getItem('mj-lang')") == "en", "an English phone did not get English")
        check(await page.evaluate("document.documentElement.dir") == "ltr", "the app did not reload in English")
        check(await page.locator('#sheet.open').count() == 1 and "Welcome" in await page.inner_text("#sheet .sheet-title"), "no English welcome screen")
        check(not errs, f"JS errors: {errs}")
    finally:
        await ctx.close()


@test
async def existing_hebrew_user_stays_in_hebrew_and_can_switch(b):
    ctx, page, errs = await open_app(b)
    try:
        check(await page.evaluate("localStorage.getItem('mj-lang')") == "he" and await page.evaluate("document.documentElement.dir") == "rtl", "an existing user did not stay in Hebrew")
        await page.click('[data-act="settings"]'); await tick(page, 2)
        async with page.expect_navigation():
            await page.click('[data-act="set-lang"][data-v="en"]'); await tick(page, 2)
        await page.clock.run_for(1500); await tick(page, 6)
        check(await page.evaluate("document.documentElement.dir") == "ltr", "switching to English did not apply")
        tabs = await page.evaluate("document.querySelector('.tabs').textContent")
        check("Home" in tabs and "Injections" in tabs, f"the tab bar is not in English after switching: {tabs}")
        await page.click('[data-act="settings"]'); await tick(page, 2)
        async with page.expect_navigation():
            await page.click('[data-act="set-lang"][data-v="he"]'); await tick(page, 2)
        await page.clock.run_for(1500); await tick(page, 6)
        check(await page.evaluate("document.documentElement.dir") == "rtl", "switching back to Hebrew did not apply")
    finally:
        await ctx.close()


CANVAS_SPY = """window.__drawn = []; window.__dirs = new Set();
const __ft = CanvasRenderingContext2D.prototype.fillText;
CanvasRenderingContext2D.prototype.fillText = function (t, x, y, w) { __drawn.push(String(t)); __dirs.add(this.direction); return __ft.call(this, t, x, y, w); };"""


@test
async def english_guide_about_and_report(b):
    ctx, page, errs = await open_app(b, BIO + CANVAS_SPY, pre=FRESH + EN_PRE)
    try:
        await tick(page, 3)
        await page.click('[data-act="welcome-new"]'); await tick(page, 3)
        await page.click('.sheet [data-pick="day"][data-val="4"]'); await page.fill('#f-last', '2026-11-12T09:00'); await page.click('[data-act="onb-save"]'); await settle(page, 0.3, 8)
        if await page.locator('[data-act="offer-skip"]').count(): await page.click('[data-act="offer-skip"]'); await tick(page, 2)
        await tick(page, 3)
        if await page.locator('#paywall.open').count():
            po = await hebrew_on_screen(page); check(not po, f"Hebrew on the English Plus offer: {po}"); await page.click('#paywall [data-act="pw-close"]'); await tick(page, 2)
        found = {}
        await page.click('.tab[data-tab="more"]'); await tick(page, 2)
        await page.click('.row[data-act="more-go"][data-k="guide"]'); await tick(page, 2)
        await page.evaluate("document.querySelectorAll('#app details').forEach(d => d.open = true)"); await tick(page, 2)
        found["guide"] = await hebrew_on_screen(page)
        check(len(await page.inner_text("#app")) > 1500, "the guide looks empty")
        await page.click('.tab[data-tab="more"]'); await tick(page, 2)
        await page.click('[data-act="about"]'); await tick(page, 3)
        await page.click('#sheet [data-act="about-ver"]'); await tick(page, 2)
        check(await page.locator('#sheet li, #sheet .log-row, #sheet .changelog *').count() > 3, "the changelog did not open")
        found["about"] = await hebrew_on_screen(page)
        await page.keyboard.press("Escape"); await tick(page, 2)
        await page.click('.tab[data-tab="more"]'); await tick(page, 2)
        await page.click('.row[data-act="more-go"][data-k="doctor"]'); await tick(page, 2)
        await page.click('#app [data-act="report"]'); await settle(page, 2.0, 10)
        drawn = await page.evaluate("__drawn"); dirs = await page.evaluate("[...__dirs]")
        heb = [t for t in drawn if __import__('re').search('[\u0590-\u05FF]', t)]
        check(drawn and any("Treatment" in t for t in drawn), f"the report did not draw its English headings: {drawn[:6]}")
        check(not heb, f"Hebrew in the English report: {heb[:5]}")
        check("rtl" not in dirs, f"the English report draws right-to-left: {dirs}")
        bad = {k: v for k, v in found.items() if v}
        check(not bad, f"Hebrew left in English: {bad}")
        check(not errs, f"JS errors: {errs}")
    finally:
        await ctx.close()


async def lang_end_to_end(b, lang, home, settings):
    pre = "if (!localStorage.getItem('__lang')) { localStorage.setItem('mj-lang', '%s'); localStorage.setItem('__lang', '1'); }\n" % lang
    ctx, page, errs = await open_app(b, BIO, pre=FRESH + pre)
    try:
        await tick(page, 3)
        check(await page.evaluate("document.documentElement.lang") == lang and await page.evaluate("document.documentElement.dir") == "ltr", f"{lang}: wrong lang or direction")
        found = {"welcome": await hebrew_on_screen(page)}
        await page.click('[data-act="welcome-new"]'); await tick(page, 3)
        await page.click('.sheet [data-pick="day"][data-val="4"]'); await page.click('[data-act="onb-save"]'); await settle(page, 0.3, 8)
        if await page.locator('[data-act="offer-skip"]').count(): await page.click('[data-act="offer-skip"]'); await tick(page, 2)
        await tick(page, 3)
        if await page.locator('#paywall.open').count():
            found['plus offer'] = await hebrew_on_screen(page); await page.click('#paywall [data-act="pw-close"]'); await tick(page, 2)
        for tab in ["home", "shots", "food", "track", "more"]:
            await page.click(f'.tab[data-tab="{tab}"]'); await tick(page, 2); found[tab] = await hebrew_on_screen(page)
        await page.click('.tab[data-tab="food"]'); await tick(page, 1); await page.click('[data-act="seg"][data-k="supps"]'); await tick(page, 2); found["supplements"] = await hebrew_on_screen(page)
        await page.click('.tab[data-tab="track"]'); await tick(page, 1)
        for seg in ["symptoms", "body", "train"]:
            await page.click(f'[data-act="seg"][data-k="{seg}"]'); await tick(page, 2); found["track/" + seg] = await hebrew_on_screen(page)
        await page.click('.tab[data-tab="more"]'); await tick(page, 2)
        await page.click('.row[data-act="more-go"][data-k="guide"]'); await tick(page, 2)
        await page.evaluate("document.querySelectorAll('#app details').forEach(d => d.open = true)"); await tick(page, 2); found["guide"] = await hebrew_on_screen(page)
        await open_reminders(page); found["reminders"] = await hebrew_on_screen(page)
        await page.click('[data-act="settings"]'); await tick(page, 2); found["settings"] = await hebrew_on_screen(page)
        check(settings in await page.inner_text("#sheet .sheet-title"), f"{lang}: settings title is not translated")
        for p in ["med", "goals", "privacy", "backup"]:
            await page.click(f'[data-act="set-go"][data-p="{p}"]'); await tick(page, 2); found["settings/" + p] = await hebrew_on_screen(page)
            await page.click('[data-act="set-back"]'); await tick(page, 2)
        tabs = await page.evaluate("document.querySelector('.tabs').textContent")
        check(home in tabs, f"{lang}: the tab bar is not translated: {tabs.split()}")
        bad = {k: v for k, v in found.items() if v}
        check(not bad, f"{lang}: Hebrew left: {bad}")
        notes = await page.evaluate("__ln.scheduled.map(n => n.title + ' ' + n.body)")
        check(notes and not [t for t in notes if __import__('re').search('[\u0590-\u05FF]', t)], f"{lang}: notifications with Hebrew: {notes[:2]}")
        check(not errs, f"{lang}: JS errors: {errs}")
    finally:
        await ctx.close()


@test
async def russian_interface(b):
    await lang_end_to_end(b, "ru", "Главная", "Настройки")
    ctx, page, errs = await open_app(b, "", pre="if (!localStorage.getItem('__lang')) { localStorage.setItem('mj-lang', 'ru'); localStorage.setItem('__lang', '1'); }\n")
    try:
        tabs = await page.evaluate("document.querySelector('.tabs').textContent")
        check("Инъекции" in tabs and "Инъекций" not in tabs, f"ru: the injections tab label has the counting form: {tabs.split()}")
    finally:
        await ctx.close()


@test
async def spanish_interface(b):
    await lang_end_to_end(b, "es", "Inicio", "Ajustes")


@test
async def french_interface(b):
    await lang_end_to_end(b, "fr", "Accueil", "Réglages")


@test
async def languages_follow_the_phone(b):
    for locale, want in [("ru-RU", "ru"), ("es-ES", "es"), ("fr-FR", "fr"), ("de-DE", "en"), ("he-IL", "he")]:
        ctx = await b.new_context(viewport={"width": 390, "height": 844}, locale=locale, timezone_id="Asia/Jerusalem", reduced_motion="reduce")
        page = await ctx.new_page()
        await page.clock.install(time=__import__('datetime').datetime(2026, 11, 13, 10, 30))
        await page.route("**/fonts.g*/**", lambda r: r.abort())
        await ctx.add_init_script(PRE + FRESH + MOCK + CAP)
        try:
            await page.goto(URL, wait_until="domcontentloaded"); await page.clock.run_for(1500); await tick(page, 8); await settle(page, 0.5, 6)
            got = await page.evaluate("localStorage.getItem('mj-lang')")
            check(got == want, f"phone {locale}: got {got}, expected {want}")
        finally:
            await ctx.close()


PURCHASES = """window.MYSHOT_RC_KEY = 'goog_test_key';
window.__rc = { active: false, calls: [] };
const __ci = () => ({ entitlements: { all: {}, active: __rc.active ? { plus: { identifier: 'plus', isActive: true, willRenew: true, periodType: 'TRIAL', expirationDate: '2026-11-20T10:30:00Z' } } : {} }, managementURL: 'https://play.google.com/store/account/subscriptions' });
window.Capacitor.Plugins.Purchases = {
  configure: async o => { __rc.calls.push('configure:' + o.apiKey); },
  getAppUserID: async () => ({ appUserID: '$RCAnonymousID:test123' }),
  getCustomerInfo: async () => ({ customerInfo: __ci() }),
  getOfferings: async () => ({ current: { identifier: 'default', availablePackages: [
    { identifier: '$rc_monthly', packageType: 'MONTHLY', product: { identifier: 'myshot_plus:monthly', price: 14.9, currencyCode: 'ILS', priceString: '₪14.90' } },
    { identifier: '$rc_annual', packageType: 'ANNUAL', product: { identifier: 'myshot_plus:yearly', price: 99, currencyCode: 'ILS', priceString: '₪99.00', defaultOption: { freePhase: { billingPeriod: { iso8601: 'P1W' } } } } }] } }),
  purchasePackage: async o => { __rc.calls.push('buy:' + o.aPackage.identifier); __rc.active = true; return { customerInfo: __ci(), productIdentifier: o.aPackage.product.identifier }; },
  restorePurchases: async () => { __rc.calls.push('restore'); return { customerInfo: __ci() }; } };"""
THREE_REMINDERS = """if (!localStorage.getItem('__rem3')) { const db = JSON.parse(localStorage.getItem('__mockdb') || '{}'), k = 'data/users/u123/core'; let c = db[k]; const str = typeof c === 'string'; c = str ? JSON.parse(c) : c; c.settings = c.settings || {};
  c.settings.rem = Object.assign({}, c.settings.rem || {}, { custom: [1, 2, 3].map(i => ({ id: 'c' + i, title: 'R' + i, note: '', time: '09:0' + i, rep: 'daily', days: [], date: null, on: true })) });
  db[k] = str ? JSON.stringify(c) : c; localStorage.setItem('__mockdb', JSON.stringify(db)); localStorage.setItem('__rem3', '1'); }
"""


async def open_doctor_report(page):
    await page.click('.tab[data-tab="more"]'); await tick(page, 2)
    await page.click('.row[data-act="more-go"][data-k="doctor"]'); await tick(page, 2)
    await page.click('#app [data-act="report"]'); await settle(page, 0.6, 8)


async def paywall(page):
    return (await page.locator('#paywall.open').count()) == 1


@test
async def plus_preview_in_a_development_build(b):
    ctx, page, errs = await open_app(b)
    try:
        await open_doctor_report(page)
        check(not await paywall(page) and "MyShot Plus" not in await page.inner_text("#sheet .sheet-title"), "a development build locked the report by default")
        await page.keyboard.press("Escape"); await tick(page, 2)
        await page.click('[data-act="settings"]'); await tick(page, 2)
        check(await page.locator('#sheet .plus-card').count() == 1, "no Plus card at the top of settings")
        await page.click('#sheet .plus-card'); await tick(page, 3)
        t = await page.inner_text("#paywall")
        check(await paywall(page) and "תצוגה מקדימה" in t, "the Plus screen did not open as a full-screen preview")
        check(await page.locator('#paywall .pw-plan').count() == 2 and "שנתי" in await page.inner_text('#paywall .pw-plan.on'), "expected two plans with the yearly one selected")
        check("איך עובד הניסיון החינמי" in t and "חיסכון" in t and "בחינם, תמיד" in t, "no trial timeline, savings badge or free-stays-free line")
        await page.click('#paywall [data-act="plus-sim"][data-v="free"]'); await tick(page, 2)
        await page.click('#paywall [data-act="pw-close"]'); await tick(page, 2)
        await open_doctor_report(page); await tick(page, 3)
        check(await paywall(page) and "דוח ה-PDF" in await page.inner_text("#paywall"), "as a free user the report did not open Plus with its reason")
        await page.click('#paywall [data-act="pw-buy"]'); await tick(page, 2)
        await page.click('.confirm [data-c="1"]'); await settle(page, 0.4, 4)
        check("ברוכים הבאים ל-MyShot Plus" in await page.inner_text("#paywall"), "no welcome screen after the simulated purchase")
        await page.click('#paywall .pw-foot [data-act="pw-close"]'); await tick(page, 2)
        await open_doctor_report(page)
        check(not await paywall(page), "the report is still locked as a subscriber")
        check(not errs, f"JS errors: {errs}")
    finally:
        await ctx.close()


@test
async def plus_paywall_purchase_unlocks(b):
    ctx, page, errs = await open_app(b, PURCHASES)
    try:
        await tick(page, 4)
        check("configure:goog_test_key" in await page.evaluate("__rc.calls"), "RevenueCat was not configured with the key")
        await page.click('.tab[data-tab="track"]'); await tick(page, 1); await page.click('[data-act="seg"][data-k="symptoms"]'); await tick(page, 2)
        check(await page.locator('#app .plus-lock').count() >= 1, "insights are open without Plus")
        await open_doctor_report(page); await tick(page, 3)
        t = await page.inner_text("#paywall")
        check(await paywall(page) and "תצוגה מקדימה" not in t, "the PDF report did not open the real Plus screen")
        on = await page.inner_text('#paywall .pw-plan.on')
        check("₪99.00" in on and "45%" in on and "8.25" in on, f"the yearly plan should be selected, with its saving and monthly price: {on}")
        check("להתחיל ניסיון חינם" in await page.inner_text('#paywall [data-act="pw-buy"]') and "7 ימים חינם, ואחר כך ₪99.00 לשנה" in await page.inner_text('#paywall .pw-terms'), "the button and the charge line do not match the trial")
        await page.click('#paywall .pw-plan:not(.on)'); await tick(page, 2)
        check("להצטרף" in await page.inner_text('#paywall [data-act="pw-buy"]') and await page.locator('#paywall .pw-tl').count() == 0 and "₪14.90 לחודש" in await page.inner_text('#paywall .pw-terms'), "choosing the monthly plan did not update the button and terms")
        await page.click('#paywall .pw-plan:not(.on)'); await tick(page, 2)
        await page.click('#paywall [data-act="pw-buy"]'); await settle(page, 0.5, 6)
        check("buy:$rc_annual" in await page.evaluate("__rc.calls"), "the yearly package was not bought")
        check("ברוכים הבאים ל-MyShot Plus" in await page.inner_text("#paywall"), "no welcome screen after buying")
        await page.click('#paywall .pw-foot [data-act="pw-close"]'); await tick(page, 2)
        await open_doctor_report(page)
        check(not await paywall(page), "the report is still locked after buying")
        await page.keyboard.press("Escape"); await tick(page, 2)
        await page.click('.tab[data-tab="track"]'); await tick(page, 1); await page.click('[data-act="seg"][data-k="symptoms"]'); await tick(page, 2)
        check(await page.locator('#app .plus-lock').count() == 0, "insights are still locked after buying")
        await page.click('[data-act="settings"]'); await tick(page, 2)
        check("פעיל" in await page.inner_text('#sheet .plus-card'), "settings do not show Plus as active")
        notes = await page.evaluate("__ln.scheduled.map(n => n.id + ' ' + n.title)")
        check(any(n.startswith("6600 ") for n in notes), f"no reminder before the free trial ends: {notes[:4]}")
        check(not errs, f"JS errors: {errs}")
    finally:
        await ctx.close()


@test
async def plus_restore_and_reminder_limit(b):
    ctx, page, errs = await open_app(b, PURCHASES, pre=THREE_REMINDERS)
    try:
        await tick(page, 4)
        await open_reminders(page)
        await page.click('[data-act="rem-cnew"]'); await tick(page, 3)
        check(await paywall(page) and "3 תזכורות" in await page.inner_text("#paywall"), "a 4th reminder of your own did not open Plus with the limit explained")
        await page.evaluate("__rc.active = true")
        await page.click('#paywall [data-act="plus-restore"]'); await settle(page, 0.5, 6)
        check("restore" in await page.evaluate("__rc.calls") and "שוחזר" in await page.inner_text("#toast"), "restoring the purchase did not work")
        await page.click('#paywall [data-act="pw-close"]'); await tick(page, 2)
        await page.click('[data-act="rem-cnew"]'); await tick(page, 3)
        check(not await paywall(page) and "MyShot Plus" not in await page.inner_text("#sheet .sheet-title"), "a 4th reminder is still locked after restoring Plus")
        check(not errs, f"JS errors: {errs}")
    finally:
        await ctx.close()


@test
async def plus_ai_included_and_free_quota(b):
    seen = {"n": 0, "users": []}
    meal = {"items": [{"name": "אורז לבן", "qty": "כוס", "kcal": 205, "p": 4.3, "c": 45, "f": 0.4, "fib": 0.6}]}

    async def myshot_ai(route):
        seen["n"] += 1; seen["users"].append(route.request.headers.get("x-myshot-user"))
        if seen["n"] == 1:
            return await route.fulfill(status=200, content_type="application/json", headers={"x-myshot-remaining": "4"}, body=gem_text(meal))
        await route.fulfill(status=402, content_type="application/json", body=json.dumps({"error": "quota", "remaining": 0, "plus": False}))
    ctx, page, errs = await open_app(b, HTTP + CAMERA + PURCHASES + "window.MYSHOT_AI_URL = 'https://ai.example.test';", routes=[("https://ai.example.test/**", myshot_ai)])
    try:
        await tick(page, 4)
        await page.click('[data-act="quick"]'); await tick(page, 2)
        await page.click('.qa [data-act="log-meal"][data-mode="photo"]'); await settle(page, 0.5, 10)
        check("אורז לבן" in await page.inner_text("#sheet .sheet-body"), "a meal photo did not work through MyShot AI without a key")
        check(seen["users"][:1] == ["$RCAnonymousID:test123"], f"MyShot AI did not get the anonymous user id: {seen['users']}")
        await page.click('[data-act="meal-rephoto"]'); await settle(page, 0.5, 10); await tick(page, 6)
        check(await paywall(page) and "נגמרו הזיהויים" in await page.inner_text("#paywall"), "using up the free quota did not offer Plus")
        await page.click('#paywall [data-act="pw-close"]'); await tick(page, 2)
        await settings_page(page, "ai")
        check("MyShot AI" in await page.inner_text("#sheet .sheet-body"), "the AI page does not explain MyShot AI")
        errs = [e for e in errs if "status of 402" not in e]   # the server's "quota used" answer, expected here
        check(not errs, f"JS errors: {errs}")
    finally:
        await ctx.close()


@test
async def plus_paywall_in_english(b):
    ctx, page, errs = await open_app(b, PURCHASES, pre="if (!localStorage.getItem('__lang')) { localStorage.setItem('mj-lang', 'en'); localStorage.setItem('__lang', '1'); }\n")
    try:
        await tick(page, 4)
        await open_doctor_report(page); await tick(page, 3)
        body = await page.inner_text("#paywall")
        heb = [l for l in body.split("\n") if __import__('re').search('[\u0590-\u05FF]', l)]
        check("Yearly" in body and "Start free trial" in body and "Restore purchase" in body and not heb, f"the paywall is not fully in English: {heb[:3]}")
        check(not errs, f"JS errors: {errs}")
    finally:
        await ctx.close()


@test
async def plus_offered_after_first_setup_and_on_home(b):
    ctx, page, errs = await open_app(b, BIO, pre=FRESH)
    try:
        await tick(page, 3)
        await page.click('[data-act="welcome-new"]'); await tick(page, 3)
        await page.click('.sheet [data-pick="day"][data-val="4"]'); await page.click('[data-act="onb-save"]'); await settle(page, 0.3, 8)
        await page.click('[data-act="offer-skip"]'); await tick(page, 4)
        check(await paywall(page), "Plus was not offered after the first setup")
        await page.click('#paywall [data-act="pw-close"]'); await tick(page, 2)
        check(not await paywall(page) and await page.evaluate("localStorage.getItem('mj-plus-intro')") == "1", "closing the offer did not work or it will show again")
        await page.evaluate("localStorage.setItem('mj-opens', '5')"); await page.click('.tab[data-tab="shots"]'); await tick(page, 1); await page.click('.tab[data-tab="home"]'); await tick(page, 2)
        check(await page.locator('#app .plus-home').count() == 1, "no Plus card on the home screen")
        await page.click('#app .plus-home [data-act="plus-card-hide"]'); await tick(page, 2)
        check(await page.locator('#app .plus-home').count() == 0, "the home Plus card did not hide")
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
