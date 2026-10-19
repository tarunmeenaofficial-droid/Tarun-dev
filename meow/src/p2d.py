
# ==========================================================
# WEB + REDDIT SEARCH (Perplexity / ChatGPT-search style)
#   plan queries with the model → search in parallel → read the best pages and Reddit threads
#   → keep only the most relevant passages → answer with numbered citations [1] [2]
# Works free out of the box (DuckDuckGo/Bing/Brave via the `ddgs` package + Reddit's public JSON).
# Optional keys (env vars or Kaggle → Add-ons → Secrets) for better results:
#   SERPER_API_KEY (Google results, 2,500 free) · BRAVE_API_KEY · TAVILY_API_KEY
#   REDDIT_CLIENT_ID + REDDIT_CLIENT_SECRET (free "script" app at reddit.com/prefs/apps — fixes Reddit blocking cloud IPs)
# ==========================================================
import math
import concurrent.futures as _cf
from urllib.parse import urlparse, quote_plus

def _ensure_web_pkgs():
    import importlib.util, subprocess, sys
    need = {"ddgs": "ddgs", "trafilatura": "trafilatura", "youtube_transcript_api": "youtube-transcript-api"}
    miss = [pkg for mod, pkg in need.items() if importlib.util.find_spec(mod) is None]
    if miss:
        print("📦 installing", " ".join(miss), "for web search…")
        subprocess.run([sys.executable, "-m", "pip", "install", "-q", *miss], check=False)


_ensure_web_pkgs()
FEATURES["web"] = True
WEB_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
REDDIT_UA = "python:meow-assistant:v1.0 (personal research bot)"
SKIP_FETCH = ("youtube.com", "youtu.be", "facebook.com", "instagram.com", "tiktok.com", "x.com", "twitter.com",
              "linkedin.com", "pinterest.", "quora.com")
_SECRETS = {}


def _secret(name):
    if name in _SECRETS: return _SECRETS[name]
    v = os.environ.get(name, "").strip() or str(globals().get(name) or "").strip()
    if not v:
        try:
            from kaggle_secrets import UserSecretsClient
            v = (UserSecretsClient().get_secret(name) or "").strip()
        except Exception:
            v = ""
    _SECRETS[name] = v
    return v


def _domain(u):
    try: return urlparse(u).netloc.lower().removeprefix("www.")
    except Exception: return ""


def _norm_url(u):
    p = urlparse(u); host = p.netloc.lower().removeprefix("www.").removeprefix("old.").removeprefix("m.")
    return host + p.path.rstrip("/")


def _http():
    import requests
    s = requests.Session(); s.headers.update({"User-Agent": WEB_UA, "Accept-Language": "en-US,en;q=0.9"})
    return s


# ---------- search engines ----------
def _ddgs_text(q, n, recency):
    from ddgs import DDGS
    tl = {"day": "d", "week": "w", "month": "m", "year": "y"}.get(recency)
    out = []
    for r in DDGS(timeout=8).text(q, max_results=n, timelimit=tl, region="us-en") or []:
        if r.get("href"): out.append({"title": r.get("title", ""), "url": r["href"], "snippet": r.get("body", "")})
    return out


def _ddgs_news(q, n, recency):
    from ddgs import DDGS
    tl = {"day": "d", "week": "w", "month": "m"}.get(recency, "m")
    out = []
    for r in DDGS(timeout=8).news(q, max_results=n, timelimit=tl) or []:
        if r.get("url"): out.append({"title": r.get("title", ""), "url": r["url"], "snippet": r.get("body", ""),
                                     "date": (r.get("date") or "")[:10], "kind": "news", "site": r.get("source", "")})
    return out


def _serper(q, n, recency):
    key = _secret("SERPER_API_KEY")
    if not key: return None
    body = {"q": q, "num": n}
    if recency in ("day", "week", "month", "year"): body["tbs"] = "qdr:" + recency[0]
    r = _http().post("https://google.serper.dev/search", json=body, headers={"X-API-KEY": key}, timeout=10)
    r.raise_for_status(); j = r.json(); out = []
    if j.get("answerBox", {}).get("answer") or j.get("answerBox", {}).get("snippet"):
        ab = j["answerBox"]; out.append({"title": ab.get("title", "Google answer"), "url": ab.get("link", "https://google.com"),
                                         "snippet": ab.get("answer") or ab.get("snippet", "")})
    for it in j.get("organic", []):
        out.append({"title": it.get("title", ""), "url": it.get("link", ""), "snippet": it.get("snippet", ""), "date": it.get("date", "")})
    return [o for o in out if o["url"]]


