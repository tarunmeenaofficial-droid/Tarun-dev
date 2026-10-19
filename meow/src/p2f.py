
# ==========================================================
# SEARCH ANYTHING: specialist sources + link reader + deep research (2 rounds)
#   YouTube (transcripts) · Wikipedia · papers (Semantic Scholar + arXiv) · GitHub · Stack Overflow · Hacker News
#   · image results · any link the user pastes (pages, PDFs, YouTube, Reddit threads, GitHub repos)
# ==========================================================
URL_RE = re.compile(r"https?://[^\s<>\"'`)\]]+", re.I)
YT_RE = re.compile(r"(?:youtube\.com/(?:watch\?(?:.*&)?v=|shorts/|live/|embed/)|youtu\.be/)([\w-]{11})")


def _html2text(s):
    s = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", s or "")
    s = re.sub(r"(?i)<br\s*/?>|</p>|</li>|</h\d>", "\n", s)
    s = re.sub(r"(?i)<pre[^>]*>|</pre>", "\n```\n", s)
    s = re.sub(r"<[^>]+>", "", s)
    return html.unescape(re.sub(r"\n{3,}", "\n\n", s)).strip()


def _safe_fetch(url):
    try: return fetch_page(url)
    except Exception as e: print("⚠️  read:", str(e)[:100]); return ""


def _get_json(url, params=None, headers=None, timeout=12):
    r = _http().get(url, params=params, headers=headers or {}, timeout=timeout)
    r.raise_for_status(); return r.json()


# ---------- YouTube ----------
def yt_transcript(vid, max_chars=24000):
    try:
        from youtube_transcript_api import YouTubeTranscriptApi
    except ImportError:
        subprocess.run([_sys.executable, "-m", "pip", "install", "-q", "youtube-transcript-api"], check=False)
        from youtube_transcript_api import YouTubeTranscriptApi
    api = YouTubeTranscriptApi()
    tl = api.list(vid)
    tr = None
    for langs in (["en", "en-US", "en-GB", "en-IN"], ["hi"]):
        try: tr = tl.find_transcript(langs); break
        except Exception: pass
    if tr is None: tr = next(iter(tl))
    if not tr.language_code.startswith(("en", "hi")) and getattr(tr, "is_translatable", False):
        try: tr = tr.translate("en")
        except Exception: pass
    parts, t_mark = [], -60
    for sn in tr.fetch():
        start = getattr(sn, "start", 0) if not isinstance(sn, dict) else sn.get("start", 0)
        text = getattr(sn, "text", "") if not isinstance(sn, dict) else sn.get("text", "")
        if start - t_mark >= 60:                              # a timestamp every minute so the model can cite moments
            parts.append(f"\n[{int(start // 60)}:{int(start % 60):02d}] "); t_mark = start
        parts.append(text.replace("\n", " ") + " ")
    return re.sub(r"[ \t]+", " ", "".join(parts)).strip()[:max_chars]


def yt_meta(url):
    try:
        j = _get_json("https://www.youtube.com/oembed", {"url": url, "format": "json"}, timeout=8)
        return {"title": j.get("title", ""), "channel": j.get("author_name", "")}
    except Exception:
        return {}


def youtube_search(q, n=6):
    key = _secret("SERPER_API_KEY")
    if key:
        try:
            r = _http().post("https://google.serper.dev/videos", json={"q": q, "num": n}, headers={"X-API-KEY": key}, timeout=10)
            r.raise_for_status()
            out = [{"title": v.get("title", ""), "url": v.get("link", ""), "snippet": v.get("snippet", ""), "date": v.get("date", ""),
                    "channel": v.get("channel", ""), "thumb": v.get("imageUrl", ""), "duration": v.get("duration", "")}
                   for v in r.json().get("videos", [])]
            out = [v for v in out if YT_RE.search(v["url"])]
            if out: return out[:n]
        except Exception as e:
            print("⚠️  serper videos:", str(e)[:120])
    try:
        from ddgs import DDGS
        out = []
        for v in DDGS(timeout=8).videos(q, max_results=n) or []:
            u = v.get("content") or v.get("embed_url") or ""
            if YT_RE.search(u):
                out.append({"title": v.get("title", ""), "url": u, "snippet": v.get("description", ""), "date": (v.get("published") or "")[:10],
                            "channel": v.get("uploader", ""), "thumb": (v.get("images") or {}).get("medium", ""), "duration": v.get("duration", "")})
        return out
    except Exception as e:
        print("⚠️  video search:", str(e)[:120]); return []


def youtube_docs(q, n_read=2):
    vids = youtube_search(q, 6); docs = []

    def one(v):
        vid = YT_RE.search(v["url"]).group(1)
        try:
            txt = yt_transcript(vid)
        except Exception as e:
            print("⚠️  transcript:", str(e)[:100]); txt = ""
        return {**v, "kind": "youtube", "site": v.get("channel", ""),
                "text": (f"VIDEO TRANSCRIPT ({v.get('duration') or 'length ?'}):\n" + txt) if txt else (v.get("snippet") or "")}
    with _cf.ThreadPoolExecutor(3) as ex:
        docs = list(ex.map(one, vids[:n_read]))
    docs += [{**v, "kind": "youtube", "text": v.get("snippet", "")} for v in vids[n_read:4] if v.get("snippet")]
    return [d for d in docs if d.get("text")]


