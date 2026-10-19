import os, time, json, re
os.environ["MEOW_CAPTIONS"]="0"
PLAN={"search": True, "queries": ["iphone 17 pro battery life review 2026", "iphone 17 pro vs pixel 10 pro battery"], "reddit": True, "recency": "year"}
ANSWER="The iPhone 17 Pro lasts about 31 hours of video playback [1], and Redditors mostly say it easily lasts a full day [3][4]. Pixel trails slightly [2]."
class FakeLLM:
    metadata={"tokenizer.chat_template":"<|im_start|>"}
    def n_ctx(self): return 16384
    def tokenize(self,b,add_bos=False,special=False): return list(range(len(b)//4+1))
    def detokenize(self,t): return b"x"*(len(t)*4)
    def create_completion(self, prompt, **kw):
        if "You plan web searches" in prompt: text=json.dumps(PLAN)
        else:
            FakeLLM.last=prompt; text=ANSWER
        for i in range(0,len(text),8): yield {"choices":[{"text":text[i:i+8]}]}
g={"__name__":"x","llm":FakeLLM()}
exec(compile(open("/tmp/meow_tests/meow.py").read(),"meow.py","exec"), g)
# ---- mock network
PAGES={"https://www.apple.com/iphone-17-pro/specs/":"<html><head><title>iPhone 17 Pro - Specs</title></head><body><nav>menu menu</nav><article><h1>iPhone 17 Pro Technical Specifications</h1>"+"<p>Battery: Up to 31 hours video playback on iPhone 17 Pro. The A19 Pro chip is efficient and the battery life is excellent for most users all day long.</p>"*3+"<p>Unrelated paragraph about colours and finishes available in titanium and aluminium in many regions of the world.</p>"*4+"</article></body></html>",
       "https://www.gsmarena.com/pixel_10_pro-review.php":"<html><body><article><p>Pixel 10 Pro battery life review: the Tensor G5 phone scored 14 hours in our active use test which trails the iPhone 17 Pro battery by around an hour.</p>"*3+"</article></body></html>"}
def fake_web(q,n=8,recency=None):
    if "site:reddit.com" in q:
        return [{"title":"iPhone 17 Pro battery after 1 month : r/iphone","url":"https://www.reddit.com/r/iphone/comments/abc123/iphone_17_pro_battery_after_1_month/","snippet":"Getting 8h SOT"}]
    return [{"title":"iPhone 17 Pro - Technical Specifications - Apple","url":"https://www.apple.com/iphone-17-pro/specs/","snippet":"Up to 31 hours video playback"},
            {"title":"Pixel 10 Pro review: Battery life","url":"https://www.gsmarena.com/pixel_10_pro-review.php","snippet":"14 hours active use"},
            {"title":"iPhone 17 Pro video","url":"https://www.youtube.com/watch?v=xyz","snippet":"video review"}]
g["web_search"]=fake_web
g["_ddgs_news"]=lambda q,n,r: []
class R:
    def __init__(s,html_,ct="text/html; charset=utf-8"): s.status_code=200; s.headers={"content-type":ct}; s._b=html_.encode(); s.encoding="utf-8"
    def iter_content(s,n): yield s._b
class Sess:
    headers={}
    def get(s,url,**k):
        if url in PAGES: return R(PAGES[url])
        r=R(""); r.status_code=404; return r
g["_http"]=lambda: Sess()
REDDIT_SEARCH={"data":{"children":[{"kind":"t3","data":{"title":"Is the 17 Pro battery actually better?","permalink":"/r/apple/comments/zzz999/is_the_17_pro_battery_actually_better/","subreddit":"apple","score":842,"num_comments":311,"created_utc":1757000000,"selftext":"Coming from a 15 Pro","id":"zzz999"}}]}}
def thread_json(tid):
    post={"title":"t","permalink":f"/r/x/comments/{tid}/t/","subreddit":"apple" if tid=="zzz999" else "iphone","score":842,"num_comments":311,"created_utc":1757000000,"selftext":"Coming from a 15 Pro, battery seems way better.","id":tid}
    cm=[{"kind":"t1","data":{"body":"Easily a full day, 8-9 hours screen on time for me.","score":523,"replies":{"data":{"children":[{"kind":"t1","data":{"body":"Same here, ends day at 30%.","score":120}}]}}}},
        {"kind":"t1","data":{"body":"[deleted]","score":50,"replies":""}},
        {"kind":"t1","data":{"body":"Mine drains fast with 5G, maybe 6 hours.","score":210,"replies":""}},
        {"kind":"more","data":{}}]
    return [{"data":{"children":[{"data":post}]}},{"data":{"children":cm}}]
def fake_reddit_get(path, params=None, timeout=10):
    if path=="/search": return REDDIT_SEARCH
    m=re.match(r"/comments/(\w+)",path); return thread_json(m.group(1))
g["_reddit_get"]=fake_reddit_get
from fastapi.testclient import TestClient
c=TestClient(g["app"])
def run(prompt, web, mode="fast"):
    t=time.time(); r=c.post("/api/chat",json={"prompt":prompt,"mode":mode,"web":web,"history":[],"file_ids":[],"rid":"r"+web})
    ev=[json.loads(l[6:]) for l in r.text.split("\n") if l.startswith("data: {")]
    return ev, time.time()-t
ev,dt=run("is iphone 17 pro battery good? what does reddit say","auto")
st=[e["search"]["stage"] for e in ev if "search" in e]; src=[e for e in ev if "sources" in e]
print("auto stages:", st, f"{dt:.1f}s")
S=src[0]["sources"] if src else []
for s in S: print("  ", s["n"], s["kind"], s["domain"], s.get("sub"), s.get("score"), s["title"][:50])
p=FakeLLM.last
print("prompt has web_results:", "<web_results" in p, "| rules:", "WEB SEARCH —" in p, "| comments:", "COMMENT (▲523)" in p, "| reply:", "REPLY (▲120)" in p, "| deleted skipped:", "[deleted]" not in p)
print("apple passage:", "31 hours" in p, "| youtube skipped (snippet only):", "video review" in p)
print("answer streamed:", "".join(e.get("t","") for e in ev).strip()[:60])
ev,_=run("write me a poem about cats","auto"); print("auto poem → search events:", [e for e in ev if "search" in e or "sources" in e])
ev,_=run("hello","off"); print("off → search events:", [e for e in ev if "search" in e])
PLAN={"search": False, "queries": [], "reddit": False, "recency":"any"}
ev,_=run("what is the latest news today","auto"); print("planner says no →", [e["search"]["stage"] for e in ev if "search" in e])
PLAN={"search": True, "queries": ["best budget mechanical keyboard 2026"], "reddit": False, "recency":"any"}
ev,_=run("best budget mechanical keyboard","reddit"); print("reddit mode:", [ (s["kind"],s.get("sub")) for e in ev if "sources" in e for s in e["sources"]])
# failure path: engines down
g["web_search"]=lambda *a,**k: []
g["_reddit_get"]=lambda *a,**k: (_ for _ in ()).throw(RuntimeError("blocked"))
ev,_=run("latest gpu prices","web"); print("all down →", [e["search"]["stage"] for e in ev if "search" in e], "| ctx note:", "returned nothing usable" in FakeLLM.last)
# respace/ranking sanity
print("rank:", g["rank_passages"](["battery"],[{"chunks":["battery battery life","colours"],"order":0},{"chunks":["nothing here","battery test"],"order":1}],500))
g["web_search"]=fake_web; g["_reddit_get"]=fake_reddit_get
PLAN={"search": True, "queries": ["iphone 17 pro battery"], "reddit": True, "recency": "year"}
run("iphone 17 pro battery reddit","auto")
p=FakeLLM.last; i=p.find("<web_results searched"); print(p[i:p.find("</web_results>")+15][:2500])