def _brave(q, n, recency):
    key = _secret("BRAVE_API_KEY")
    if not key: return None
    params = {"q": q, "count": min(n, 20)}
    if recency in ("day", "week", "month", "year"): params["freshness"] = {"day": "pd", "week": "pw", "month": "pm", "year": "py"}[recency]
    r = _http().get("https://api.search.brave.com/res/v1/web/search", params=params,
                    headers={"X-Subscription-Token": key, "Accept": "application/json"}, timeout=10)
    r.raise_for_status()
    return [{"title": it.get("title", ""), "url": it.get("url", ""), "snippet": re.sub(r"<[^>]+>", "", it.get("description", "")),
             "date": it.get("age", "")} for it in r.json().get("web", {}).get("results", []) if it.get("url")]


def _tavily(q, n, recency):
    key = _secret("TAVILY_API_KEY")
    if not key: return None
    body = {"api_key": key, "query": q, "max_results": min(n, 10), "search_depth": "advanced"}
    if recency in ("day", "week"): body["topic"] = "news"; body["days"] = 1 if recency == "day" else 7
    r = _http().post("https://api.tavily.com/search", json=body, timeout=15)
    r.raise_for_status()
    return [{"title": it.get("title", ""), "url": it.get("url", ""), "snippet": it.get("content", ""),
             "date": (it.get("published_date") or "")[:10]} for it in r.json().get("results", []) if it.get("url")]


def web_search(q, n=8, recency=None):
    """Best available engine first; the free ddgs metasearch is the fallback."""
    errs = []
    for eng in (_serper, _brave, _tavily, _ddgs_text):
        try:
            res = eng(q, n, recency)
            if res: return res
        except Exception as e:
            errs.append(f"{eng.__name__}: {e}")
    if errs: print("⚠️  web search:", " | ".join(errs)[:300])
    return []


# ---------- Reddit (deep) ----------
# Finding threads:  official search (if keys) + Google/Serper "site:reddit.com" + Tavily (reddit.com only) + Arctic Shift archive
# Reading threads:  official API (if keys) → public JSON → Arctic Shift archive (free, no key) → Tavily Extract (your Tavily key)
ARCTIC = "https://arctic-shift.photon-reddit.com"
_REDDIT_TOKEN = {"tok": None, "exp": 0}
_BAD_BODY = ("", "[deleted]", "[removed]")


def _reddit_get(path, params=None, timeout=10):
    """GET a Reddit JSON endpoint: OAuth app if configured (works from cloud IPs), else public JSON."""
    s = _http(); s.headers["User-Agent"] = REDDIT_UA
    params = dict(params or {}, raw_json=1)
    cid, csec = _secret("REDDIT_CLIENT_ID"), _secret("REDDIT_CLIENT_SECRET")
    if cid and csec:
        if not _REDDIT_TOKEN["tok"] or time.time() > _REDDIT_TOKEN["exp"]:
            r = s.post("https://www.reddit.com/api/v1/access_token", auth=(cid, csec),
                       data={"grant_type": "client_credentials"}, timeout=timeout)
            r.raise_for_status(); j = r.json()
            _REDDIT_TOKEN.update(tok=j["access_token"], exp=time.time() + int(j.get("expires_in", 3600)) - 60)
        r = s.get("https://oauth.reddit.com" + path, params=params, headers={"Authorization": "bearer " + _REDDIT_TOKEN["tok"]}, timeout=timeout)
        r.raise_for_status(); return r.json()
    if time.time() < _REDDIT_TOKEN.get("blocked_until", 0):
        raise RuntimeError("Reddit is blocking this server right now (using the archive instead)")
    last = None
    for host in ("https://www.reddit.com", "https://old.reddit.com"):
        try:
            r = s.get(host + path.rstrip("/") + ".json", params=params, timeout=timeout)
            if r.status_code == 200 and r.headers.get("content-type", "").startswith("application/json"): return r.json()
            last = f"HTTP {r.status_code}"
            if r.status_code in (403, 429):                    # blocked for this server — stop trying for 10 minutes
                _REDDIT_TOKEN["blocked_until"] = time.time() + 600; break
        except Exception as e:
            last = str(e)
    raise RuntimeError(f"Reddit blocked the request ({last})")


