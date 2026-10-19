import os, time, json, re
os.environ["MEOW_CAPTIONS"]="0"
PLAN={"search": True, "queries": ["is macbook air m4 worth it for cs students", "macbook air m4 vs thinkpad for programming"], "reddit": True, "recency": "any"}
class FakeLLM:
    metadata={"tokenizer.chat_template":"<|im_start|>"}
    def n_ctx(self): return 16384
    def tokenize(self,b,add_bos=False,special=False): return list(range(len(b)//4+1))
    def detokenize(self,t): return b"x"*(len(t)*4)
    def create_completion(self, prompt, **kw):
        if "You plan web searches" in prompt: FakeLLM.plan_prompt=prompt; text=json.dumps(PLAN)
        elif "You check research" in prompt:
            FakeLLM.judge=getattr(FakeLLM,"judge",0)+1; FakeLLM.judge_prompt=prompt
            text=json.dumps({"answered": FakeLLM.judge>1, "missing":"long-term reliability reports", "queries":["macbook air m4 after 1 year cs"], "subreddits":["mac","r/learnprogramming"]})
        else: FakeLLM.last=prompt; text="Redditors mostly say yes [1][2]."
        for i in range(0,len(text),8): yield {"choices":[{"text":text[i:i+8]}]}
g={"__name__":"x","llm":FakeLLM()}
exec(compile(open("/tmp/meow_tests/meow.py").read(),"meow.py","exec"), g)
os.environ["TAVILY_API_KEY"]="tvly-test"; g["_SECRETS"].clear()
CALLS=[]
def hit(sub, tid, title): return {"title": f"{title} : r/{sub}", "url": f"https://www.reddit.com/r/{sub}/comments/{tid}/{title.lower().replace(' ','_')}/", "snippet": f"{title} snippet"}
def fake_web(q,n=8,recency=None):
    CALLS.append(("web",q))
    if "after 1 year" in q or "/r/mac" in q:
        return [hit("mac","eee555","M4 Air one year later"), hit("learnprogramming","fff666","Air for coding long term")]
    if "site:reddit.com" in q or q.endswith(" reddit"):
        return [hit("macbookair","aaa111","M4 Air for CS degree"), hit("cscareerquestions","bbb222","Mac or Windows for CS"), {"title":"x","url":"https://www.reddit.com/r/apple/","snippet":""}]
    return [{"title":"MacBook Air M4 review","url":"https://www.theverge.com/m4-air-review","snippet":"great battery"}]
g["web_search"]=fake_web
def blocked(*a,**k): raise RuntimeError("Reddit blocked the request (HTTP 403)")
g["_reddit_get"]=blocked
TREE={"data":[
 {"kind":"t1","data":{"body":"Got it for my CS degree, 16GB is plenty for VS Code, Docker is the only pain.","score":412,"author":"rahul_dev","replies":{"kind":"Listing","data":{"children":[
    {"kind":"t1","data":{"body":"Docker on Apple silicon is fine now honestly.","score":88,"replies":{"kind":"Listing","data":{"children":[{"kind":"t1","data":{"body":"Agreed, colima works great.","score":30,"replies":""}}]}}}},
    {"kind":"t1","data":{"body":"[removed]","score":5,"replies":""}}]}}}},
 {"kind":"t1","data":{"body":"I have been using it for 8 months, made ₹40k freelancing on it.","score":233,"author":"b","replies":""}},
 {"kind":"t1","data":{"body":"I am a bot","score":1,"author":"AutoModerator","replies":""}},
 {"kind":"more","data":{"children":["x"]}}]}
class R:
    def __init__(s,obj=None,html_=None,status=200):
        s.status_code=status; s._obj=obj; s.headers={"content-type":"application/json" if obj is not None else "text/html"}; s.encoding="utf-8"; s._b=(html_ or "").encode()
    def json(s): return s._obj
    def raise_for_status(s):
        if s.status_code>=400: raise RuntimeError(f"HTTP {s.status_code}")
    def iter_content(s,n): yield s._b
class Sess:
    headers={}
    def get(s,url,params=None,**k):
        CALLS.append(("get",url,dict(params or {})))
        if url.endswith("/api/posts/search"):
            return R({"data":[{"id":"ccc333","title":"Macbook air m4 worth it? (CS student)","subreddit":"macbookair","score":150,"num_comments":97,"created_utc":1750000000,"selftext":"Starting uni","permalink":"/r/macbookair/comments/ccc333/m4_worth_it/"}]})
        if url.endswith("/api/posts/ids"):
            i=params["ids"]; return R({"data":[{"id":i,"title":f"Thread {i}","subreddit":"macbookair" if i!="bbb222" else "cscareerquestions","score":300,"num_comments":120,"created_utc":1755000000,"selftext":f"Body of {i}","permalink":f"/r/x/comments/{i}/t/"}]})
        if url.endswith("/api/comments/tree"):
            if params["link_id"]=="t3_bbb222": return R(status=500)   # archive fails for this one → Tavily
            return R(TREE)
        if url.endswith("/api/comments/search"):
            return R({"data":[{"body":"I've used the M4 Air for a full semester of CS, compiling Java and running Docker; zero issues and 15h battery.","score":64,"subreddit":params["subreddit"],"created_utc":1758000000,"permalink":f"/r/{params['subreddit']}/comments/zzz/t/c1/"}]})
        if "theverge" in url: return R(html_="<html><body><article><p>"+"The MacBook Air M4 battery and performance review for students and programmers. "*20+"</p></article></body></html>")
        return R(status=404)
    def post(s,url,json=None,headers=None,**k):
        CALLS.append(("post",url))
        if url.endswith("/search"): return R({"results":[{"title":"Best laptop CS : r/learnprogramming","url":"https://www.reddit.com/r/learnprogramming/comments/ddd444/best_laptop/","content":"mac vs linux"}]})
        if url.endswith("/extract"):
            return R({"results":[{"url":u,"raw_content":"r/cscareerquestions\nMac or Windows for CS\nReply\nShare\n5h ago\nMac is fine, most of the industry uses Macs or Linux for development.\nvote\n12 points\nWindows with WSL2 is also fine if you're on a budget."} for u in json["urls"]]})
        return R(status=404)
g["_http"]=lambda: Sess()
from fastapi.testclient import TestClient
c=TestClient(g["app"])
t=time.time()
r=c.post("/api/chat",json={"prompt":"is the macbook air m4 good for a CS student? what does reddit think","mode":"fast","web":"reddit","history":[],"file_ids":[],"rid":"x"})
ev=[json.loads(l[6:]) for l in r.text.split("\n") if l.startswith("data: {")]
print(f"took {time.time()-t:.1f}s; stages:", [e["search"]["stage"] for e in ev if "search" in e])
print("statuses:", [e["status"] for e in ev if e.get("status")])
src=[s for e in ev if "sources" in e for s in e["sources"]]
for s in src: print("  ", s["n"], s["kind"], s.get("sub"), s.get("score"), s.get("comments"), s["title"][:55])
p=FakeLLM.last; blk=p[p.find("<web_results searched"):p.find("</web_results>")]
print("reddit-style planner hint:", "phrased like Reddit post titles" in FakeLLM.plan_prompt)
print("web pages skipped in reddit mode:", "theverge" not in blk)
print("nested reply levels:", "↳ REPLY (▲88)" in blk, "↳ (▲30)" in blk, "| removed/automod skipped:", "[removed]" not in blk and "I am a bot" not in blk)
print("tavily fallback used for blocked thread:", "WSL2" in blk, "| junk lines cleaned:", "\nReply\n" not in blk)
print("deep comment search block:", "More comments in r/" in blk, "| archive found thread:", "ccc333" in blk)
print("sources searched:", sorted(set(x[1].split('/')[-1] if x[0]!='web' else 'serper:'+x[1][:30] for x in CALLS))[:12])
print("judge calls:", FakeLLM.judge, "| evidence in judge:", "COMMENT" not in FakeLLM.judge_prompt and "(▲" in FakeLLM.judge_prompt)
print("round-2 thread used:", "eee555" in blk or "fff666" in blk, "| stage seq:", [ (e["search"]["stage"], e["search"].get("round"), e["search"].get("rounds")) for e in ev if "search" in e])
print("statuses2:", [e["status"] for e in ev if e.get("status")])
i=blk.find("COMMENT"); print(blk[:1500])