# ---------- Wikipedia ----------
def wiki_docs(q, n=2, lang="en"):
    api = f"https://{lang}.wikipedia.org/w/api.php"
    j = _get_json(api, {"action": "query", "list": "search", "srsearch": q, "srlimit": n, "format": "json"},
                  headers={"User-Agent": REDDIT_UA})
    titles = [h["title"] for h in j.get("query", {}).get("search", [])][:n]
    if not titles: return []
    j = _get_json(api, {"action": "query", "prop": "extracts|info", "explaintext": 1, "inprop": "url", "titles": "|".join(titles),
                        "format": "json", "redirects": 1}, headers={"User-Agent": REDDIT_UA})
    out = []
    for p in j.get("query", {}).get("pages", {}).values():
        txt = (p.get("extract") or "").strip()
        if txt:
            txt = re.sub(r"\n=+ (References|External links|See also|Further reading|Notes|Sources)[\s\S]*$", "", txt)
            out.append({"title": p.get("title", "") + " — Wikipedia", "url": p.get("fullurl") or f"https://{lang}.wikipedia.org/wiki/{quote_plus(p.get('title', ''))}",
                        "kind": "wiki", "text": txt[:30000]})
    out.sort(key=lambda d: titles.index(d["title"].replace(" — Wikipedia", "")) if d["title"].replace(" — Wikipedia", "") in titles else 9)
    return out


# ---------- research papers ----------
def paper_docs(q, n=6):
    out, seen = [], set()
    try:
        j = _get_json("https://api.semanticscholar.org/graph/v1/paper/search",
                      {"query": q, "limit": n, "fields": "title,abstract,year,citationCount,url,venue,authors,openAccessPdf,tldr"}, timeout=12)
        for p in j.get("data", []):
            if not p.get("abstract") and not (p.get("tldr") or {}).get("text"): continue
            t = p.get("title", ""); seen.add(t.lower()[:60])
            au = ", ".join(a.get("name", "") for a in (p.get("authors") or [])[:3]) + (" et al." if len(p.get("authors") or []) > 3 else "")
            out.append({"title": t, "url": (p.get("openAccessPdf") or {}).get("url") or p.get("url", ""), "kind": "paper",
                        "date": str(p.get("year") or ""), "site": p.get("venue") or "Semantic Scholar",
                        "text": f"{au} ({p.get('year')}), {p.get('venue') or ''} — cited {p.get('citationCount', 0)} times.\n"
                                + (f"TL;DR: {p['tldr']['text']}\n" if (p.get('tldr') or {}).get('text') else "") + f"Abstract: {p.get('abstract') or ''}"})
    except Exception as e:
        print("⚠️  semantic scholar:", str(e)[:120])
    try:
        r = _http().get("http://export.arxiv.org/api/query", params={"search_query": "all:" + q, "max_results": 5, "sortBy": "relevance"}, timeout=12)
        for e in re.findall(r"<entry>(.*?)</entry>", r.text, re.S):
            g_ = lambda tag: html.unescape(re.sub(r"\s+", " ", (re.search(rf"<{tag}[^>]*>(.*?)</{tag}>", e, re.S) or [None, ""])[1])).strip()
            t = g_("title")
            if not t or t.lower()[:60] in seen: continue
            au = re.findall(r"<name>(.*?)</name>", e)
            out.append({"title": t, "url": g_("id"), "kind": "paper", "date": g_("published")[:10], "site": "arXiv",
                        "text": f"{', '.join(au[:3])}{' et al.' if len(au) > 3 else ''} ({g_('published')[:10]}, arXiv preprint)\nAbstract: {g_('summary')}"})
    except Exception as e:
        print("⚠️  arxiv:", str(e)[:120])
    return out[:n + 3]