def _arctic(path, params, timeout=15):
    """Arctic Shift: a free public Reddit archive (posts + full comment trees, no key)."""
    last = None
    for attempt in range(2):
        try:
            r = _http().get(ARCTIC + path, params=params, timeout=timeout)
            if r.status_code == 200:
                j = r.json()
                if isinstance(j, dict) and j.get("error"): raise RuntimeError(str(j["error"])[:120])
                return j.get("data", j) if isinstance(j, dict) else j
            last = f"HTTP {r.status_code}"
        except Exception as e:
            last = str(e)
        time.sleep(1.5)
    raise RuntimeError(f"archive unavailable ({last})")


def _date(ts):
    try: return datetime.datetime.fromtimestamp(float(ts), datetime.timezone.utc).strftime("%Y-%m-%d")
    except Exception: return ""


def _thread_of(d):
    sub = d.get("subreddit", ""); pid = d.get("id", "")
    link = d.get("permalink") or (f"/r/{sub}/comments/{pid}/" if sub and pid else "")
    return {"title": d.get("title", ""), "url": "https://www.reddit.com" + link, "kind": "reddit",
            "sub": sub, "score": d.get("score"), "comments": d.get("num_comments"),
            "date": _date(d.get("created_utc")) if d.get("created_utc") else "",
            "snippet": (d.get("selftext") or "")[:300], "id": pid}


def _tid(url):
    m = re.search(r"/comments/([a-z0-9]+)", url or ""); return m.group(1) if m else ""


def _from_hit(r):
    m = re.search(r"reddit\.com/r/([^/]+)/comments/([a-z0-9]+)", r["url"])
    return {"title": re.sub(r"\s*[:\-|]\s*r/\w+.*$", "", r.get("title", "")).strip(), "url": r["url"].split("?")[0], "kind": "reddit",
            "sub": m.group(1) if m else "", "id": m.group(2) if m else "", "score": None, "comments": None,
            "date": r.get("date", ""), "snippet": r.get("snippet", "")}


def _tavily_reddit(q, n):
    key = _secret("TAVILY_API_KEY")
    if not key: return []
    r = _http().post("https://api.tavily.com/search", json={"api_key": key, "query": q, "max_results": min(n, 10),
                     "include_domains": ["reddit.com"]}, headers={"Authorization": "Bearer " + key}, timeout=15)
    r.raise_for_status()
    return [{"title": it.get("title", ""), "url": it.get("url", ""), "snippet": it.get("content", "")} for it in r.json().get("results", [])]


def reddit_search(q, n=6, recency=None, deep=False, subs=None):
    """Find the best threads for `q` across ALL of Reddit using every source at once; threads that several
    sources agree on rank first, then engagement (comments / upvotes)."""
    t = {"day": "day", "week": "week", "month": "month", "year": "year"}.get(recency, "all")
    kw = " ".join(_terms(q)[:5])

    def official():
        j = _reddit_get("/search", {"q": q, "sort": "relevance", "t": t, "limit": 25, "type": "link"}, timeout=8)
        return [_thread_of(c["data"]) for c in j.get("data", {}).get("children", []) if not c.get("data", {}).get("over_18")]

    def google():
        out = []
        qqs = [f"{q} site:reddit.com/r/{s}" for s in (subs or [])[:2]] or [f"{q} site:reddit.com"]
        if deep and kw and not subs: qqs.append(f"{kw} reddit")
        for qq in qqs:
            out += [_from_hit(r) for r in web_search(qq, 10 if deep else 8, "year" if recency == "year" else None)
                    if "reddit.com/r/" in r["url"] and "/comments/" in r["url"]]
        return out

    def tavily():
        return [_from_hit(r) for r in _tavily_reddit(q, 10) if "/comments/" in r["url"]]

    def archive():
        if not kw: return []
        p = {"title": kw, "limit": 25, "sort": "desc", "fields": "id,title,subreddit,score,num_comments,created_utc,selftext,permalink,over_18"}
        if subs: p["subreddit"] = subs[0]
        if recency in ("day", "week", "month", "year"):
            p["after"] = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days={"day": 2, "week": 8, "month": 32, "year": 370}[recency])).strftime("%Y-%m-%d")
        return [_thread_of(d) for d in (_arctic("/api/posts/search", p) or []) if isinstance(d, dict) and not d.get("over_18")]

    found = {}
    with _cf.ThreadPoolExecutor(4) as ex:
        futs = {ex.submit(fn): name for name, fn in (("official", official), ("google", google), ("tavily", tavily), ("archive", archive))}
        try:
            for f in _cf.as_completed(futs, timeout=25):
                try:
                    res = f.result() or []
                except Exception as e:
                    print(f"⚠️  reddit {futs[f]}:", str(e)[:140]); continue
                for pos, th in enumerate(res):
                    key = th.get("id") or _norm_url(th["url"])
                    if not key: continue
                    cur = found.get(key)
                    if cur is None:
                        found[key] = {**th, "_votes": 1, "_pos": pos}
                    else:
                        cur["_votes"] += 1; cur["_pos"] = min(cur["_pos"], pos)
                        for k_, v in th.items():
                            if cur.get(k_) in (None, "") and v not in (None, ""): cur[k_] = v
        except _cf.TimeoutError:
            print("⚠️  some Reddit searches were too slow — skipped")
    out = list(found.values())
    for th in out:
        th["_rank"] = th["_pos"] - 2.0 * (th["_votes"] - 1) - 0.6 * math.log1p(th.get("comments") or 0) - 0.3 * math.log1p(max(0, th.get("score") or 0))
    return sorted(out, key=lambda th: th["_rank"])[:n]


