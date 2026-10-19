import os, threading, time, json, re
exec(open("/tmp/meow_tests/web_test.py").read().split("from fastapi.testclient")[0])
time.sleep(0)
ANSWER="## Battery verdict\n\nThe **iPhone 17 Pro** is rated for up to 31 hours of video [1], about an hour ahead of the Pixel 10 Pro [2].\n\nOn Reddit, most owners report a full day with 8–9 hours of screen time [4], though some see faster drain on 5G [5].\n\n```python\nprint('[1] not a cite')\n```"
import uvicorn
srv=uvicorn.Server(uvicorn.Config(g["app"],host="127.0.0.1",port=8766,log_level="warning"))
threading.Thread(target=srv.run,daemon=True).start(); time.sleep(1.5)
from playwright.sync_api import sync_playwright
proxy=os.environ.get("HTTPS_PROXY"); L="/tmp/meow_tests/libs/"
MAP={"marked.min.js":L+"marked-12.0.2/package/marked.min.js","purify.min.js":L+"dompurify-3.1.6/package/dist/purify.min.js","highlight.min.js":L+"hl/package/highlight.min.js","atom-one-dark.min.css":L+"hl/package/styles/atom-one-dark.min.css","katex.min.js":L+"katex-0.16.9/package/dist/katex.min.js","katex.min.css":L+"katex-0.16.9/package/dist/katex.min.css"}
def rt(r):
    u=r.request.url
    for k,v in MAP.items():
        if u.split("?")[0].endswith(k): return r.fulfill(path=v)
    if "127.0.0.1" in u: return r.continue_()
    return r.abort()
T="/tmp/meow_tests/"
with sync_playwright() as p:
    b=p.chromium.launch(args=["--ignore-certificate-errors", f"--proxy-server={proxy}", "--proxy-bypass-list=127.0.0.1;localhost;<loopback>"])
    for vw in [(1440,900),(390,844)]:
        pg=b.new_page(viewport={"width":vw[0],"height":vw[1]}); pg.route("**/*", rt)
        errs=[]; pg.on("pageerror", lambda e: errs.append("PAGEERR "+str(e)[:300])); pg.on("console", lambda m: errs.append(m.text) if m.type=="error" and "Failed to load" not in m.text and "ERR_FAILED" not in m.text else None)
        pg.goto("http://127.0.0.1:8766/", wait_until="networkidle"); time.sleep(0.6)
        print("web label default:", pg.inner_text("#webLbl"))
        pg.click("#webBtn"); time.sleep(0.3); pg.screenshot(path=T+f"w_menu_{vw[0]}.png")
        pg.click('#webMenu button[data-web="web"]'); time.sleep(0.2)
        print("after pick:", pg.inner_text("#webLbl"), pg.eval_on_selector("#webBtn","e=>e.className"), "menu hidden:", pg.eval_on_selector("#webMenu","e=>e.classList.contains('hidden')"))
        pg.fill("#input","is the iphone 17 pro battery good? what does reddit say"); pg.keyboard.press("Enter")
        pg.wait_for_function("(document.querySelector('.wp-head')||{}).textContent?.startsWith('Searched') && !document.querySelector('.caret')", timeout=60000); time.sleep(0.5)
        print("sources cards:", pg.locator(".src").count(), "reddit cards:", pg.locator(".src.reddit").count(), "| cites:", pg.locator(".answer a.cite").count(), "| head:", pg.inner_text(".wp-head"))
        print("cite hrefs:", pg.eval_on_selector_all(".answer a.cite","els=>els.map(e=>e.textContent+'→'+e.getAttribute('href').slice(0,40))"))
        print("code untouched:", "[1] not a cite" in pg.inner_text(".answer pre"))
        pg.screenshot(path=T+f"w_ans_{vw[0]}.png")
        pg.reload(wait_until="networkidle"); time.sleep(0.6)
        if vw[0]<800: pg.click("#menuBtn") if pg.locator("#menuBtn").count() else None; time.sleep(0.3)
        pg.locator(".cl-item").first.click(); time.sleep(0.6)
        print("persisted after reload: web=", pg.inner_text("#webLbl"), "cards=", pg.locator(".src").count(), "cites=", pg.locator(".answer a.cite").count())
        print("errors:", errs or "none")
        pg.evaluate("localStorage.clear()")
        pg.close()