# ---------- code: GitHub + Stack Overflow ----------
def code_docs(q):
    out = []
    try:
        hdr = {"Accept": "application/vnd.github+json"}
        if _secret("GITHUB_TOKEN"): hdr["Authorization"] = "Bearer " + _secret("GITHUB_TOKEN")
        j = _get_json("https://api.github.com/search/repositories", {"q": q, "sort": "stars", "per_page": 5}, headers=hdr)
        lines = [f"- {it['full_name']} ★{it.get('stargazers_count', 0):,} — {it.get('description') or ''} (language: {it.get('language') or '?'}, "
                 f"updated {str(it.get('pushed_at', ''))[:10]}) {it.get('html_url')}" for it in j.get("items", [])[:5]]
        if lines:
            out.append({"title": f"GitHub repositories for “{q}”", "url": f"https://github.com/search?q={quote_plus(q)}&type=repositories",
                        "kind": "code", "site": "github.com", "text": "\n".join(lines)})
    except Exception as e:
        print("⚠️  github:", str(e)[:120])
    try:
        base = "https://api.stackexchange.com/2.3"
        j = _get_json(base + "/search/advanced", {"order": "desc", "sort": "relevance", "q": q, "site": "stackoverflow",
                                                   "pagesize": 4, "filter": "withbody"})
        qs_ = [it for it in j.get("items", []) if it.get("answer_count", 0) > 0][:3]
        if qs_:
            ids = ";".join(str(it["question_id"]) for it in qs_)
            ans = _get_json(f"{base}/questions/{ids}/answers", {"order": "desc", "sort": "votes", "site": "stackoverflow", "filter": "withbody", "pagesize": 12})
            by = {}
            for a in ans.get("items", []): by.setdefault(a["question_id"], []).append(a)
            for it in qs_:
                al = sorted(by.get(it["question_id"], []), key=lambda a: (not a.get("is_accepted"), -a.get("score", 0)))[:2]
                body = f"QUESTION (▲{it.get('score', 0)}): {_html2text(it.get('body', ''))[:1500]}\n" + "\n".join(
                    f"{'ACCEPTED ' if a.get('is_accepted') else ''}ANSWER (▲{a.get('score', 0)}): {_html2text(a.get('body', ''))[:2500]}" for a in al)
                out.append({"title": html.unescape(it.get("title", "")), "url": it.get("link", ""), "kind": "code", "site": "stackoverflow.com",
                            "date": _date(it.get("last_activity_date")), "text": body})
    except Exception as e:
        print("⚠️  stack overflow:", str(e)[:120])
    return out


# ---------- Hacker News ----------
def hn_docs(q, n=3):
    j = _get_json("https://hn.algolia.com/api/v1/search", {"query": q, "tags": "story", "hitsPerPage": 8})
    hits = sorted([h for h in j.get("hits", []) if h.get("num_comments")], key=lambda h: -(h.get("points") or 0))[:n]
    out = []

    def one(h):
        try:
            it = _get_json(f"https://hn.algolia.com/api/v1/items/{h['objectID']}", timeout=12)
            kids = sorted([c for c in it.get("children", []) if c.get("text")], key=lambda c: -len(c.get("children", [])))[:10]
            cm = "\n".join(f"COMMENT ({len(c.get('children', []))} replies): {_html2text(c['text'])[:700]}" for c in kids)
        except Exception:
            cm = ""
        return {"title": h.get("title", ""), "url": f"https://news.ycombinator.com/item?id={h['objectID']}", "kind": "hn", "site": "Hacker News",
                "date": (h.get("created_at") or "")[:10], "text": f"▲{h.get('points', 0)} points, {h.get('num_comments', 0)} comments. "
                + (f"Link: {h.get('url')}\n" if h.get("url") else "\n") + cm}
    with _cf.ThreadPoolExecutor(3) as ex:
        out = list(ex.map(one, hits))
    return out


# ---------- images ----------
def image_search(q, n=8):
    key = _secret("SERPER_API_KEY")
    if key:
        try:
            r = _http().post("https://google.serper.dev/images", json={"q": q, "num": n}, headers={"X-API-KEY": key}, timeout=10)
            r.raise_for_status()
            return [{"img": i.get("imageUrl"), "thumb": i.get("thumbnailUrl") or i.get("imageUrl"), "title": i.get("title", ""),
                     "link": i.get("link", ""), "site": i.get("domain") or i.get("source", "")} for i in r.json().get("images", [])][:n]
        except Exception as e:
            print("⚠️  serper images:", str(e)[:120])
    try:
        from ddgs import DDGS
        return [{"img": i.get("image"), "thumb": i.get("thumbnail") or i.get("image"), "title": i.get("title", ""), "link": i.get("url", ""),
                 "site": i.get("source", "")} for i in DDGS(timeout=8).images(q, max_results=n) or []]
    except Exception as e:
        print("⚠️  image search:", str(e)[:120]); return []