def _walk_comments(nodes, depth=0, out=None, max_depth=3):
    """Flatten a Reddit-style comment listing (official API or archive) into dicts with replies attached."""
    out = [] if out is None else out
    if isinstance(nodes, dict): nodes = nodes.get("data", {}).get("children", nodes.get("children", []))
    for n in nodes or []:
        if not isinstance(n, dict) or n.get("kind") == "more": continue
        d = n.get("data", n)
        body = (d.get("body") or "").strip()
        if body in _BAD_BODY or d.get("stickied") or d.get("author") == "AutoModerator": continue
        c = {"score": d.get("score") or 0, "body": body, "depth": depth, "replies": [], "author": d.get("author") or ""}
        rep = d.get("replies")
        if rep and depth < max_depth: _walk_comments(rep, depth + 1, c["replies"], max_depth)
        out.append(c)
    return out


_PROMO_RE = re.compile(r"(ref(erral)?[ _-]?(link|code)|use my (code|link)|promo code|invite code|\bref=|dm me|message me|inbox me|telegram|whats ?app|t\.me/|"
                       r"link in (my )?bio|join my|my (course|group|channel|discord)|guaranteed (profit|income|returns)|100% (legit|guaranteed)|"
                       r"signals? group|limited (spots|seats)|bit\.ly/|tinyurl)", re.I)
_PROOF_RE = re.compile(r"((i|i've|i have|i'm|i am|we)\s+(made|make|earn(ed)?|been (doing|using|working)|use[d]?|using|bought|own|work(ed)?|got (paid|hired|an? offer|it)|switched|tried)|"
                       r"\b(got|bought) (it|mine|one)\b|"
                       r"(₹|rs\.?|inr|\$|usd|€|£)\s?\d|\d+\s?(k|lpa|lakh|lakhs|per month|/mo(nth)?|a month|/hr|per hour)\b|"
                       r"\b\d+\s+(months?|years?|weeks?)\b|my experience|for me it|in my case|update:)", re.I)


def comment_tags(body):
    """Cheap credibility hints for the model: first-hand evidence vs promotion/scam signals."""
    tags = []
    if _PROMO_RE.search(body): tags.append("⚠ promo/scam signs")
    elif _PROOF_RE.search(body): tags.append("first-hand")
    return (" [" + ", ".join(tags) + "]") if tags else ""


def fmt_comment(c, prefix="COMMENT", maxlen=1000):
    who = f" u/{c['author']}" if c.get("author") and c["author"] not in ("[deleted]",) else ""
    return f"{prefix}{who} (▲{c['score']}){comment_tags(c['body'])}: {c['body'][:maxlen]}"


def _pick_comments(tree, k):
    """Top comments by votes, each with its best reply (and that reply's best reply) — the useful part of a thread."""
    tops = sorted(tree, key=lambda c: -c["score"])[:k]
    res = []
    for c in tops:
        item = {"score": c["score"], "body": c["body"], "replies": [], "author": c.get("author", "")}
        for r in sorted(c["replies"], key=lambda x: -x["score"])[:2]:
            rr = {"score": r["score"], "body": r["body"], "author": r.get("author", "")}
            if r["replies"]:
                b = max(r["replies"], key=lambda x: x["score"]); rr["sub"] = {"score": b["score"], "body": b["body"], "author": b.get("author", "")}
            item["replies"].append(rr)
        res.append(item)
    return res


