import os, threading, time, json, re
os.environ["MEOW_CAPTIONS"]="0"
ANS = {}
class FakeLLM:
    metadata={"tokenizer.chat_template":"<|im_start|>"}
    def n_ctx(self): return 16384
    def tokenize(self,b,add_bos=False,special=False): return list(range(len(b)//4+1))
    def detokenize(self,t): return b"x"*(len(t)*4)
    def create_completion(self, prompt, **kw):
        user = prompt.split("<|im_start|>user\n")[-1].split("<|im_end|>")[0]
        tail = prompt.split("<|im_start|>assistant\n")[-1]
        if "chart" in user:
            if "meow-output" not in tail:
                text = "I'll compute it.\n\n```meow-python\nimport matplotlib.pyplot as plt\nxs=list(range(10))\nplt.plot(xs,[x*x for x in xs]); plt.title('Squares')\nsum(x*x for x in xs)\n```\nTRAILING"
            else:
                text = "The sum of squares 0–9 is **285**, and the chart is above.\n\n<<followups: What about cubes? | Plot it on a log scale | Explain the formula>>"
        elif "diagram" in user:
            text = "Here's the flow:\n\n```mermaid\ngraph TD\n  A[Upload] --> B{PDF?}\n  B -->|yes| C[Edit]\n  B -->|no| D[Convert]\n```\n\nAnd a demo page:\n\n```html\n<h1 style='color:purple'>Hello Meow</h1><button onclick=\"this.textContent='clicked'\">Click</button>\n```"
        else:
            text = f"You said: {user[-40:]}"
        for i in range(0,len(text),6):
            time.sleep(0.003); yield {"choices":[{"text":text[i:i+6]}]}
g={"__name__":"x","llm":FakeLLM()}
exec(compile(open("/tmp/meow_tests/meow.py").read(),"meow.py","exec"), g)
import uvicorn
srv=uvicorn.Server(uvicorn.Config(g["app"],host="127.0.0.1",port=8767,log_level="warning"))
threading.Thread(target=srv.run,daemon=True).start(); time.sleep(1.5)
from playwright.sync_api import sync_playwright
proxy=os.environ.get("HTTPS_PROXY"); L="/tmp/meow_tests/libs/"
MAP={"marked.min.js":L+"marked-12.0.2/package/marked.min.js","purify.min.js":L+"dompurify-3.1.6/package/dist/purify.min.js","highlight.min.js":L+"hl/package/highlight.min.js","atom-one-dark.min.css":L+"hl/package/styles/atom-one-dark.min.css","katex.min.js":L+"katex-0.16.9/package/dist/katex.min.js","katex.min.css":L+"katex-0.16.9/package/dist/katex.min.css","mermaid.min.js":L+"mm/package/dist/mermaid.min.js"}
def rt(r):
    u=r.request.url
    for k,v in MAP.items():
        if u.split("?")[0].endswith(k): return r.fulfill(path=v)
    if "127.0.0.1" in u: return r.continue_()
    return r.abort()
T="/tmp/meow_tests/"
def done(pg): pg.wait_for_function("!document.querySelector('.caret') && document.getElementById('sendBtn').title==='Send'", timeout=60000); time.sleep(0.5)
with sync_playwright() as p:
    b=p.chromium.launch(args=["--ignore-certificate-errors", f"--proxy-server={proxy}", "--proxy-bypass-list=127.0.0.1;localhost;<loopback>"])
    pg=b.new_page(viewport={"width":1440,"height":1000}); pg.route("**/*", rt)
    errs=[]; pg.on("pageerror", lambda e: errs.append("PAGEERR "+str(e)[:300])); pg.on("console", lambda m: errs.append(m.text) if m.type=="error" and "Failed to load" not in m.text and "ERR_FAILED" not in m.text else None)
    pg.goto("http://127.0.0.1:8767/", wait_until="networkidle"); time.sleep(0.6)
    pg.click('#webMenu button[data-web="off"]', force=True) if False else None
    pg.fill("#input","make a chart of squares"); pg.keyboard.press("Enter"); done(pg)
    print("py code block:", pg.locator("pre.py-code").count(), "| output:", pg.locator("pre.py-out").count(), pg.inner_text("pre.py-out code")[:30].replace("\n"," "), "| chart img:", pg.locator(".answer img").count(),
          "| TRAILING removed:", "TRAILING" not in pg.inner_text(".answer"))
    print("followups:", pg.locator(".fup").count(), "| raw marker hidden:", "<<followups" not in pg.inner_text(".answer"))
    pg.screenshot(path=T+"u6_python.png", full_page=True)
    nat=pg.eval_on_selector(".answer img","e=>e.naturalWidth"); print("chart loaded px:", nat)
    pg.locator(".fup").first.click(); done(pg)
    print("followup sent:", pg.locator(".msg.user").count(), pg.locator(".msg.user .bubble").last.inner_text())
    # edit message
    pg.locator(".msg.user").last.hover(); pg.locator(".msg.user").last.locator('[data-act="edit-user"]').click(); time.sleep(0.2)
    print("edit bar visible:", pg.is_visible("#editBar"), "| input:", pg.input_value("#input"))
    pg.fill("#input","draw a diagram please"); pg.keyboard.press("Enter"); done(pg); pg.wait_for_selector(".mermaid-box svg", timeout=20000)
    print("mm pre labels:", pg.eval_on_selector_all(".answer pre .code-bar span:first-child","els=>els.map(e=>e.textContent)"), "mermaid global:", pg.evaluate("typeof window.mermaid"))
    print("after edit msgs:", pg.locator(".msg.user").count(), pg.locator(".msg.assistant").count(), "| mermaid svg:", pg.locator(".mermaid-box svg").count())
    pg.locator('[data-act="preview-html"]').first.click(); time.sleep(0.6)
    fr=pg.frame_locator("#htmlPrev iframe"); print("preview h1:", fr.locator("h1").inner_text())
    fr.locator("button").click(); print("preview js works:", fr.locator("button").inner_text())
    pg.screenshot(path=T+"u6_preview.png"); pg.click('[data-hp="close"]')
    pg.screenshot(path=T+"u6_diagram.png", full_page=True)
    # voice overlay
    pg.click("#voiceBtn"); time.sleep(0.4); print("voice overlay:", pg.is_visible("#voiceOv"), pg.inner_text("#voState")); pg.screenshot(path=T+"u6_voice.png")
    pg.keyboard.press("Escape"); time.sleep(0.2); print("voice closed:", not pg.is_visible("#voiceOv"))
    m=b.new_page(viewport={"width":390,"height":844}, has_touch=True, is_mobile=True); m.route("**/*", rt)
    m.goto("http://127.0.0.1:8767/", wait_until="networkidle"); time.sleep(0.5)
    print("mobile cam btn visible:", m.is_visible("#camBtn")); m.screenshot(path=T+"u6_mobile.png")
    print("errors:", errs or "none")