# ---------- links the user pasted ----------
def read_link(url):
    url = url.rstrip(".,;:!?")
    m = YT_RE.search(url)
    if m:
        meta = yt_meta(url)
        try:
            txt = yt_transcript(m.group(1), 60000)
        except Exception as e:
            txt = ""; print("⚠️  transcript:", str(e)[:120])
        if not txt:
            try: txt = tavily_extract([url]).get(url, "")
            except Exception: txt = ""
        return {"title": meta.get("title") or "YouTube video", "url": url, "kind": "youtube", "site": meta.get("channel", "YouTube"),
                "text": ("VIDEO TRANSCRIPT:\n" + txt) if txt else "(No transcript available for this video — YouTube may be blocking this server.)"}
    if re.search(r"reddit\.com/r/[^/]+/comments/", url):
        th = {"url": url.split("?")[0], "id": _tid(url), "title": "", "kind": "reddit", "sub": (re.search(r"/r/([^/]+)", url) or [None, ""])[1]}
        read_threads([th], 30)
        parts = ([f"POST: {th['body'][:4000]}"] if th.get("body") else [])
        for c in th.get("top_comments", []):
            s_ = fmt_comment(c, maxlen=1200)
            for r in c.get("replies", []): s_ += "\n  ↳ " + fmt_comment(r, "REPLY", 500)
            parts.append(s_)
        if not parts and th.get("page_text"): parts = [th["page_text"]]
        return {**th, "text": "\n\n".join(parts) or "(Couldn't read this thread.)"}
    gh = re.match(r"https?://github\.com/([\w.-]+)/([\w.-]+)/?$", url)
    if gh:
        o, r_ = gh.group(1), gh.group(2).removesuffix(".git")
        meta, readme = "", ""
        try:
            j = _get_json(f"https://api.github.com/repos/{o}/{r_}")
            meta = f"{j.get('full_name')} ★{j.get('stargazers_count', 0):,} · {j.get('language') or ''} · {j.get('description') or ''} · updated {str(j.get('pushed_at', ''))[:10]}\n"
        except Exception:
            pass
        for br in ("HEAD", "main", "master"):
            try:
                rr = _http().get(f"https://raw.githubusercontent.com/{o}/{r_}/{br}/README.md", timeout=10)
                if rr.status_code == 200: readme = rr.text; break
            except Exception:
                pass
        if meta or readme:
            return {"title": f"{o}/{r_} (GitHub)", "url": url, "kind": "link", "site": "github.com", "text": meta + readme[:40000]}
    txt = ""
    try:
        txt = fetch_page(url, max_bytes=12_000_000)
    except Exception as e:
        print("⚠️  link:", str(e)[:120])
    if len(txt) < 400:
        try:
            alt = tavily_extract([url]).get(url, "")
            if len(alt) > len(txt): txt = alt
        except Exception:
            pass
    title = ""
    m2 = re.match(r"\s*(.{5,140}?)\n", txt or "")
    if m2: title = m2.group(1).strip()
    return {"title": title or _domain(url), "url": url, "kind": "link", "site": _domain(url),
            "text": txt or "(This page couldn't be read — it may need a login, block bots, or be JavaScript-only.)"}


def _link_passages(text, terms, cap_tokens):
    """Whole text if it fits; otherwise the opening part plus the passages most relevant to the question."""
    if len(text) // 4 <= cap_tokens: return [text]
    ch = _chunks(text, 150)
    head, used = [], 0
    for c in ch:
        if used + len(c) // 4 > cap_tokens * 0.35: break
        head.append(c); used += len(c) // 4
    rest = ch[len(head):]
    picked = rank_passages(terms, [{"chunks": rest, "order": 0}], cap_tokens - used, per_doc=60).get(0, []) if rest else []
    return head + (["…"] if picked else []) + picked


# ---------- deep research: a second round for what's still missing ----------
def plan_followups(user, docs, n=3):
    today = datetime.datetime.now().strftime("%d %B %Y")
    found = "\n".join(f"- {d.get('title', '')[:90]}: {(d.get('chunks') or [d.get('text', '')])[0][:160]}" for d in docs[:12])
    p = (f"<|im_start|>system\nYou are a research planner. Today is {today}. Given a question and what the first search round found, "
         f"list up to {n} NEW web searches that would fill the most important gaps (missing facts, other viewpoints, primary sources, "
         'recent updates). Reply ONLY with JSON: {"queries": ["..."]} — use [] if the findings already cover it.<|im_end|>\n'
         f"<|im_start|>user\nQuestion: {user[:1200]}\n\nFound so far:\n{found}<|im_end|>\n<|im_start|>assistant\n<think>\n\n</think>\n\n")
    try:
        m = re.search(r"\{.*\}", _llm_text(p, 160), re.S)
        qs = json.loads(m.group(0)).get("queries", []) if m else []
        return [str(q).strip()[:200] for q in qs if str(q).strip()][:n]
    except Exception as e:
        print("⚠️  follow-up planner:", str(e)[:120]); return []


SPECIALISTS = {"youtube": youtube_docs, "wiki": wiki_docs, "papers": paper_docs, "code": code_docs, "hn": hn_docs}
SRC_LABEL = {"youtube": "YouTube", "wiki": "Wikipedia", "papers": "research papers", "code": "GitHub + Stack Overflow", "hn": "Hacker News", "news": "news"}


# ---------- finding THE answer: relevance-ranked Reddit comments + "is it answered yet?" loop ----------
def _bm25(texts, terms):
    toks = [_terms(t) for t in texts]
    N = max(1, len(toks)); avg = sum(len(t) for t in toks) / N or 1
    df = {}
    for t in toks:
        for w in set(t): df[w] = df.get(w, 0) + 1
    out = []
    for t in toks:
        tf = {}
        for w in t: tf[w] = tf.get(w, 0) + 1
        s = 0.0
        for w in set(terms):
            if w in tf:
                s += math.log(1 + (N - df[w] + 0.5) / (df[w] + 0.5)) * tf[w] * 2.2 / (tf[w] + 1.2 * (0.25 + 0.75 * len(t) / avg))
        out.append(s)
    return out