def _thread_official(th, k):
    j = _reddit_get(f"/comments/{th['id']}", {"sort": "top", "limit": 100, "depth": 3}, timeout=8)
    post = j[0]["data"]["children"][0]["data"]
    return post, _walk_comments(j[1])


def _thread_archive(th, k):
    post = None
    try:
        ps = _arctic("/api/posts/ids", {"ids": th["id"]})
        if ps: post = ps[0]
    except Exception:
        pass
    tree = _arctic("/api/comments/tree", {"link_id": "t3_" + th["id"], "limit": 1500}, timeout=20)
    return post, _walk_comments(tree)


def reddit_thread(th, k=12):
    """Post body + the most upvoted comments with their best replies. Tries the official API, then the archive."""
    th["id"] = th.get("id") or _tid(th["url"])
    if not th["id"]: return th
    for name, fn in (("reddit", _thread_official), ("archive", _thread_archive)):
        try:
            post, tree = fn(th, k)
        except Exception as e:
            print(f"⚠️  thread via {name}:", str(e)[:120]); continue
        if post:
            th.update({k_: v for k_, v in _thread_of(post).items() if v not in (None, "")})
            th["body"] = (post.get("selftext") or "").strip()
        if tree or post:
            th["top_comments"] = _pick_comments(tree, k); th["via"] = name
            return th
    return th


def tavily_extract(urls):
    """Read pages through Tavily's servers (works when a site blocks this machine). 1 credit per 5 pages."""
    key = _secret("TAVILY_API_KEY")
    if not key or not urls: return {}
    r = _http().post("https://api.tavily.com/extract", json={"api_key": key, "urls": urls[:20], "extract_depth": "advanced"},
                     headers={"Authorization": "Bearer " + key}, timeout=40)
    r.raise_for_status()
    return {it.get("url"): it.get("raw_content") or "" for it in r.json().get("results", [])}


def read_threads(threads, k=12):
    """Read every thread in parallel; whatever Reddit and the archive can't give, Tavily reads in one batch."""
    with _cf.ThreadPoolExecutor(8) as ex:
        list(ex.map(lambda th: _safe_thread(th, k), threads))
    miss = [th for th in threads if not th.get("top_comments") and not th.get("body")]
    if miss:
        try:
            got = tavily_extract([th["url"] for th in miss])
            for th in miss:
                txt = got.get(th["url"]) or next((v for u, v in got.items() if _tid(u) == th["id"]), "")
                if txt: th["page_text"] = _clean_reddit_page(txt); th["via"] = "tavily"
        except Exception as e:
            print("⚠️  tavily extract:", str(e)[:140])
    return threads


def _safe_thread(th, k):
    try: return reddit_thread(th, k)
    except Exception as e: print("⚠️  thread:", str(e)[:120]); return th


def _clean_reddit_page(txt):
    lines = [l.strip() for l in txt.splitlines()]
    junk = re.compile(r"^(reply|share|report|save|follow|upvote|downvote|vote|award|more replies|continue this thread|sort by:?.*|"
                      r"open comment sort options|best|top|new|controversial|old|q&a|level \d+|\d+ (points?|replies|comments?)|"
                      r"\d+[hdmy] ago|•|edited.*|log in|sign up|get the app|promoted|advertise.*|privacy policy|user agreement)$", re.I)
    out = [l for l in lines if l and not junk.match(l) and len(l) > 2]
    return "\n".join(out)


def reddit_comment_search(terms, subs, per_sub=40):
    """Deep mode: comments anywhere in the relevant subreddits that mention the topic (archive search)."""
    kw = " ".join(terms[:3])
    out = []
    for sub in subs[:2]:
        try:
            res = _arctic("/api/comments/search", {"body": kw, "subreddit": sub, "limit": per_sub, "sort": "desc",
                                                   "fields": "body,score,link_id,subreddit,created_utc,permalink,author"})
        except Exception as e:
            print("⚠️  comment search:", str(e)[:120]); continue
        for d in res or []:
            body = (d.get("body") or "").strip()
            if body in _BAD_BODY or len(body) < 40: continue
            out.append({"sub": d.get("subreddit", sub), "score": d.get("score") or 0, "body": body, "date": _date(d.get("created_utc")), "author": d.get("author") or "",
                        "url": "https://www.reddit.com" + (d.get("permalink") or f"/r/{sub}/comments/{(d.get('link_id') or '')[3:]}/")})
    return out


