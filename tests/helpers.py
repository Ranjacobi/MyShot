import threading, functools, http.server, socketserver, datetime
def serve(port=8765, root="www"):
    class Q(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *a, **k): super().__init__(*a, directory=root, **k)
        def log_message(self, *a): pass
    socketserver.TCPServer.allow_reuse_address = True
    srv = socketserver.ThreadingTCPServer(("127.0.0.1", port), Q)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv
async def new_page(b, scheme="light", w=390, h=844):
    ctx = await b.new_context(viewport={"width":w,"height":h}, device_scale_factor=2, locale="he-IL", timezone_id="Asia/Jerusalem", color_scheme=scheme, reduced_motion="reduce")
    page = await ctx.new_page()
    errs = []
    page.on("pageerror", lambda e: errs.append("PAGEERROR " + str(e)))
    page.on("console", lambda m: errs.append(f"console.{m.type}: {m.text}") if m.type == "error" and "ERR_FAILED" not in m.text else None)
    await page.clock.install(time=datetime.datetime(2026,11,13,10,30))
    await page.route("**/fonts.g*/**", lambda r: r.abort())
    return ctx, page, errs
async def onboard(page):
    await page.wait_for_selector("#sheet.open", timeout=8000)
    await page.click('.sheet [data-pick="day"][data-val="4"]')
    await page.fill('#f-time', '09:00')
    await page.click('.sheet [data-pick="dose"][data-val="5"]')
    await page.fill('#f-last', '2026-11-05T09:00')
    await page.click('.sheet [data-pick="left"][data-val="2"]')
    await page.fill('#f-spare', '1')
    await page.fill('#f-start', '2026-10-08')
    await page.click('[data-act="onb-save"]')
    await page.clock.run_for(600)