def rerank_threads(threads, terms, keep=25):
    """Order each thread's comments by (relevance to the question + upvotes + first-hand), promo last; order threads
    by how much they actually talk about the question — so the model sees the comments that ANSWER it."""
    allc = [(th, c) for th in threads for c in th.get("top_comments", [])]
    if not allc: return threads
    texts = [c["body"] + " " + " ".join(r["body"] for r in c.get("replies", [])) for _, c in allc]
    rel = _bm25(texts, terms); top = max(rel) or 1.0
    for (th, c), r in zip(allc, rel):
        tag = comment_tags(c["body"])
        c["_rank"] = 2.2 * r / top + 0.35 * math.log1p(max(0, c["score"])) + (0.6 if "first-hand" in tag else 0) - (3 if "promo" in tag else 0)
    for th in threads:
        cs = sorted(th.get("top_comments", []), key=lambda c: -c.get("_rank", 0))
        th["top_comments"] = cs[:keep]
        trel = _bm25([th.get("title", "") + " " + th.get("body", "")], terms)[0] if th.get("title") else 0
        th["_rel"] = sum(c.get("_rank", 0) for c in cs[:4]) + 0.5 * trel
    return threads


def judge_coverage(user, evidence, mode):
    """Ask the model whether what we found really answers the question; if not, what to search next (and where)."""
    today = datetime.datetime.now().strftime("%d %B %Y")
    where = "Reddit" if mode == "reddit" else "the web and Reddit"
    p = (f"<|im_start|>system\nYou check research for an AI assistant. Today is {today}. Given the user's question and the evidence found "
         f"so far on {where}, decide if it's enough to give a precise, well-supported answer. Reply ONLY with JSON:\n"
         '{"answered": true|false, "missing": "what is still unknown, in a few words", "queries": ["..."], "subreddits": ["..."]}\n'
         "- answered=false if the evidence is off-topic, too thin (only 1-2 people), outdated for a time-sensitive question, or misses part of the question.\n"
         "- queries: up to 3 NEW searches phrased differently from before (synonyms, how people phrase it on Reddit, specific names/versions "
         "mentioned in the evidence, 'X vs Y', 'X experience', 'X scam'). subreddits: up to 3 communities most likely to discuss it (names without r/).<|im_end|>\n"
         f"<|im_start|>user\nQuestion: {user[:1500]}\n\nEvidence so far:\n{evidence}<|im_end|>\n<|im_start|>assistant\n<think>\n\n</think>\n\n")
    try:
        m = re.search(r"\{.*\}", _llm_text(p, 220), re.S)
        j = json.loads(m.group(0)) if m else {}
    except Exception as e:
        print("⚠️  coverage judge:", str(e)[:120]); j = {}
    j["queries"] = [str(q).strip()[:200] for q in (j.get("queries") or []) if str(q).strip()][:3]
    j["subreddits"] = [re.sub(r"^/?r/", "", str(s).strip()).strip("/ ") for s in (j.get("subreddits") or []) if str(s).strip()][:3]
    j["subreddits"] = [s for s in j["subreddits"] if re.fullmatch(r"\w{2,21}", s)]
    return j


def _evidence(threads, docs, terms, max_tokens=2600):
    out, used = [], 0
    for th in sorted([t for t in threads if t.get("top_comments") or t.get("snippet")], key=lambda t: -t.get("_rel", 0)):
        head = f"• r/{th.get('sub', '?')} — {th.get('title', '')[:110]}"
        lines = [head] + [f"  - (▲{c['score']}) {c['body'][:220]}" for c in th.get("top_comments", [])[:3]]
        if not th.get("top_comments") and th.get("snippet"): lines.append("  - " + th["snippet"][:220])
        t = sum(len(l) for l in lines) // 4
        if used + t > max_tokens * 0.7: break
        out += lines; used += t
    for d in docs[:8]:
        l = f"• {d.get('title', '')[:100]} ({_domain(d['url'])}): {(d.get('chunks') or [''])[0][:260]}"
        if used + len(l) // 4 > max_tokens: break
        out.append(l); used += len(l) // 4
    return "\n".join(out) or "(nothing useful found yet)"