# ---------- page reading ----------
def fetch_page(url, max_bytes=4_000_000):
    """Download a page (or PDF) and return its main text."""
    if any(s in _domain(url) for s in SKIP_FETCH): return ""
    r = _http().get(url, timeout=(5, 10), stream=True, allow_redirects=True)
    if r.status_code != 200: return ""
    ct = r.headers.get("content-type", "").lower(); data = b""
    for chunk in r.iter_content(65536):
        data += chunk
        if len(data) > max_bytes: break
    if "pdf" in ct or url.lower().endswith(".pdf"):
        with fitz.open(stream=data, filetype="pdf") as d:
            return "\n".join(p.get_text() for p in list(d)[:25])
    if "html" not in ct and "text" not in ct: return ""
    html_ = data.decode(r.encoding or "utf-8", errors="replace")
    try:
        import trafilatura
        txt = trafilatura.extract(html_, url=url, favor_recall=True, include_comments=False, include_tables=True, deduplicate=True)
        if txt and len(txt) > 200: return txt
    except Exception:
        pass
    html_ = re.sub(r"(?is)<(script|style|noscript|nav|footer|header|svg|form)[^>]*>.*?</\1>", " ", html_)
    txt = re.sub(r"(?s)<[^>]+>", "\n", html_)
    txt = html.unescape(re.sub(r"\n\s*\n+", "\n\n", re.sub(r"[ \t]+", " ", txt)))
    return txt.strip()


_STOP = set("a an the and or of to in on for with is are was were be been it this that what which who whom how why when "
            "where do does did can could should would will i you me my your we our they their at by from as about into vs "
            "please tell give show find best latest new".split())


def _terms(s):
    return [w for w in re.findall(r"[a-z0-9][a-z0-9+#.\-]*", s.lower()) if w not in _STOP and len(w) > 1]


def _chunks(text, words=140):
    paras = [p.strip() for p in re.split(r"\n\s*\n|\n(?=[-•*#\d])", text) if len(p.strip()) > 30]
    out, cur = [], []
    for p in paras:
        w = p.split()
        if len(w) > words * 1.6:                            # long paragraph → split
            for i in range(0, len(w), words): out.append(" ".join(w[i:i + words]))
            continue
        cur += w
        if len(cur) >= words: out.append(" ".join(cur)); cur = []
    if cur: out.append(" ".join(cur))
    return out


