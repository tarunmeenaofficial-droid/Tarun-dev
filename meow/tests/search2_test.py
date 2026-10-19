import os, time, json, re
os.environ["MEOW_CAPTIONS"]="0"
PLAN={"search": True, "queries": ["transformer attention explained"], "reddit": False, "recency": "any", "sources": ["wiki","papers","code","hn","youtube"], "images": True}
class FakeLLM:
    metadata={"tokenizer.chat_template":"<|im_start|>"}
    def n_ctx(self): return 16384
    def tokenize(self,b,add_bos=False,special=False): return list(range(len(b)//4+1))
    def detokenize(self,t): return b"x"*(len(t)*4)
    def create_completion(self, prompt, **kw):
        if "You plan web searches" in prompt: text=json.dumps(PLAN)
        elif "research planner" in prompt: text='{"queries": ["attention is all you need criticism 2026"]}'
        else: FakeLLM.last=prompt; text="Answer [1]."
        for i in range(0,len(text),8): yield {"choices":[{"text":text[i:i+8]}]}
g={"__name__":"x","llm":FakeLLM()}
exec(compile(open("/tmp/meow_tests/meow.py").read(),"meow.py","exec"), g)
os.environ["SERPER_API_KEY"]="k"; g["_SECRETS"].clear()
def fake_web(q,n=8,recency=None): return [{"title":f"Page about {q}","url":f"https://example.com/{abs(hash(q))%999}","snippet":"snip"}]
g["web_search"]=fake_web; g["_ddgs_news"]=lambda *a: []
class Tr:
    language_code="en"; is_translatable=True
    def fetch(self): return [type("S",(),{"text":f"line {i} about attention heads","start":i*20})() for i in range(8)]
class TL:
    def find_transcript(self, langs): return Tr()
    def __iter__(self): return iter([Tr()])
class YAPI:
    def list(self, vid): return TL()
import types; mod=types.ModuleType("youtube_transcript_api"); mod.YouTubeTranscriptApi=YAPI; import sys; sys.modules["youtube_transcript_api"]=mod
class R:
    def __init__(s,obj=None,text="",status=200,ct=None):
        s.status_code=status; s._obj=obj; s.text=text; s.headers={"content-type": ct or ("application/json" if obj is not None else "text/html")}; s.encoding="utf-8"; s._b=text.encode()
    def json(s): return s._obj
    def raise_for_status(s):
        if s.status_code>=400: raise RuntimeError(f"HTTP {s.status_code}")
    def iter_content(s,n): yield s._b
ART="<html><body><article>"+"<p>The attention mechanism lets each token look at every other token. Scaled dot-product attention divides by sqrt(d_k). </p>"*12+"</article></body></html>"
class Sess:
    headers={}
    def get(s,url,params=None,**k):
        if "wikipedia.org" in url:
            if params.get("list")=="search": return R({"query":{"search":[{"title":"Attention (machine learning)"}]}})
            return R({"query":{"pages":{"1":{"title":"Attention (machine learning)","fullurl":"https://en.wikipedia.org/wiki/Attention_(machine_learning)","extract":"Attention is a technique in neural networks.\n\n== History ==\nBahdanau 2014.\n\n== References ==\nlots"}}}})
        if "semanticscholar" in url: return R({"data":[{"title":"Attention Is All You Need","abstract":"We propose the Transformer.","year":2017,"citationCount":150000,"url":"https://s2/x","venue":"NeurIPS","authors":[{"name":"Vaswani"}],"tldr":{"text":"Transformers beat RNNs."}}]})
        if "arxiv.org/api" in url: return R(text="<feed><entry><id>http://arxiv.org/abs/2401.1</id><title>Efficient Attention</title><summary>Linear attention.</summary><published>2024-01-02</published><author><name>Lee</name></author></entry></feed>")
        if "api.github.com/search" in url: return R({"items":[{"full_name":"karpathy/nanoGPT","stargazers_count":40000,"description":"smallest GPT","language":"Python","pushed_at":"2026-01-01","html_url":"https://github.com/karpathy/nanoGPT"}]})
        if "api.github.com/repos" in url: return R({"full_name":"karpathy/nanoGPT","stargazers_count":40000,"language":"Python","description":"smallest GPT","pushed_at":"2026-01-01"})
        if "raw.githubusercontent" in url: return R(text="# nanoGPT\nThe simplest, fastest repository for training medium-sized GPTs.")
        if "search/advanced" in url: return R({"items":[{"question_id":1,"title":"What is attention mask?","body":"<p>How does the <code>mask</code> work?</p>","score":50,"answer_count":2,"link":"https://so/q/1","last_activity_date":1750000000}]})
        if "/questions/1/answers" in url: return R({"items":[{"question_id":1,"is_accepted":True,"score":80,"body":"<p>It hides future tokens.</p><pre><code>mask = torch.tril(...)</code></pre>"}]})
        if "hn.algolia.com/api/v1/search" in url: return R({"hits":[{"objectID":"42","title":"Transformers explained","points":500,"num_comments":120,"url":"https://blog","created_at":"2025-05-01T00:00"}]})
        if "hn.algolia.com/api/v1/items" in url: return R({"children":[{"text":"<p>Great intuition piece</p>","children":[1,2]}]})
        if "oembed" in url: return R({"title":"Attention in transformers, visually","author_name":"3Blue1Brown"})
        if "example.com" in url or "blog.site" in url: return R(text=ART)
        return R(status=404)
    def post(s,url,json=None,headers=None,**k):
        if url.endswith("/videos"): return R({"videos":[{"title":"Attention in transformers, visually","link":"https://www.youtube.com/watch?v=eMlx5fFNoYc","snippet":"3b1b","channel":"3Blue1Brown","duration":"26:10","imageUrl":"x"}]})
        if url.endswith("/images"): return R({"images":[{"imageUrl":"https://img/1.png","thumbnailUrl":"https://img/t1.png","title":"attention diagram","link":"https://src","domain":"src.com"}]})
        if url.endswith("/extract"): return R({"results":[]})
        return R(status=404)
g["_http"]=lambda: Sess()
from fastapi.testclient import TestClient
c=TestClient(g["app"])
def run(prompt, web):
    r=c.post("/api/chat",json={"prompt":prompt,"mode":"fast","web":web,"history":[],"file_ids":[],"rid":"r"+web,"chat_id":"c"})
    return [json.loads(l[6:]) for l in r.text.split("\n") if l.startswith("data: {")]
t=time.time(); ev=run("explain transformer attention","deep")
print(f"{time.time()-t:.1f}s stages:", [e["search"]["stage"] for e in ev if "search" in e])
print("statuses:", [e["status"] for e in ev if e.get("status")])
print("images:", [i["thumb"] for e in ev if "images" in e for i in e["images"]])
for s in [s for e in ev if "sources" in e for s in e["sources"]]: print("  ", s["n"], s["kind"], s["domain"], s["title"][:50])
p=FakeLLM.last; blk=p[p.find("<web_results searched"):]
print("transcript ts:", "[0:40]" in blk or "[1:00]" in blk, "| wiki refs stripped:", "lots" not in blk, "| SO accepted:", "ACCEPTED ANSWER" in blk, "| hn:", "Great intuition" in blk, "| 2nd round q:", "criticism" in blk)
# links only, web off
ev=run("summarise this video https://youtu.be/eMlx5fFNoYc and this https://github.com/karpathy/nanoGPT","off")
print("links stages:", [e["search"]["stage"] for e in ev if "search" in e])
for s in [s for e in ev if "sources" in e for s in e["sources"]]: print("  ", s["n"], s["kind"], s["title"][:50])
p=FakeLLM.last; print("link text in prompt:", "VIDEO TRANSCRIPT" in p, "nanoGPT" in p, "| rules:", "Link you shared" in p)
ev=run("hello there","off"); print("plain chat search events:", [e for e in ev if "search" in e])