# ---------- the whole research run (a generator of progress events) ----------
def web_research(user, history, mode, budget_tokens, rid="", urls=None, search=True):
    """Yields {"status"}, {"search"}, {"sources"}, {"images"} events; the final event is {"_ctx": prompt_block}."""
    stopped = lambda: bool(rid and rid in STOP)
    urls = list(dict.fromkeys(u.rstrip(".,;:!?") for u in (urls or [])))[:4]
    link_docs = []
    if urls:
        yield {"search": {"stage": "links", "links": urls}}
        yield {"status": f"Reading {len(urls)} link{'s' if len(urls) > 1 else ''}…"}
        with _cf.ThreadPoolExecutor(4) as ex:
            link_docs = list(ex.map(read_link, urls))
    plan = {"search": False, "queries": [], "sources": [], "reddit": False, "recency": None, "images": False}
    if search and not stopped():
        yield {"search": {"stage": "planning", "links": urls}}
        plan = plan_search(user, history, mode)
    if not plan.get("search") and not link_docs:
        yield {"search": {"stage": "skipped"}}; yield {"_ctx": ""}; return
    qs, rec, want_reddit, extra = plan["queries"], plan["recency"], plan.get("reddit"), plan.get("sources", [])
    web_on = plan.get("search") and mode != "reddit"
    hits, threads, spec_docs, images = [], [], [], []
    if plan.get("search"):
        labels = (["the web"] if web_on else []) + (["Reddit"] if want_reddit else []) + [SRC_LABEL[x] for x in extra if x in SRC_LABEL and x != "news"]
        yield {"search": {"stage": "searching", "queries": qs, "reddit": bool(want_reddit), "sources": extra, "links": urls}}
        yield {"status": "Searching " + ", ".join(labels[:-1]) + (" and " if len(labels) > 1 else "") + labels[-1] + "…"}
        n_per = 10 if mode == "deep" else 8
        news_q = "news" in extra or rec in ("day", "week") or bool(re.search(r"\bnews\b|\btoday\b|\blatest\b", user, re.I))
        with _cf.ThreadPoolExecutor(14) as ex:
            futs = {}
            if web_on:
                for q in qs: futs[ex.submit(web_search, q, n_per, rec)] = "web"
                if news_q: futs[ex.submit(_ddgs_news, qs[0], 6, rec)] = "news"
            if want_reddit:
                deep_r = mode in ("deep", "reddit")
                for q in qs[:3 if deep_r else 2]: futs[ex.submit(reddit_search, q, 10 if deep_r else 6, rec, deep_r)] = "reddit"
            for x in extra:
                if x in SPECIALISTS: futs[ex.submit(SPECIALISTS[x], qs[0])] = "spec"
            if plan.get("images"): futs[ex.submit(image_search, qs[0], 10)] = "images"
            try:
                for f in _cf.as_completed(futs, timeout=45):
                    try:
                        res = f.result() or []
                    except Exception as e:
                        print(f"⚠️  {futs[f]} search:", str(e)[:120]); continue
                    kind = futs[f]
                    if kind == "reddit": threads.extend(res)
                    elif kind == "spec": spec_docs.extend(res)
                    elif kind == "images": images = res
                    else: hits.extend(res)
            except _cf.TimeoutError:
                print("⚠️  some searches were too slow — skipped")
        if images:
            yield {"images": [i for i in images if i.get("img")][:10]}
    if stopped(): yield {"_ctx": ""}; return
    # merge + de-duplicate web hits (results that several queries agree on rise)
    pool = {}
    n_per = 10 if mode == "deep" else 8
    for i, h in enumerate(hits):
        u = _norm_url(h["url"])
        if not u or "reddit.com" in u and "/comments/" in u:
            if "reddit.com" in u: threads.append(_from_hit(h))
            continue
        if YT_RE.search(h["url"]) and "youtube" in extra: continue
        if u in pool: pool[u]["votes"] += 1; pool[u]["pos"] = min(pool[u]["pos"], i % n_per)
        else: pool[u] = {**h, "votes": 1, "pos": i % n_per, "kind": h.get("kind", "web")}
    linked = {_norm_url(d["url"]) for d in link_docs}
    web = [h for h in sorted(pool.values(), key=lambda h: (h["pos"] - 1.5 * (h["votes"] - 1))) if _norm_url(h["url"]) not in linked]
    tseen, tl = {}, []
    for i, th in enumerate(threads):
        key = th.get("id") or _tid(th["url"]) or _norm_url(th["url"])
        if key in tseen: tseen[key]["_hits"] += 1; continue
        th = {**th, "_hits": 1, "_i": i}; tseen[key] = th; tl.append(th)
    tl.sort(key=lambda th: th["_i"] - 3 * (th["_hits"] - 1))
    n_read = 10 if mode == "deep" else 6
    n_thr = {"reddit": 10, "deep": 6}.get(mode, 3) if want_reddit else 0
    if not n_thr and tl and plan.get("search"): n_thr = 1
    k_cm = {"reddit": 25, "deep": 14}.get(mode, 10)
    web_read, thr_read = web[:n_read], tl[:n_thr]
    side, subs = [], []
    if web_read or thr_read:
        msg = ([f"{len(web_read)} page{'s' if len(web_read) != 1 else ''}"] if web_read else []) + ([f"{len(thr_read)} Reddit threads with their top comments"] if thr_read else [])
        yield {"status": "Reading " + " + ".join(msg) + "…"}
        yield {"search": {"stage": "reading", "queries": qs, "reddit": bool(want_reddit), "sources": extra, "links": urls,
                          "found": len(web) + len(tl) + len(spec_docs)}}
        cnt = {}
        for th in thr_read:
            if th.get("sub"): cnt[th["sub"]] = cnt.get(th["sub"], 0) + 1
        subs = sorted(cnt, key=lambda s_: -cnt[s_])
        with _cf.ThreadPoolExecutor(12) as ex:
            fw = {ex.submit(fetch_page, h["url"]): h for h in web_read}
            ft = ex.submit(read_threads, thr_read, max(k_cm, 40) if mode in ("reddit", "deep") else k_cm) if thr_read else None
            fc = ex.submit(reddit_comment_search, _terms(" ".join(qs)), subs) if (mode in ("reddit", "deep") and subs) else None
            try:
                for f in _cf.as_completed(list(fw) + [x for x in (ft, fc) if x], timeout=45):
                    try:
                        res = f.result()
                    except Exception as e:
                        res = None; print("⚠️  read:", str(e)[:120])
                    if f in fw: fw[f]["text"] = res or ""
                    elif f is fc: side = res or []
            except _cf.TimeoutError:
                print("⚠️  some pages were too slow — skipped")
        # pages that blocked this server → read them through Tavily in one batch
        blocked = [h for h in web_read if len(h.get("text") or "") < 300 and not any(s in _domain(h["url"]) for s in SKIP_FETCH)]
        if blocked and _secret("TAVILY_API_KEY") and not stopped():
            try:
                got = tavily_extract([h["url"] for h in blocked])
                for h in blocked:
                    if len(got.get(h["url"], "")) > len(h.get("text") or ""): h["text"] = got[h["url"]]
            except Exception as e:
                print("⚠️  tavily extract:", str(e)[:120])
    if stopped(): yield {"_ctx": ""}; return
    docs = []
    for h in web[:max(n_read, 8)]:
        body = (h.get("text") or "").strip()
        ch = _chunks(body) if body else []
        if not ch and h.get("snippet"): ch = [h["snippet"]]
        if ch: docs.append({**h, "chunks": ch})
    # keep searching until the question is actually answered (Reddit + Deep modes): up to 2 extra rounds
    terms = _terms(" ".join(qs) + " " + user)
    read = [th for th in tl if th.get("top_comments") or th.get("body") or th.get("page_text")]
    rerank_threads(read, terms, 40)
    rounds = 1
    if mode in ("reddit", "deep") and plan.get("search") and not stopped():
        seen_t = {th.get("id") or _tid(th["url"]) for th in tl}
        seen_u = {_norm_url(d["url"]) for d in docs}
        for rnd in (2, 3):
            if stopped(): break
            yield {"search": {"stage": "checking", "round": rnd - 1, "queries": qs, "reddit": bool(want_reddit), "sources": extra, "links": urls,
                              "found": len(web) + len(tl) + len(spec_docs)}}
            yield {"status": "Checking if this really answers your question…"}
            j = judge_coverage(user, _evidence(read, docs, terms), mode)
            if j.get("answered") or not (j.get("queries") or j.get("subreddits")): break
            nq = j["queries"] or [qs[0]]
            subs_r = list(dict.fromkeys(j.get("subreddits", []) + [s for s in subs if s]))[:3]
            qs = qs + [q for q in nq if q not in qs]
            yield {"search": {"stage": "deeper", "round": rnd, "queries": qs, "reddit": bool(want_reddit), "sources": extra, "links": urls,
                              "missing": j.get("missing", ""), "subs": subs_r, "found": len(web) + len(tl) + len(spec_docs)}}
            yield {"status": f"Round {rnd}: " + (j.get("missing") or "digging deeper")[:90] + (f" · searching r/{', r/'.join(subs_r)}" if subs_r and want_reddit else "")}
            new_thr, new_web = [], []
            with _cf.ThreadPoolExecutor(10) as ex:
                futs = []
                if want_reddit:
                    for q in nq: futs.append(("r", ex.submit(reddit_search, q, 8, rec, True, None)))
                    for s_ in subs_r[:2]: futs.append(("r", ex.submit(reddit_search, nq[0], 8, rec, True, [s_])))
                if mode == "deep":
                    for q in nq: futs.append(("w", ex.submit(web_search, q, 6, rec)))
                for kind, f_ in futs:
                    try:
                        res = f_.result(timeout=40) or []
                    except Exception as e:
                        print("⚠️  round search:", str(e)[:100]); continue
                    for h in res:
                        if kind == "r":
                            k_ = h.get("id") or _tid(h["url"])
                            if k_ and k_ not in seen_t: seen_t.add(k_); new_thr.append(h)
                        else:
                            u = _norm_url(h["url"])
                            if u not in seen_u and "reddit.com" not in u: seen_u.add(u); new_web.append(h)
            new_thr = sorted(new_thr, key=lambda th: th.get("_rank", 0))[:6]
            new_web = new_web[:5]
            if not new_thr and not new_web: break
            rounds = rnd
            with _cf.ThreadPoolExecutor(8) as ex:
                ft = ex.submit(read_threads, new_thr, 40) if new_thr else None
                texts = list(ex.map(_safe_fetch, [h["url"] for h in new_web]))
                if ft:
                    try: ft.result(timeout=60)
                    except Exception as e: print("⚠️  round read:", str(e)[:100])
            for h, t_ in zip(new_web, texts):
                ch = _chunks(t_) if t_ else ([h["snippet"]] if h.get("snippet") else [])
                if ch: docs.append({**h, "kind": "web", "chunks": ch})
            for th in new_thr:
                tl.append(th)
                if th.get("top_comments") or th.get("body") or th.get("page_text"): read.append(th)
            terms = _terms(" ".join(qs) + " " + user)
            rerank_threads(read, terms, 40)
    # the threads that best answer the question go first
    keep_c = {"reddit": 25, "deep": 14}.get(mode, 10)
    unread = [th for th in tl if th not in read][:2 if want_reddit else 0]
    reddit_final = sorted(read, key=lambda th: -th.get("_rel", 0))[:{"reddit": 12, "deep": 8}.get(mode, n_thr)] + unread
    for d in spec_docs:
        ch = _chunks(d["text"], 150) if d.get("kind") not in ("code", "hn") else [d["text"][i:i + 2400] for i in range(0, len(d["text"]), 2400)]
        if ch: docs.append({**d, "chunks": ch})
    for th in reddit_final:
        parts = []
        if th.get("body"): parts.append("POST: " + th["body"][:2000])
        for c in th.get("top_comments", [])[:keep_c]:
            s_ = fmt_comment(c, maxlen=1000)
            for r in c.get("replies", []):
                s_ += "\n  ↳ " + fmt_comment(r, "REPLY", 450)
                if r.get("sub"): s_ += "\n    ↳ " + fmt_comment(r["sub"], "REPLY", 300)
            parts.append(s_)
        if not parts and th.get("page_text"): parts = _chunks(th["page_text"], 110)
        if not parts and th.get("snippet"): parts = [th["snippet"]]
        if parts: docs.append({**th, "chunks": parts})
    if side:
        qt = set(_terms(" ".join(qs)))
        side.sort(key=lambda c: -(c["score"] + 25 * len(qt & set(_terms(c["body"])))))
        bysub = {}
        for c in side[:24]: bysub.setdefault(c["sub"], []).append(c)
        for sub, cs in bysub.items():
            docs.append({"title": f"More comments in r/{sub} on this topic", "url": f"https://www.reddit.com/r/{sub}/search/?q={quote_plus(' '.join(qs[:1]))}",
                         "kind": "reddit", "sub": sub, "score": None, "comments": len(cs), "date": "",
                         "chunks": [fmt_comment(c, f"COMMENT ({c['date']})", 700) for c in cs]})
    for i, d in enumerate(docs): d["order"] = i
    qterms = _terms(" ".join(qs) + " " + user)
    # links the user pasted come first and get the biggest share
    link_budget = int(budget_tokens * (0.85 if not docs else 0.5)) if link_docs else 0
    blocks, sources = [], []

    def add_source(d, passages):
        n = len(sources) + 1
        src = {"n": n, "title": (d.get("title") or _domain(d["url"]))[:160], "url": d["url"], "domain": _domain(d["url"]),
               "kind": d.get("kind", "web"), "date": d.get("date", ""), "snippet": (d.get("snippet") or passages[0])[:220]}
        if d.get("kind") == "reddit":
            src.update(sub=d.get("sub", ""), score=d.get("score"), comments=d.get("comments"))
            meta = ", ".join(x for x in [f"▲{d['score']}" if d.get("score") is not None else "", f"{d['comments']} comments" if d.get("comments") else "", d.get("date", "")] if x)
            head = f"[{n}] Reddit r/{d.get('sub', '?')} — \"{d.get('title', '')}\"" + (f" ({meta})" if meta else "")
        else:
            tag = {"youtube": "YouTube", "wiki": "Wikipedia", "paper": "Paper", "code": d.get("site") or "Code", "hn": "Hacker News",
                   "link": "Link you shared", "news": "News"}.get(d.get("kind"), "")
            if d.get("kind") == "youtube" and d.get("site"): tag += f" · {d['site']}"
            head = f"[{n}] {(tag + ': ') if tag else ''}{d.get('title', '')} — {_domain(d['url'])}" + (f" ({d['date']})" if d.get("date") else "")
        sep = "\n" if d.get("kind") in ("reddit", "code", "hn") else "\n…\n"
        blocks.append(head + f"\nURL: {d['url']}\n" + sep.join(passages)); sources.append(src)

    for d in link_docs:
        add_source(d, _link_passages(d["text"], qterms, max(400, link_budget // max(1, len(link_docs)))))
    picked = rank_passages(qterms, docs, budget_tokens - link_budget - 60 * len(docs),
                           reddit_share={"reddit": 0.92, "deep": 0.5}.get(mode, 0.4))
    for di, d in enumerate(docs):
        if di in picked: add_source(d, picked[di])
    yield {"sources": sources}
    yield {"search": {"stage": "done", "rounds": rounds, "queries": qs, "reddit": bool(want_reddit), "sources": extra, "links": urls,
                      "found": len(web) + len(tl) + len(spec_docs), "used": len(sources)}}
    if not blocks:
        yield {"_ctx": "<web_results>\n(The search returned nothing usable — the network may be off, or the engines rate-limited this server.)\n</web_results>"}
        return
    today = datetime.datetime.now().strftime("%d %B %Y")
    yield {"_ctx": f'<web_results searched="{today}" queries="{" | ".join(qs)}">\n' + "\n\n".join(blocks) + "\n</web_results>"}