def rank_passages(query_terms, docs, budget_tokens, per_doc=4, reddit_share=0.45):
    """BM25 over all passages; every source gets its best passage before any source gets a second."""
    items = []
    for di, d in enumerate(docs):
        for pi, c in enumerate(d.get("chunks", [])): items.append((di, pi, c, _terms(c)))
    if not items: return {}
    N = len(items); avgdl = sum(len(t) for *_, t in items) / N
    df = {}
    for *_, t in items:
        for w in set(t): df[w] = df.get(w, 0) + 1
    qset = list(dict.fromkeys(query_terms))
    scored = {}
    for di, pi, c, t in items:
        tf = {}
        for w in t: tf[w] = tf.get(w, 0) + 1
        s = 0.0
        for w in qset:
            if w in tf:
                idf = math.log(1 + (N - df[w] + 0.5) / (df[w] + 0.5))
                s += idf * tf[w] * 2.2 / (tf[w] + 1.2 * (0.25 + 0.75 * len(t) / avgdl))
        s += 0.15 * (pi == 0)                               # intros usually summarise the page
        scored.setdefault(di, []).append((s, pi, c))
    for di in scored: scored[di].sort(key=lambda x: -x[0])
    picked, used = {}, 0
    for di, d in enumerate(docs):                          # Reddit: the post + its top comments, in upvote order
        if d.get("kind") != "reddit": continue
        n_red = max(1, sum(1 for x in docs if x.get("kind") == "reddit"))
        cap, got = max(250, int(budget_tokens * reddit_share / n_red * 1.3)), []
        for pi, c in enumerate(d.get("chunks", [])):
            t = len(c) // 4 + 8
            if got and (sum(len(x) // 4 + 8 for _, x in got) + t > cap or used + t > budget_tokens * reddit_share): break
            got.append((pi, c)); used += t
        if got: picked[di] = got
        scored.pop(di, None)
    for rnd in range(per_doc):
        for di in sorted(scored, key=lambda d: docs[d].get("order", d)):
            lst = scored[di]
            if rnd >= len(lst) or (rnd > 0 and lst[rnd][0] < 0.35 * lst[0][0]) or (rnd > 0 and lst[rnd][0] <= 0): continue
            c = lst[rnd][2]; t = len(c) // 4 + 8
            if used + t > budget_tokens: continue
            picked.setdefault(di, []).append((lst[rnd][1], c)); used += t
    return {di: [c for _, c in sorted(v)] for di, v in picked.items()}


# ---------- planning ----------
AUTO_SEARCH_RE = re.compile(
    r"\b(latest|news|today|tonight|yesterday|tomorrow|this (week|month|year)|current(ly)?|right now|recent(ly)?|price|prices|cost|"
    r"rate|stock|share price|score|weather|release[sd]?|launch(ed)?|update[sd]?|version|who (is|won|are|was)|when (is|does|will|did)|"
    r"20(2[4-9]|3\d)|search|google|look ?up|find (me|out)|reddit|reviews?|vs\.?|versus|compare|best|recommend|worth it|"
    r"trending|election|match|ipl|budget|specs|benchmark|deadline|schedule|result|ranking|available|near me|"
    r"aaj|abhi|kab|kitne|kaun)\b", re.I)


def _llm_text(prompt, max_tokens=200, temperature=0.2):
    out = ""
    for ch in llm.create_completion(prompt=prompt, max_tokens=max_tokens, stream=True, temperature=temperature, top_p=0.9,
                                    stop=["<|im_end|>", "<|endoftext|>", "<|im_start|>"]):
        out += ch["choices"][0].get("text", "")
    return out


def plan_search(user, history, mode):
    """Ask the model for focused search queries (resolves 'it'/'that' from the chat). Heuristic fallback."""
    today = datetime.datetime.now().strftime("%d %B %Y")
    ctx = ""
    for m in history[-4:]:
        c = THINK_RE.sub("", str(m.get("content") or "")).strip()
        if c: ctx += f"{m.get('role')}: {c[:500]}\n"
    nq = 4 if mode == "deep" else 3
    sys_ = (f"You plan web searches for an AI assistant. Today is {today}. Reply with ONLY one JSON object, no prose:\n"
            '{"search": true|false, "queries": ["..."], "reddit": true|false, "recency": "day|week|month|year|any", "sources": [], "images": true|false}\n'
            "- search=true when a good answer needs current, factual, niche or checkable info (news, prices, people, products, "
            "releases, sports, weather, docs, statistics, reviews). false for chit-chat, jokes, creative writing, maths, or code the user pasted.\n"
            f"- 1-{nq} short keyword queries like a human would type into Google. Resolve pronouns from the chat. Add the year for time-sensitive topics. Use English unless the topic is local.\n"
            "- reddit=true for opinions, experiences, recommendations, 'is X worth it', comparisons, troubleshooting, or when the user mentions Reddit.\n"
            "- recency: how fresh results must be.\n"
            "- sources: extra specialist sources worth searching, any of: \"youtube\" (tutorials, how-to, talks, product reviews, "
            "music/video topics), \"wiki\" (definitions, concepts, history, people, places, organisations), \"papers\" (science, "
            "medicine, ML/AI research, academic questions), \"code\" (programming errors, libraries, APIs, repos — searches GitHub + "
            "Stack Overflow), \"hn\" (tech industry, startups, developer tools discussions), \"news\" (current events). Usually 0-2.\n"
            "- images=true when seeing pictures helps (what something looks like, designs, places, products, people, animals)."
            + ("\n- This is a REDDIT search: write 2-3 different queries phrased like Reddit post titles or how people ask there "
               "(e.g. 'is X worth it', 'X vs Y', 'best X for Y', 'X experience'), not SEO keywords." if mode == "reddit" else "")
            + "\n- For 'which is best / what do people actually use / how do people make money / is X legit' questions, make one of the "
              "queries hunt for warnings and proof (e.g. 'X scam', 'X legit experience', 'X income proof'), so bad options get exposed.")
    p = f"<|im_start|>system\n{sys_}<|im_end|>\n<|im_start|>user\n{('Chat so far:' + chr(10) + ctx + chr(10)) if ctx else ''}Latest message: {user[:1500]}<|im_end|>\n<|im_start|>assistant\n<think>\n\n</think>\n\n"
    plan = None
    try:
        raw = _llm_text(p, 220)
        m = re.search(r"\{.*\}", raw, re.S)
        if m: plan = json.loads(m.group(0))
    except Exception as e:
        print("⚠️  search planner:", str(e)[:120])
    if isinstance(plan, dict) and plan.get("search") is False and mode == "auto":
        return {"search": False, "queries": [], "reddit": False, "recency": None}
    if not isinstance(plan, dict) or not plan.get("queries"):
        q = re.sub(r"\s+", " ", user).strip()[:200]
        plan = {"search": True, "queries": [q], "reddit": bool(re.search(r"reddit|worth|recommend|review|vs|best|experience", user, re.I)), "recency": "any"}
    plan["queries"] = [str(q).strip()[:200] for q in plan.get("queries", []) if str(q).strip()][:nq]
    srcs = plan.get("sources") if isinstance(plan.get("sources"), list) else []
    plan["sources"] = [x for x in dict.fromkeys(str(v).lower() for v in srcs) if x in ("youtube", "wiki", "papers", "code", "hn", "news")]
    if mode == "deep" and "wiki" not in plan["sources"] and not plan.get("recency"): plan["sources"].append("wiki")
    if mode == "reddit": plan["sources"] = []
    plan["images"] = bool(plan.get("images")) and mode != "reddit"
    if mode in ("web", "deep", "reddit"): plan["search"] = True
    if mode == "reddit": plan["reddit"] = True
    if mode == "deep": plan["reddit"] = True
    if mode == "web" and re.search(r"\breddit\b", user, re.I): plan["reddit"] = True
    rc = str(plan.get("recency", "any")).lower()
    plan["recency"] = rc if rc in ("day", "week", "month", "year") else None
    return plan


WEB_RULES = """
WEB SEARCH — results for this message are in <web_results>, fetched moments ago.
- Base the answer on them. Cite sources inline right after the claim they support, using their numbers like [1] or [2][4]. Only cite numbers that exist. No "Sources" list at the end — the app shows the source cards.
- Prefer the newest and most authoritative sources for anything time-sensitive, and mention dates when they matter. If sources disagree, say so and say which is more reliable.
- Reddit threads are people's opinions and experiences, not facts: summarise them as what Redditors say, mention the consensus and notable disagreements, and weigh by upvotes (▲). When the answer is mostly from Reddit, organise it as: the consensus → the top picks/answers and how strongly they're backed (e.g. "recommended in 4 of 6 threads") → disagreements and caveats → a couple of short real quotes in quotation marks, each cited.
- Sources marked "Link you shared" are pages the user gave you: treat them as the main subject (summarise, answer about or analyse them as asked).
- YouTube sources are video transcripts with [m:ss] timestamps — mention the timestamp when pointing to a moment. Papers: mention year and how established the finding is. Stack Overflow: prefer accepted / highly voted answers and note the version they apply to.
- RECOMMENDATIONS FROM PEOPLE ("best X", "which version", "what do people actually use", "how are people genuinely making money",
  "is X legit"): don't just repeat what was said — verify it like a sceptical friend.
  • Build a ranked list of SPECIFIC options (exact names, versions, sites, programs, tools). For each, give: how many DIFFERENT users
    (u/names) and threads back it, the upvotes behind it, the concrete first-hand evidence (real numbers, how long they've done it,
    results), and its main downside.
  • Comments tagged [first-hand] carry more weight; comments tagged [⚠ promo/scam signs] (referral links, "DM me", Telegram groups,
    guaranteed income, selling a course) must NOT count as recommendations — mention them only as warnings.
  • Treat as unverified anything backed by only one person, by vague claims without numbers, or by too-good-to-be-true income.
  • Organise as: ✅ Genuinely recommended (several independent first-hand reports) → 🤔 Mixed / depends on → ⚠️ Avoid or scam
    reports. For money-making: give realistic numbers people report (ranges, time to first income) and what it takes, never hype.
- If the results don't cover the question, say that plainly, then answer from your own knowledge and mark it as such."""
