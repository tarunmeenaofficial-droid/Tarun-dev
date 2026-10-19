
# ==========================================================
# PHOTO-REAL IMAGE EDITING (GPU when free)
#   text in images: OCR → LaMa background rebuild → font match (40+ families) → pixel-matched redraw
#   magic eraser (LaMa) · AI upscale (Real-ESRGAN)
# ==========================================================
from PIL import ImageDraw, ImageFont
from functools import lru_cache
import glob as _glob, tarfile as _tarfile, urllib.request as _urlreq

MODEL_DIR = os.path.join(WORK_DIR, "models")
FONT_DIR = os.path.join(WORK_DIR, "fonts")
os.makedirs(MODEL_DIR, exist_ok=True); os.makedirs(FONT_DIR, exist_ok=True)
LAMA_URL = "https://github.com/enesmsahin/simple-lama-inpainting/releases/download/v0.1.0/big-lama.pt"
ESRGAN_URL = "https://github.com/xinntao/Real-ESRGAN/releases/download/v0.1.0/RealESRGAN_x4plus.pth"
FONT_FAMILIES = ["inter", "roboto", "open-sans", "noto-sans", "lato", "poppins", "montserrat", "source-sans-3", "nunito",
                 "ubuntu", "ibm-plex-sans", "dm-sans", "manrope", "rubik", "work-sans", "fira-sans", "pt-sans", "arimo",
                 "carlito", "raleway", "oswald", "tinos", "caladea", "noto-serif", "merriweather", "pt-serif",
                 "playfair-display", "source-serif-4", "lora", "eb-garamond", "roboto-mono", "cousine", "source-code-pro",
                 "jetbrains-mono", "noto-sans-devanagari", "mukta", "hind"]
_KEEP_STYLES = ("300Light", "400Regular", "500Medium", "600SemiBold", "700Bold", "800ExtraBold", "400Regular_Italic", "700Bold_Italic")
_FONTS, _FONTS_N = None, -1
_PACK_DONE = threading.Event()


def _download(url, path):
    if os.path.exists(path) and os.path.getsize(path) > 1000: return path
    tmp = path + ".part"
    _urlreq.urlretrieve(url, tmp); os.replace(tmp, path)
    return path


def _safe(fn):
    try: return fn()
    except Exception: return None


def _fetch_font_pack():
    """Static TTFs for 37 Google font families (via the npm registry), cached in WORK_DIR/fonts."""
    try:
        for fam in FONT_FAMILIES:
            key = fam.replace("-", "")
            if _glob.glob(os.path.join(FONT_DIR, key + "__*.ttf")): continue
            try:
                meta = json.loads(_urlreq.urlopen(f"https://registry.npmjs.org/@expo-google-fonts/{fam}/latest", timeout=20).read())
                tgz = os.path.join(FONT_DIR, fam + ".tgz"); _download(meta["dist"]["tarball"], tgz)
                with _tarfile.open(tgz) as tf:
                    for m in tf.getmembers():
                        if not m.name.endswith(".ttf"): continue
                        style = m.name.split("/")[-2]
                        if style not in _KEEP_STYLES: continue
                        open(os.path.join(FONT_DIR, f"{key}__{style}.ttf"), "wb").write(tf.extractfile(m).read())
                os.remove(tgz)
            except Exception:
                continue
    finally:
        _PACK_DONE.set()


def warm_up_media():
    """Background downloads (font pack + LaMa) so the first edit is fast."""
    threading.Thread(target=_fetch_font_pack, daemon=True).start()
    threading.Thread(target=lambda: _safe(lambda: _download(LAMA_URL, os.path.join(MODEL_DIR, "big-lama.pt"))), daemon=True).start()


def _font_list():
    """Candidate fonts: list of dicts {path, family, weight, italic}."""
    global _FONTS, _FONTS_N
    paths = set(_glob.glob(os.path.join(FONT_DIR, "*__*.ttf")))
    if _FONTS is not None and _FONTS_N == len(paths): return _FONTS
    sysp = set()
    for root in ("/usr/share/fonts", "/usr/local/share/fonts"):
        sysp |= set(_glob.glob(os.path.join(root, "**", "*.[ot]tf"), recursive=True))
    try:
        import matplotlib
        sysp |= set(_glob.glob(os.path.join(os.path.dirname(matplotlib.__file__), "mpl-data", "fonts", "ttf", "DejaVu*.ttf")))
    except Exception:
        pass
    out, seen = [], set()
    for p in sorted(paths):
        try:
            fam, style = os.path.basename(p)[:-4].split("__")
            out.append(dict(path=p, family=fam, weight=int(style[:3]), italic="Italic" in style)); seen.add(fam)
        except Exception:
            continue
    good_sys = ("liberation", "dejavu", "carlito", "caladea", "freesans", "freeserif", "ubuntu")
    for p in sorted(sysp):
        n = os.path.basename(p).lower()
        if not any(g in n for g in good_sys) or any(k in n for k in ("cjk", "emoji", "symbol", "math", "condensed", "display", "extralight")): continue
        try:
            fam, sty = ImageFont.truetype(p, 20).getname()
        except Exception:
            continue
        key = re.sub(r"[^a-z]", "", fam.lower())
        if key in seen: continue
        s = (sty or "regular").lower()
        if s not in ("regular", "book", "bold", "italic", "bold italic", "medium", "semibold", "light", "oblique", "bold oblique"): continue
        w = 600 if "semibold" in s else 700 if "bold" in s else 500 if "medium" in s else 300 if "light" in s else 400
        out.append(dict(path=p, family=fam, weight=w, italic="italic" in s or "oblique" in s))
    _FONTS, _FONTS_N = out, len(paths)
    return out


@lru_cache(maxsize=8192)
def _tt(path, size):
    return ImageFont.truetype(path, max(4, round(size * 4) / 4))


@lru_cache(maxsize=16384)
def _ink_box(path, size, text):
    """True ink extents of `text` relative to its baseline origin (PIL's getbbox includes side bearings)."""
    import numpy as np
    f = _tt(path, size); l, t, r, b = f.getbbox(text, anchor="ls")
    pad = int(size) + 4
    im = Image.new("L", (int(r - l) + 2 * pad, int(b - t) + 2 * pad), 0)
    ImageDraw.Draw(im).text((pad - l, pad - t), text, font=f, fill=255, anchor="ls")
    a = np.asarray(im) > 60; ys, xs = np.where(a)
    if not len(xs): return None
    return (xs.min() - (pad - l), ys.min() - (pad - t), xs.max() + 1 - (pad - l), ys.max() + 1 - (pad - t))


def _render_mask(path, text, w, h):
    """Render text stretched exactly onto a w×h ink box → (0..1 map, font size, width ratio)."""
    import numpy as np
    ib = _ink_box(path, 48, text)
    if not ib or ib[2] - ib[0] < 1 or ib[3] - ib[1] < 1: return None
    size = 48 * h / (ib[3] - ib[1]); ib = _ink_box(path, size, text)
    if not ib: return None
    f = _tt(path, size); W, H = max(1, ib[2] - ib[0]), max(1, ib[3] - ib[1])
    im = Image.new("L", (W + 4, H + 4), 0)
    ImageDraw.Draw(im).text((2 - ib[0], 2 - ib[1]), text, font=f, fill=255, anchor="ls")
    im = im.crop((2, 2, 2 + W, 2 + H)).resize((max(1, int(w)), max(1, int(h))), Image.BILINEAR)
    return np.asarray(im, float) / 255.0, size, w / W


def match_font(strength, text, only=None):
    """Two-stage search over every installed font (family, then weight/italic), blur-aware correlation.
    `only` = list of font dicts to restrict the search to."""
    import numpy as np, cv2
    h, w = strength.shape
    a = strength - strength.mean(); na = np.sqrt((a * a).sum()) or 1.0
    blurs = (0, 0.6, 1.1) if h < 60 else (0, 1.0, 2.0)
    target_cov = (strength > 0.5).mean()

    def score(fd):
        try:
            r = _render_mask(fd["path"], text, w, h)
        except Exception:
            return None
        if not r: return None
        m0, size, sx = r; top = None
        for sig in blurs:
            m = cv2.GaussianBlur(m0, (0, 0), sig) if sig else m0
            bm = m - m.mean(); corr = float((a * bm).sum() / (na * (np.sqrt((bm * bm).sum()) or 1.0)))
            weight = target_cov / max(1e-3, (m > 0.5).mean())
            sc = corr - 0.15 * abs(np.log(max(1e-3, sx))) - 0.25 * abs(np.log(max(1e-3, weight)))
            if top is None or sc > top[0]: top = (sc, weight, sig)
        return (top[0], fd, size, sx, top[1], top[2])

    if only:
        res = [r for r in (score(fd) for fd in only) if r]
        return max(res, key=lambda r: r[0]) if res else None
    fams = {}
    for fd in _font_list(): fams.setdefault(fd["family"], []).append(fd)
    stage1 = []
    for fam, lst in fams.items():
        probe = [min(lst, key=lambda f: (f["italic"], abs(f["weight"] - 400)))]
        bold = [f for f in lst if not f["italic"] and f["weight"] >= 600]
        if bold: probe.append(min(bold, key=lambda f: abs(f["weight"] - 700)))
        for fd in probe:
            r = score(fd)
            if r: stage1.append(r)
    if not stage1: return None
    stage1.sort(key=lambda r: -r[0])
    best = stage1[0]
    for fam in {r[1]["family"] for r in stage1[:5]}:
        for fd in fams[fam]:
            r = score(fd)
            if r and r[0] > best[0]: best = r
    return best


# ---------- GPU models ----------
_TORCH = {}


def _device(need_gb=1.5):
    try:
        import torch
        if torch.cuda.is_available():
            f, i = max((torch.cuda.mem_get_info(i)[0], i) for i in range(torch.cuda.device_count()))
            if f / 2**30 >= need_gb: return f"cuda:{i}"
    except Exception:
        pass
    return "cpu"


def _lama():
    import torch
    if "lama" not in _TORCH:
        path = _download(LAMA_URL, os.path.join(MODEL_DIR, "big-lama.pt"))
        _TORCH["lama"] = (torch.jit.load(path, map_location="cpu").eval(), "cpu")
    model, dev = _TORCH["lama"]
    want = _device(2.0)
    if want != dev:
        try:
            model = model.to(want); dev = want
        except Exception:
            model = model.to("cpu"); dev = "cpu"
        _TORCH["lama"] = (model, dev)
    FEATURES["lama"] = dev
    return model, dev


def inpaint(rgb, mask, max_side=1024):
    """Rebuild masked pixels with LaMa (OpenCV fallback). rgb HxWx3 uint8, mask HxW."""
    import numpy as np, cv2
    m = (mask > 0).astype(np.uint8)
    if not m.any(): return rgb
    ys, xs = np.where(m); H, W = m.shape
    big = max(ys.max() - ys.min() + 1, xs.max() - xs.min() + 1)
    mg = int(max(48, 1.6 * big if big < 200 else 0.6 * big))
    X0, Y0 = max(0, xs.min() - mg), max(0, ys.min() - mg); X1, Y1 = min(W, xs.max() + 1 + mg), min(H, ys.max() + 1 + mg)
    crop, cm = rgb[Y0:Y1, X0:X1], m[Y0:Y1, X0:X1]
    try:
        import torch
        model, dev = _lama()
        k = min(1.0, max_side / max(crop.shape[:2]))
        ci = cv2.resize(crop, None, fx=k, fy=k, interpolation=cv2.INTER_AREA) if k < 1 else crop
        mi = cv2.resize(cm, (ci.shape[1], ci.shape[0]), interpolation=cv2.INTER_NEAREST) if k < 1 else cm
        mi = cv2.dilate(mi, np.ones((3, 3), np.uint8), iterations=1)
        ph, pw = (-ci.shape[0]) % 8, (-ci.shape[1]) % 8
        ci_p = np.pad(ci, ((0, ph), (0, pw), (0, 0)), mode="reflect"); mi_p = np.pad(mi, ((0, ph), (0, pw)))
        t = torch.from_numpy(np.ascontiguousarray(ci_p)).permute(2, 0, 1)[None].float().div(255).to(dev)
        tm = torch.from_numpy(np.ascontiguousarray(mi_p))[None, None].float().to(dev)
        with torch.no_grad():
            out = model(t, tm)[0].permute(1, 2, 0).clamp(0, 1).mul(255).byte().cpu().numpy()
        out = out[:ci.shape[0], :ci.shape[1]]
        if k < 1: out = cv2.resize(out, (crop.shape[1], crop.shape[0]), interpolation=cv2.INTER_CUBIC)
    except Exception:
        FEATURES["lama"] = "unavailable (OpenCV fallback)"
        out = cv2.inpaint(crop, cm * 255, 5, cv2.INPAINT_TELEA)
    soft = cv2.GaussianBlur(cv2.dilate(cm, np.ones((3, 3), np.uint8)).astype(np.float32), (5, 5), 0)[..., None]
    res = rgb.copy()
    res[Y0:Y1, X0:X1] = np.clip(out * soft + crop * (1 - soft), 0, 255).astype(np.uint8)
    return res


def ai_upscale(img, scale=2):
    """Real-ESRGAN ×4 (tiled; GPU when free), resized to the requested scale."""
    import numpy as np, torch
    if "esrgan" not in _TORCH:
        import spandrel
        path = _download(ESRGAN_URL, os.path.join(MODEL_DIR, "RealESRGAN_x4plus.pth"))
        _TORCH["esrgan"] = spandrel.ModelLoader().load_from_file(path).model.eval()
    dev = _device(2.5); model = _TORCH["esrgan"].to(dev); half = dev.startswith("cuda")
    if half: model = model.half()
    alpha = img.getchannel("A") if "A" in img.getbands() else None
    x = np.asarray(img.convert("RGB")).astype(np.float32) / 255
    H, W = x.shape[:2]; tile, ov = 256, 16
    out = np.zeros((H * 4, W * 4, 3), np.float32)
    for y in range(0, H, tile):
        for xx in range(0, W, tile):
            y0, x0 = max(0, y - ov), max(0, xx - ov); y1, x1 = min(H, y + tile + ov), min(W, xx + tile + ov)
            t = torch.from_numpy(np.ascontiguousarray(x[y0:y1, x0:x1])).permute(2, 0, 1)[None].to(dev)
            if half: t = t.half()
            with torch.no_grad():
                r = model(t)[0].float().clamp(0, 1).permute(1, 2, 0).cpu().numpy()
            oy, ox = (y - y0) * 4, (xx - x0) * 4; hh, ww = min(tile, H - y) * 4, min(tile, W - xx) * 4
            out[y * 4:y * 4 + hh, xx * 4:xx * 4 + ww] = r[oy:oy + hh, ox:ox + ww]
    if half: _TORCH["esrgan"] = model.float()
    res = Image.fromarray((out * 255).round().astype(np.uint8))
    if scale != 4: res = res.resize((int(W * scale), int(H * scale)), Image.LANCZOS)
    if alpha: res.putalpha(alpha.resize(res.size, Image.LANCZOS))
    FEATURES["esrgan"] = dev
    return res


# ---------- OCR & analysis ----------
def ocr_boxes(img, max_side=2600):
    """Line-level OCR: [{bbox:[x0,y0,x1,y1] (image px), text, score}]."""
    global _OCR
    import numpy as np
    if _OCR is None:
        from rapidocr_onnxruntime import RapidOCR
        _OCR = RapidOCR(); FEATURES["ocr"] = True
    im = img.convert("RGB"); k = 1.0
    if max(im.size) > max_side:
        k = max_side / max(im.size); im = im.resize((int(im.width * k), int(im.height * k)), Image.LANCZOS)
    elif max(im.size) < 900:                                  # small screenshots read better enlarged
        k = 2.0; im = im.resize((im.width * 2, im.height * 2), Image.LANCZOS)
    res, _ = _OCR(np.array(im))
    out = []
    for quad, text, score in (res or []):
        score = float(score)
        if score < 0.5 or not text.strip(): continue
        xs = [q[0] / k for q in quad]; ys = [q[1] / k for q in quad]
        out.append({"bbox": [min(xs), min(ys), max(xs), max(ys)], "text": text.strip(), "score": round(score, 3)})
    return out


def _tight_box(gray, box):
    """Shrink an OCR box to the real ink (text = the minority colour). On gradients/photos the ink is
    measured against a local background estimate so shaded background never counts as text."""
    import numpy as np, cv2
    x0, y0, x1, y1 = [int(round(v)) for v in box]
    x0, y0 = max(0, x0), max(0, y0)
    crop = gray[y0:y1, x0:x1]
    if crop.size == 0: return box, None
    _, th = cv2.threshold(crop, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    ink = th > 0
    if ink.mean() > 0.5: ink = ~ink
    if (~ink).sum() > 20 and float(crop[~ink].std()) > 6 and min(crop.shape) >= 6:
        h = crop.shape[0]; k = min(255, (int(h * 2.2) // 2) * 2 + 1); p = k // 2 + 1
        big = cv2.copyMakeBorder(crop, p, p, p, p, cv2.BORDER_REFLECT)
        bg = cv2.medianBlur(big, k)[p:-p, p:-p].astype(np.float32)
        d = crop.astype(np.float32) - bg
        sign = 1.0 if float(np.mean(crop[ink])) > float(np.mean(crop[~ink])) else -1.0
        dd = np.clip(d * sign, 0, None)
        core = dd[ink]
        if core.size > 10:
            thr = max(10.0, 0.35 * float(np.percentile(core, 90)))
            loc = dd > thr
            if loc.sum() > 10: ink = loc
    ys, xs = np.where(ink)
    if len(xs) < 4: return box, ink
    return [x0 + xs.min(), y0 + ys.min(), x0 + xs.max() + 1, y0 + ys.max() + 1], ink[ys.min():ys.max() + 1, xs.min():xs.max() + 1]


def _style_from_pixels(rgb, ink):
    import numpy as np
    txt = rgb[ink].astype(float); bg = rgb[~ink].astype(float)
    bc = np.median(bg, axis=0) if len(bg) else np.array([255., 255., 255.])
    if len(txt):
        dist = np.linalg.norm(txt - bc, axis=1)
        core = txt[dist >= np.quantile(dist, 0.7)]
        tc = np.median(core if len(core) else txt, axis=0)
    else:
        tc = np.array([0., 0., 0.])
    bstd = float(bg.std(axis=0).mean()) if len(bg) > 8 else 0.0
    return tuple(int(v) for v in tc), tuple(int(v) for v in bc), bstd


def _ink_strength(rgb, tc, bc):
    import numpy as np
    tc, bc = np.array(tc, float), np.array(bc, float); d = tc - bc; dd = float((d * d).sum()) or 1.0
    return np.clip(((rgb.astype(float) - bc) @ d) / dd, 0, 1)


_WIDTH_FONT = None


def _width_font():
    """A neutral sans font used only to estimate relative character widths."""
    global _WIDTH_FONT
    if _WIDTH_FONT is None:
        cands = [f for f in _font_list() if not f["italic"] and f["weight"] == 400 and any(k in f["family"].lower() for k in ("arimo", "liberation sans", "roboto", "dejavu sans", "notosans"))]
        _WIDTH_FONT = _tt(cands[0]["path"], 100) if cands else ImageFont.load_default()
    return _WIDTH_FONT


def _ink_gaps(ink):
    """Empty-column runs inside a text line, split into letter gaps vs word gaps (natural break)."""
    h, w = ink.shape; cols = ink.any(axis=0); runs, x = [], 0
    while x < w:
        if not cols[x]:
            s0 = x
            while x < w and not cols[x]: x += 1
            if s0 > 0 and x < w: runs.append((s0, x))
        else:
            x += 1
    if not runs: return []
    ws = sorted(e - s for s, e in runs)
    thr = 0.3 * h
    best = 0
    for a, b in zip(ws, ws[1:]):
        if b >= 0.16 * h and a > 0 and b / a > best: best, cut = b / a, b
    if best >= 1.45: thr = min(thr, cut) if cut >= 0.16 * h else thr
    return [(s, e) for s, e in runs if e - s >= thr]


def _local_strength(region, tc, k=None):
    """Ink coverage measured against a LOCAL background estimate (works on gradients, photos, paper)."""
    import numpy as np, cv2
    h = region.shape[0]
    k = k or max(3, (int(h * 2.2) // 2) * 2 + 1)
    k = min(k, 255)
    lb = cv2.medianBlur(region, k).astype(np.float32)
    d = np.array(tc, np.float32)[None, None, :] - lb
    num = ((region.astype(np.float32) - lb) * d).sum(-1); den = (d * d).sum(-1) + 1e-3
    return np.clip(num / den, 0, 1)


def _word_gap_filter(gaps, text_nospace, path, size, scale, h):
    """Keep only gaps that are wider than the font's own letter spacing would explain."""
    f = _tt(path, size); keep = []
    pos = [f.getlength(text_nospace[:i]) * scale for i in range(len(text_nospace) + 1)]
    inks = [_ink_box(path, size, c) for c in text_nospace]
    for s0, e0 in gaps:
        j = min(range(1, len(text_nospace)), key=lambda q: abs(pos[q] - s0), default=None)
        if j is None: continue
        a, b = inks[j - 1], inks[j]
        expected = ((f.getlength(text_nospace[j - 1]) - (a[2] if a else 0)) + (b[0] if b else 0)) * scale
        if (e0 - s0) - max(0, expected) > 0.16 * size * scale: keep.append((s0, e0))
    return keep


def _respace(text, ink, font=None, gaps=None):
    """OCR often drops spaces ('Flat50%offthisweekend'); put them back where the ink has word gaps.
    Each ink segment between gaps is matched to a run of characters whose rendered ink width fits it
    best (dynamic programming over all split points, matched font's widths when known)."""
    if not text or ink is None or getattr(ink, "size", 0) == 0: return text
    gaps = _ink_gaps(ink) if gaps is None else gaps
    keep_sp = set()
    if " " in text:                                            # OCR kept some spaces: only fill in the missing ones
        words = text.split()
        if not gaps or len(gaps) <= len(words) - 1: return text
        pos = 0
        for w_ in words[:-1]:
            pos += len(w_); keep_sp.add(pos)
        orig_text, text = text, "".join(words)
    n = len(text)
    if not gaps or n < 2: return text
    gaps = sorted(gaps)[:n - 1]
    h, w = ink.shape
    f = font or _width_font()
    P = [0.0] + [f.getlength(text[:i]) for i in range(1, n + 1)]
    path = getattr(f, "path", None); fs = getattr(f, "size", 100)
    lsb, rsb = [], []
    for i, c in enumerate(text):
        ib = _ink_box(path, fs, c) if path else None
        adv = P[i + 1] - P[i]
        lsb.append(ib[0] if ib else 0.0); rsb.append(adv - ib[2] if ib else 0.0)
    edges = [0] + [v for g in gaps for v in g] + [w]
    segw = [max(0.0, edges[2 * k + 1] - edges[2 * k]) for k in range(len(gaps) + 1)]
    inkw = lambda a, b: max(1e-3, P[b] - P[a] - lsb[a] - rsb[b - 1])
    k = len(segw); INF = float("inf")

    def prior(a):                                              # how plausible a word break between text[a-1] and text[a] is
        p, q = text[a - 1], text[a]
        if p in ":;,.)]!?" and q not in ".,:;": return -0.45
        if q in "([" : return -0.1
        if p.isdigit() and q.isdigit(): return 0.9
        if p.isdigit() != q.isdigit() and p.isalnum() and q.isalnum(): return -0.05
        if p.isupper() and q.islower(): return 0.12
        if q in ".,:;%)!?": return 0.3
        return 0.0
    pri = [0.0] + [prior(a) - (0.6 if a in keep_sp else 0.0) for a in range(1, n)]
    scale = sum(segw) / inkw(0, n); cuts = None
    for _ in range(2):                                         # solve, refit the scale on the chosen split, solve again
        dp = [[INF] * (n + 1) for _ in range(k + 1)]; bk = [[0] * (n + 1) for _ in range(k + 1)]
        dp[0][0] = 0.0
        for j in range(1, k + 1):
            for i in range(j, n - (k - j) + 1):
                best, arg = INF, 0
                for a in range(j - 1, i):
                    if dp[j - 1][a] == INF: continue
                    c = dp[j - 1][a] + ((segw[j - 1] - inkw(a, i) * scale) / max(4.0, h)) ** 2 + (pri[a] if a > 0 else 0.0)
                    if c < best: best, arg = c, a
                dp[j][i], bk[j][i] = best, arg
        if dp[k][n] == INF: return text
        cuts, i = [], n
        for j in range(k, 0, -1):
            cuts.append(i); i = bk[j][i]
        cuts = sorted(cuts)                                    # segment ends
        starts = [0] + cuts[:-1]
        scale = sum(segw) / max(1e-3, sum(inkw(a, b) for a, b in zip(starts, cuts)))
    cuts = starts[1:]
    cuts = set(c for c in cuts if 0 < c < n)
    return "".join((" " if i in cuts else "") + c for i, c in enumerate(text))


def _membrane(img, hole, iters=300):
    """Smooth (harmonic) fill of `hole` pixels from their surroundings — multigrid Jacobi, no seams."""
    import numpy as np, cv2
    h, w = hole.shape
    if not hole.any(): return img
    out = img.copy()
    if min(h, w) >= 32 and iters > 40:                         # coarse solve first → fast convergence
        sh, sw = max(8, h // 4), max(8, w // 4)
        kw = (~hole).astype(np.float32)                        # mask-aware downscale (holes must not darken it)
        wsm = cv2.resize(kw, (sw, sh), interpolation=cv2.INTER_AREA)
        small = cv2.resize(img * kw[..., None], (sw, sh), interpolation=cv2.INTER_AREA) / np.maximum(wsm, 1e-6)[..., None]
        sm_hole = wsm < 0.5
        sm = _membrane(small, sm_hole, iters)
        out[hole] = cv2.resize(sm, (w, h), interpolation=cv2.INTER_LINEAR)[hole]
        iters = max(40, iters // 4)
    else:
        known = out[~hole].mean(axis=0) if (~hole).any() else 0
        out[hole] = known
    hm = hole[..., None]
    for _ in range(iters):
        out = np.where(hm, cv2.blur(out, (3, 3)), img)
    return out


def _texture_fill(orig, mask, valid, hb):
    """Background rebuild for gradients, grain and soft textures: a seamless smooth colour field (harmonic
    fill from the clean pixels around the hole) plus real grain copied from nearby clean background.
    Looks like the surrounding paper/photo instead of a smear. Returns (filled rgb, texture std)."""
    import numpy as np, cv2
    H, W = mask.shape; m = mask > 0
    ys, xs = np.where(m)
    if not len(xs): return orig.copy(), 0.0
    y0, y1, x0, x1 = ys.min(), ys.max() + 1, xs.min(), xs.max() + 1
    mh = y1 - y0; P = max(mh, hb) * 2 + 8
    Y0, Y1, X0, X1 = max(0, y0 - P), min(H, y1 + P), max(0, x0 - P), min(W, x1 + P)
    o = orig[Y0:Y1, X0:X1].astype(np.float32); mm = m[Y0:Y1, X0:X1]
    good = valid[Y0:Y1, X0:X1] & ~mm; v = good.astype(np.float32)
    s0 = max(2.0, hb * 0.08)                                   # light, ink-free smoothing of the background
    wv = cv2.GaussianBlur(v, (0, 0), s0)
    B = cv2.GaussianBlur(o * v[..., None], (0, 0), s0) / np.maximum(wv, 1e-6)[..., None]
    known = good & (wv > 0.25)
    low = _membrane(np.where(known[..., None], B, 0).astype(np.float32), ~known)
    res = o - low
    rstd = float(res[good].std(axis=0).mean()) if good.sum() > 30 else 0.0
    # grain: copy the residual from the nearest clean rows above/below (same columns → same texture scale)
    out = o.copy(); my0, my1 = y0 - Y0, y1 - Y0; cols = slice(x0 - X0, x1 - X0)
    fill_res = np.zeros((my1 - my0, x1 - x0, 3), np.float32); have = np.zeros((my1 - my0, x1 - x0), bool)
    for d in (mh + 3, -(mh + 3), mh // 2 + 2, -(mh // 2 + 2), 2 * mh + 5, -(2 * mh + 5)):
        a0, a1 = my0 + d, my1 + d
        if a0 < 0 or a1 > out.shape[0]: continue
        src_ok = good[a0:a1, cols] & ~have
        fill_res[src_ok] = res[a0:a1, cols][src_ok]; have |= src_ok
        if have.all(): break
    if not have.all():                                         # leftovers: matching random grain
        sd = res[good].std(axis=0) if good.sum() > 30 else np.zeros(3)
        nz = cv2.GaussianBlur(np.random.normal(0, 1, fill_res.shape).astype(np.float32), (0, 0), 0.7) * 1.6 * sd
        fill_res[~have] = nz[~have]
    blk = low[my0:my1, cols] + fill_res
    sub = out[my0:my1, cols]; hm = mm[my0:my1, cols]
    sub[hm] = blk[hm]
    res_img = orig.copy(); res_img[Y0:Y1, X0:X1] = np.clip(out, 0, 255).astype(np.uint8)
    return res_img, rstd


def smart_fill(rgb, mask):
    """Pick the most natural background rebuild: exact colour for flat UI, harmonic field + real grain for
    gradients/paper/soft photos, LaMa (GPU) for real structure (objects, people, detailed scenes)."""
    import numpy as np, cv2
    m = (mask > 0).astype(np.uint8)
    if not m.any(): return rgb
    ys, xs = np.where(m); hb = max(8, int(min(ys.max() - ys.min(), xs.max() - xs.min()) + 1))
    ring = (cv2.dilate(m, np.ones((15, 15), np.uint8)) > 0) & (cv2.dilate(m, np.ones((5, 5), np.uint8)) == 0)
    rp = rgb[ring].astype(np.float32)
    if len(rp) > 30 and float(rp.std(axis=0).mean()) < 3.0:
        out = rgb.copy(); out[m > 0] = np.median(rp, axis=0).astype(np.uint8); return out
    filled, rstd = _texture_fill(rgb, m, np.ones(m.shape, bool), hb)
    # structure test: strong edges around the hole mean objects/lines that a smooth fill would smear
    g = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    edges = cv2.Canny(g, 60, 150) > 0
    edge_frac = float(edges[ring].mean()) if ring.any() else 0.0
    if rstd < 9 and edge_frac < 0.04: return filled
    return inpaint(rgb, m)


def _subpixel_aa(rgb, strength):
    """Detect ClearType-style coloured fringes (Windows screenshots)."""
    import numpy as np
    edge = (strength > 0.15) & (strength < 0.85)
    if edge.sum() < 20: return False
    px = rgb[edge].astype(float)
    chroma = (np.abs(px[:, 0] - px[:, 1]) + np.abs(px[:, 1] - px[:, 2])).mean()
    core = rgb[strength > 0.9].astype(float)
    base = (np.abs(core[:, 0] - core[:, 1]) + np.abs(core[:, 1] - core[:, 2])).mean() if len(core) else 0
    return chroma > 18 and chroma > base + 12


def _noise_sigma(rgb, mask):
    import numpy as np, cv2
    g = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY).astype(np.float32)
    hp = g - cv2.GaussianBlur(g, (0, 0), 1.5)
    v = hp[mask]
    return float(np.median(np.abs(v)) * 1.4826) if v.size > 50 else 0.0


def _jpeg_quality(patch):
    """Estimate the JPEG quality that produced `patch` (lowest re-compression error)."""
    import numpy as np
    best, err0 = None, None
    arr = np.asarray(patch, np.float32)
    for q in (98, 95, 92, 90, 87, 85, 82, 80, 75, 70, 65, 60, 50, 40):
        buf = io.BytesIO(); patch.save(buf, "JPEG", quality=q); rec = np.asarray(Image.open(buf), np.float32)
        e = float(np.abs(rec - arr).mean())
        if err0 is None or e < err0 - 0.02: best, err0 = q, e
    return best, err0


def _draw_line(draw, x, y, text, font, tracking=0.0, fill=255):
    if abs(tracking) < 0.05:
        draw.text((x, y), text, font=font, fill=fill, anchor="ls"); return
    for i, ch in enumerate(text):
        draw.text((x + font.getlength(text[:i]) + i * tracking, y), ch, font=font, fill=fill, anchor="ls")


def retext_image(img, box, new_text, orig_text=None, color=None, align="left", jpeg_hint=None):
    """Replace the text in `box` (image px) so it looks untouched: same font, weight, size, colour,
    spacing, anti-aliasing (incl. ClearType), blur, grain and JPEG texture."""
    import numpy as np, cv2
    src = img.convert("RGBA"); alpha = src.getchannel("A")
    orig = np.array(src.convert("RGB")); rgb = orig.copy()
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY); H, W = gray.shape
    b = [max(0, box[0]), max(0, box[1]), min(W, box[2]), min(H, box[3])]
    tb, ink = _tight_box(gray, b)
    x0, y0, x1, y1 = [int(v) for v in tb]
    if ink is None or x1 - x0 < 3 or y1 - y0 < 3: raise ValueError("Couldn't find the text pixels in that area.")
    if not orig_text:
        found = ocr_boxes(Image.fromarray(orig[max(0, y0 - 6):y1 + 6, max(0, x0 - 6):x1 + 6]))
        orig_text = " ".join(f["text"] for f in found) or str(new_text)
    first = _respace(orig_text.split("\n")[0], ink)
    crop = orig[y0:y1, x0:x1]
    tc, bc, bstd = _style_from_pixels(crop, ink)
    if color: tc = tuple(int(c * 255) for c in _rgb(color))
    strength = _ink_strength(crop, tc, bc)
    th = y1 - y0
    # ---- 1. erase the old text and rebuild what was behind it
    pad = max(3, int(th * 0.4))
    X0, Y0, X1, Y1 = max(0, x0 - pad), max(0, y0 - pad), min(W, x1 + pad), min(H, y1 + pad)
    mask = np.zeros((H, W), np.uint8)
    mask[y0:y1, x0:x1] = (strength > 0.06).astype(np.uint8)
    mask = cv2.dilate(mask, np.ones((3, 3), np.uint8), iterations=max(1, th // 12))
    ring = np.zeros((H, W), bool); ring[Y0:Y1, X0:X1] = True; ring &= mask == 0
    if bstd < 3.5:                                              # flat UI / document background → exact colour
        rgb[mask > 0] = np.array(bc, np.uint8)
    else:
        rgb = inpaint(rgb, mask)
    if not str(new_text).strip():
        out = Image.fromarray(rgb); out.putalpha(alpha); return out, {"font": None, "removed": True, "lama": FEATURES.get("lama")}
    # ---- 2. identify the font
    m = match_font(strength, first)
    if not m: raise ValueError("No usable fonts found on the server.")
    score, fd, size, sx, weight, blur_sig = m
    path = fd["path"]; f = _tt(path, size)
    oib = _ink_box(path, size, first) or f.getbbox(first, anchor="ls")
    nat_w = max(1, oib[2] - oib[0]); ratio = (x1 - x0) / nat_w
    stretch, tracking = 1.0, 0.0
    if abs(ratio - 1) > 0.03:
        if abs(ratio - 1) <= 0.14 and len(first) > 2: tracking = (x1 - x0 - nat_w) / (len(first) - 1)
        else: stretch = ratio
    # ---- 3. render the new text the same way the original was rendered
    lines = str(new_text).split("\n"); lh = size * 1.2
    sub = _subpixel_aa(crop, strength) and bstd < 6
    ss = 3 if sub else 1
    fbig = _tt(path, size * ss) if ss > 1 else f
    widths = [fbig.getlength(li) + len(li) * abs(tracking) * ss for li in lines]
    m0 = int(size * ss * 0.6)
    lw = int(max(widths) + 2 * m0); lhh = int(lh * ss * len(lines) + 2 * m0)
    layer = Image.new("L", (lw, lhh), 0); d = ImageDraw.Draw(layer)
    for i, li in enumerate(lines):
        if not li.strip(): continue
        ib_l = _ink_box(path, size * ss, li)
        _draw_line(d, m0 - (ib_l[0] if ib_l else 0), m0 - oib[1] * ss + i * lh * ss, li, fbig, tracking * ss)
    A = np.asarray(layer, np.float32) / 255.0
    if ss > 1:                                                 # ClearType: 3× horizontal coverage → RGB subpixels
        A = cv2.resize(A, (A.shape[1], A.shape[0] // 3), interpolation=cv2.INTER_AREA)
        A = cv2.filter2D(A, -1, np.array([[1, 2, 3, 2, 1]], np.float32) / 9)
        w3 = A.shape[1] // 3 * 3; A = A[:, :w3]
        A = np.stack([A[:, 0::3], A[:, 1::3], A[:, 2::3]], axis=-1)
        m0x, m0y = m0 / 3, m0 / 3
    else:
        if stretch != 1.0:
            A = cv2.resize(A, (max(1, int(A.shape[1] * stretch)), A.shape[0]), interpolation=cv2.INTER_AREA if stretch < 1 else cv2.INTER_CUBIC)
        A = np.repeat(A[..., None], 3, axis=-1)
        m0x, m0y = m0 * stretch, m0
    if blur_sig: A = cv2.GaussianBlur(A, (0, 0), blur_sig)
    if weight > 1.3 and size > 18: A = cv2.dilate(A, np.ones((2, 2), np.uint8))
    A = np.clip(A, 0, 1)
    ox, oy = int(round(x0 - m0x)), int(round(y0 - m0y))
    hh, ww = A.shape[:2]
    ax0, ay0 = max(0, -ox), max(0, -oy); bx0, by0 = max(0, ox), max(0, oy)
    bx1, by1 = min(W, ox + ww), min(H, oy + hh)
    if bx1 <= bx0 or by1 <= by0: raise ValueError("Text landed outside the image.")
    Aw = A[ay0:ay0 + (by1 - by0), ax0:ax0 + (bx1 - bx0)]
    region = rgb[by0:by1, bx0:bx1].astype(np.float32)
    col = np.broadcast_to(np.array(tc, np.float32), region.shape).copy()
    core = strength > 0.85
    if core.sum() > 30:                                        # keep a vertical colour gradient if the original has one
        yy_c = np.where(core)[0].astype(np.float32); vals = crop[core].astype(np.float32)
        if np.ptp(yy_c) > 3:
            k = np.polyfit(yy_c, vals, 1)
            if np.abs(k[0]).max() * th > 25:
                yy = (np.arange(by0, by1) - y0).astype(np.float32)[:, None]
                col = np.repeat((k[0][None, :] * yy + k[1][None, :])[:, None, :], bx1 - bx0, axis=1)
    comp = region * (1 - Aw) + np.clip(col, 0, 255) * Aw
    sig = _noise_sigma(orig, ring)
    if sig > 1.2:                                               # same sensor / scan grain as the surroundings
        comp += np.random.normal(0, sig, comp.shape).astype(np.float32) * np.clip(Aw.max(axis=-1, keepdims=True) * 1.5, 0, 1)
    rgb[by0:by1, bx0:bx1] = np.clip(comp, 0, 255).astype(np.uint8)
    out = Image.fromarray(rgb)
    q = None
    if jpeg_hint or (bstd > 2 and sig > 0.8):                  # match the photo's JPEG block texture
        gx0, gy0 = max(0, (min(bx0, X0) // 8) * 8), max(0, (min(by0, Y0) // 8) * 8)
        gx1, gy1 = min(W, -(-max(bx1, X1) // 8) * 8), min(H, -(-max(by1, Y1) // 8) * 8)
        q, err = _jpeg_quality(Image.fromarray(orig[gy0:gy1, gx0:gx1]))
        if q and q < 97 and (jpeg_hint or err < 1.2):
            buf = io.BytesIO(); out.crop((gx0, gy0, gx1, gy1)).save(buf, "JPEG", quality=q)
            out.paste(Image.open(buf), (gx0, gy0))
    out.putalpha(alpha)
    return out, {"font": f"{fd['family']} {fd['weight']}{' italic' if fd['italic'] else ''}", "size_px": round(size, 1),
                 "match": round(float(score), 3), "color": "#%02x%02x%02x" % tc, "cleartype": sub, "jpeg_q": q,
                 "lama": FEATURES.get("lama")}


# ---------- line editing: change only the characters that differ ----------
_OCR_ALIKE = {"0": "0Oo", "o": "0Oo", "1": "1lI|i", "l": "1lI|i", "i": "1lI|i", "5": "5Ss", "s": "5Ss", "8": "8B", "b": "8B", "2": "2Zz", "z": "2Zz"}


def _find_pattern(find):
    parts = []
    for ch in re.sub(r"\s+", "", find):
        alike = _OCR_ALIKE.get(ch.lower())
        parts.append("[" + re.escape(alike) + "]" if alike else re.escape(ch))
    return re.compile(r"\s*".join(parts), re.I)


def _edge_softness(a):
    return float(((a > 0.15) & (a < 0.85)).mean() / max(1e-3, (a >= 0.5).mean()))


def _analyze_line(orig, box, text, only=None, respace=True):
    """Measure one text line: ink box, colours, font, size, spacing, pen origin, blur."""
    import numpy as np, cv2
    gray = cv2.cvtColor(orig, cv2.COLOR_RGB2GRAY); H, W = gray.shape
    b = [max(0, box[0]), max(0, box[1]), min(W, box[2]), min(H, box[3])]
    tb, ink = _tight_box(gray, b)
    x0, y0, x1, y1 = [int(v) for v in tb]
    if ink is None or x1 - x0 < 3 or y1 - y0 < 3: raise ValueError("Couldn't find the text pixels there.")
    raw = text
    text = _respace(raw, ink) if respace else raw
    crop = orig[y0:y1, x0:x1]
    tc, bc, bstd = _style_from_pixels(crop, ink)
    strength = _ink_strength(crop, tc, bc)
    m = match_font(strength, text, only=only)
    if not m: raise ValueError("No usable fonts found on the server.")
    if respace and text != raw:                                # second pass: real word gaps, matched font's widths
        fpath, fsize = m[1]["path"], m[2]; raw_ns = raw.replace(" ", "")
        ibr = _ink_box(fpath, fsize, raw_ns); natw = max(1.0, (ibr[2] - ibr[0]) if ibr else 1.0)
        gaps = _ink_gaps(ink); gapw = sum(e - s for s, e in gaps)
        good = _word_gap_filter(gaps, raw_ns, fpath, fsize, max(0.3, (ink.shape[1] - gapw) / natw), ink.shape[0])
        t2 = _respace(raw, ink, _tt(fpath, 100), gaps=good) if good else raw
        if t2 != text:
            m2 = match_font(strength, t2, only=only)
            if m2 and m2[0] >= m[0] - 0.01: text, m = t2, m2
    score, fd, size, sx, weight, blur_sig = m
    path = fd["path"]; f = _tt(path, size)
    ib = _ink_box(path, size, text) or f.getbbox(text, anchor="ls")
    nat = max(1.0, ib[2] - ib[0]); ratio = (x1 - x0) / nat
    stretch, tracking = 1.0, 0.0
    if abs(ratio - 1) > 0.025:
        if abs(ratio - 1) <= 0.14 and len(text) > 2: tracking = (x1 - x0 - nat) / max(1, len(text) - 1)
        else: stretch = ratio
    crisp = _render_mask(path, text, x1 - x0, y1 - y0)
    soft = _edge_softness(strength) / max(1e-3, _edge_softness(crisp[0])) if crisp else 1
    if soft < 1.25: blur_sig = 0.0
    pen0 = x0 - ib[0] * stretch                                    # x of the line's pen origin
    base = y0 - ib[1]                                              # baseline y
    segs = None                                                # measured ink extent of every word
    nsp = len([w_ for w_ in text.split(" ") if w_]) - 1
    if nsp >= 1:
        allg = _ink_gaps(ink)
        if len(allg) >= nsp:
            gg = sorted(sorted(allg, key=lambda g_: g_[0] - g_[1])[:nsp])
            if len(allg) == nsp or min(e - s_ for s_, e in gg) > 1.4 * max(1, max([e - s_ for s_, e in allg if (s_, e) not in gg] or [0])):
                ed = [0] + [v for g_ in gg for v in g_] + [ink.shape[1]]
                segs = [(x0 + ed[2 * i], x0 + ed[2 * i + 1]) for i in range(nsp + 1)]
    elif nsp == 0:
        segs = [(x0, x1)]
    return dict(segs=segs, x0=x0, y0=y0, x1=x1, y1=y1, ink=ink, strength=strength, tc=tc, bc=bc, bstd=bstd, text=text, fd=fd,
                path=path, size=size, font=f, stretch=stretch, tracking=tracking, pen0=pen0, base=base,
                weight=weight, blur=blur_sig, score=score, sub=_subpixel_aa(crop, strength) and bstd < 6)


def _pen_x(L, i):
    f, t = L["font"], L["text"]
    return L["pen0"] + (f.getlength(t[:i]) + i * L["tracking"]) * L["stretch"]


def _snap(L, x, lo, hi):
    """Move a cut position to the emptiest column nearby so no glyph gets sliced."""
    import numpy as np
    col = L["strength"].sum(axis=0); rad = max(2, int(L["size"] * 0.22))
    a, b = max(lo, int(x) - rad), min(hi, int(x) + rad)
    if b <= a: return int(round(x))
    rel = np.arange(a, b) - L["x0"]
    rel = rel[(rel >= 0) & (rel < len(col))]
    if not len(rel): return int(round(x))
    cost = col[rel] + 0.02 * np.abs(rel + L["x0"] - x)
    return int(rel[int(np.argmin(cost))] + L["x0"])


def _render_run(L, text, ss=1):
    """Coverage map (H×W×3 floats) for `text` drawn like the analysed line, plus its pen offset."""
    import numpy as np, cv2
    size, path = L["size"], L["path"]
    f = _tt(path, size * ss) if ss > 1 else L["font"]
    m0 = int(size * ss * 0.6)
    w = int(f.getlength(text) + len(text) * abs(L["tracking"]) * ss + 2 * m0)
    h = int(size * ss * 1.6 + 2 * m0)
    layer = Image.new("L", (max(1, w), max(1, h)), 0)
    _draw_line(ImageDraw.Draw(layer), m0, m0 + size * ss, text, f, L["tracking"] * ss)
    A = np.asarray(layer, np.float32) / 255.0
    if ss > 1:
        A = cv2.resize(A, (A.shape[1], A.shape[0] // 3), interpolation=cv2.INTER_AREA)
        A = cv2.filter2D(A, -1, np.array([[1, 2, 3, 2, 1]], np.float32) / 9)
        A = A[:, :A.shape[1] // 3 * 3]; A = np.stack([A[:, 0::3], A[:, 1::3], A[:, 2::3]], axis=-1)
        ox, oy = m0 / 3, m0 / 3 + size
    else:
        if L["stretch"] != 1.0:
            A = cv2.resize(A, (max(1, int(A.shape[1] * L["stretch"])), A.shape[0]), interpolation=cv2.INTER_AREA if L["stretch"] < 1 else cv2.INTER_CUBIC)
        A = np.repeat(A[..., None], 3, axis=-1)
        ox, oy = m0 * L["stretch"], m0 + size
    if L["blur"]: A = cv2.GaussianBlur(A, (0, 0), L["blur"])
    if L["weight"] > 1.3 and size > 18: A = cv2.dilate(A, np.ones((2, 2), np.uint8))
    adv = (f.getlength(text) / ss + len(text) * L["tracking"]) * L["stretch"]
    return np.clip(A, 0, 1), ox, oy, adv


def _blend(rgb, A, ox, oy, color):
    import numpy as np
    H, W = rgb.shape[:2]; hh, ww = A.shape[:2]
    ox, oy = int(round(ox)), int(round(oy))
    ax0, ay0 = max(0, -ox), max(0, -oy); bx0, by0 = max(0, ox), max(0, oy)
    bx1, by1 = min(W, ox + ww), min(H, oy + hh)
    if bx1 <= bx0 or by1 <= by0: return (0, 0, 0, 0)
    Aw = A[ay0:ay0 + (by1 - by0), ax0:ax0 + (bx1 - bx0)]
    reg = rgb[by0:by1, bx0:bx1].astype(np.float32)
    rgb[by0:by1, bx0:bx1] = np.clip(reg * (1 - Aw) + np.array(color, np.float32) * Aw, 0, 255).astype(np.uint8)
    return (bx0, by0, bx1, by1)


def _adv(L, s):
    return (L["font"].getlength(s) + len(s) * L["tracking"]) * L["stretch"]


def edit_line(img, box, line_text, start, end, new_sub, color=None, jpeg_hint=None):
    """Replace characters [start:end] of an OCR'd line with new_sub. Everything else keeps its original
    pixels; text after the edit slides so spacing stays natural. The font is measured on the words being
    edited (so 'Label: value' lines keep both styles)."""
    import numpy as np, cv2
    src = img.convert("RGBA"); alpha = src.getchannel("A")
    orig = np.array(src.convert("RGB")); rgb = orig.copy(); H, W = rgb.shape[:2]
    L = _analyze_line(orig, box, line_text)
    t = L["text"]
    if line_text != t:
        start, end = _map_idx(line_text, t, start), _map_idx(line_text, t, end, is_start=False)
    x0, y0, x1, y1 = L["x0"], L["y0"], L["x1"], L["y1"]
    # context = the words around the edit (≥4 chars) → measure the font there
    ws = t.rfind(" ", 0, start) + 1; we = t.find(" ", end); we = len(t) if we < 0 else we
    if we - ws < 4:
        nxt = t.find(" ", we + 1); prv = t.rfind(" ", 0, max(0, ws - 1)) + 1 if ws > 0 else 0
        if we < len(t): we = len(t) if nxt < 0 else nxt
        elif ws > 0: ws = prv
    C = L
    if (ws, we) != (0, len(t)):
        mid = lambda i: (_pen_x(L, i) + _pen_x(L, i + 1)) / 2     # centre of a space character
        segs = L.get("segs"); wi0, wi1 = t[:ws].count(" "), t[:we].count(" ")
        if segs and wi1 < len(segs) and t.count(" ") == len(segs) - 1:   # real word gaps measured on the ink
            cx0 = x0 if ws == 0 else int((segs[wi0 - 1][1] + segs[wi0][0]) / 2)
            cx1 = x1 if we >= len(t) else int((segs[wi1][1] + segs[wi1 + 1][0]) / 2) + 1
        else:
            cx0 = x0 if ws == 0 else _snap(L, mid(ws - 1), x0, x1)
            cx1 = x1 if we >= len(t) else _snap(L, mid(we), cx0, x1)
        try:
            cbox = [cx0 - 1, y0 - 1, cx1 + 1, y1 + 1]
            C = _analyze_line(orig, cbox, t[ws:we], respace=False)
            same = [f for f in _font_list() if f["family"] == L["fd"]["family"]]
            CL = _analyze_line(orig, cbox, t[ws:we], only=same, respace=False)   # line's family, best weight, on these words
            if CL["score"] >= C["score"] - 0.06: C = CL                # consistent with the line unless clearly different
        except Exception:
            C = L; ws, we = 0, len(t)
    tc = tuple(int(c * 255) for c in _rgb(color)) if color else C["tc"]
    cpen = lambda i: C["pen0"] + _adv(C, t[ws:i])               # pen x of char i (inside context)
    ct = t[ws:we]; cseg = C.get("segs") if C.get("segs") and len(C["segs"]) == ct.count(" ") + 1 else None
    s_word = start == ws or t[start - 1] == " "; e_word = end == we or (end < len(t) and t[end] == " ")
    xs = C["x0"] if start <= ws else _snap(C, cpen(start), C["x0"], C["x1"])
    xe = C["x1"] if end >= we else _snap(C, cpen(end), xs, C["x1"])
    if end >= we and we < len(t): xe = C["x1"]
    if cseg and s_word: xs = cseg[ct[:start - ws].count(" ")][0]    # measured ink edges beat font arithmetic
    if cseg and e_word: xe = max(xs + 1, cseg[ct[:max(0, end - ws - 1)].count(" ")][1])
    pad = max(2, int((y1 - y0) * 0.35))
    by0, by1 = max(0, y0 - pad), min(H, y1 + pad)
    tail_text = t[end:]
    ss = 3 if C["sub"] else 1
    if new_sub: A, ax, ay, adv_new = _render_run(C, new_sub, ss)
    else: A, ax, ay, adv_new = None, 0, 0, 0
    adv_old = _adv(C, t[start:end])
    pen_s = cpen(start)
    if new_sub and (start == ws or (cseg and s_word)) and new_sub[0] != " ":   # word start: align ink edges
        ib_new = _ink_box(C["path"], C["size"], new_sub)
        pen_s = xs - (ib_new[0] if ib_new else 0) * C["stretch"]
    delta = int(round(adv_new - adv_old)) if tail_text.strip() else 0
    tail, st = None, None
    if delta:
        tail = orig[by0:by1, xe:min(W, x1 + pad)].copy()
        hb = by1 - by0; wx0, wx1 = max(0, xe - 2 * hb), min(W, x1 + pad + 2 * hb)
        st = _local_strength(orig[by0:by1, wx0:wx1], L["tc"], k=min(255, (int(hb * 2.2) // 2) * 2 + 1))[:, xe - wx0:xe - wx0 + tail.shape[1]]
        st[y0 - by0:y1 - by0, :min(tail.shape[1], x1 - xe)] = np.maximum(st[y0 - by0:y1 - by0, :min(tail.shape[1], x1 - xe)], L["strength"][:, xe - x0:x1 - x0][:, :tail.shape[1]])
    ex1 = x1 if tail is not None else xe
    lpad = 0 if start > 0 else pad                             # cut sits in an empty gap → no need to bleed left
    rpad = pad if (end >= len(t) or tail is not None) else 0
    mx0, mx1 = max(0, xs - lpad), min(W, ex1 + rpad)
    hb = by1 - by0; wx0, wx1 = max(0, mx0 - 2 * hb), min(W, mx1 + 2 * hb)
    ls = _local_strength(orig[by0:by1, wx0:wx1], L["tc"], k=min(255, (int(hb * 2.2) // 2) * 2 + 1))[:, mx0 - wx0:mx1 - wx0]
    mask = np.zeros((H, W), np.uint8)
    mask[by0:by1, mx0:mx1] = (ls > 0.1).astype(np.uint8)
    mask[y0:y1, xs:ex1] |= (L["strength"][:, xs - x0:ex1 - x0] > 0.06).astype(np.uint8)
    mask = cv2.dilate(mask, np.ones((3, 3), np.uint8), iterations=max(1, (y1 - y0) // 10))
    if lpad == 0:                                              # never touch the characters before the edit,
        n_, lab, stats, _c = cv2.connectedComponentsWithStats((L["strength"] > 0.4).astype(np.uint8))
        rx = xs - x0; prev_end = -1                            # but clean the whole gap up to them (JPEG ringing)
        for ci in range(1, n_):
            l_, w_, area = stats[ci, 0], stats[ci, 2], stats[ci, 4]
            if area >= 3 and l_ + w_ / 2 < rx - 1: prev_end = max(prev_end, min(rx, l_ + w_))
        cut = max(0, x0 + prev_end + 2) if prev_end >= 0 else xs
        cut = min(cut, xs)
        if cut < xs: mask[by0:by1, cut:xs] = 1
        mask[:, :cut] = 0
    rx0, rx1 = max(0, xs - 2 * pad), min(W, ex1 + 2 * pad)
    ring = np.zeros((H, W), bool); ring[by0:by1, rx0:rx1] = True
    ring &= cv2.dilate(mask, np.ones((5, 5), np.uint8)) == 0
    anyink = _local_strength(orig[by0:by1, rx0:rx1], L["tc"], k=min(255, (int((by1 - by0) * 2.2) // 2) * 2 + 1)) > 0.06
    anyink = cv2.dilate(anyink.astype(np.uint8), np.ones((5, 5), np.uint8)) > 0
    ring[by0:by1, rx0:rx1] &= ~anyink                           # background only — no letters from neighbours
    rp = orig[ring].astype(np.float32)
    bg_std = float(rp.std(axis=0).mean()) if len(rp) > 30 else L["bstd"]
    bg_med = np.median(rp, axis=0) if len(rp) > 30 else np.array(L["bc"], np.float32)
    flat = bg_std < 4.0
    if flat:                                                   # plain UI / paper colour → exact fill
        rgb[mask > 0] = bg_med.astype(np.uint8)
    else:
        valid = np.ones((H, W), bool)
        vy0, vy1 = max(0, by0 - 3 * hb), min(H, by1 + 3 * hb); vx0, vx1 = max(0, rx0 - 3 * hb), min(W, rx1 + 3 * hb)
        reg = orig[vy0:vy1, vx0:vx1]
        ink_all = _local_strength(reg, L["tc"], k=min(255, (int(hb * 2.2) // 2) * 2 + 1)) > 0.3   # glyph cores only —
        dk = 2 * max(2, int(round(L["blur"] * 2 + (y1 - y0) * 0.06))) + 1                          # light grain stays "background"
        valid[vy0:vy1, vx0:vx1] = cv2.dilate(ink_all.astype(np.uint8), np.ones((dk, dk), np.uint8)) == 0
        filled, rstd = _texture_fill(orig, mask, valid, hb)
        if rstd < 14 or FEATURES.get("lama") is False:         # gradient / grain / soft texture → smooth field + real grain
            rgb = filled; FEATURES["fill"] = "texture"
        else:                                                  # real structure (photo) → LaMa on GPU
            rgb = inpaint(rgb, mask); FEATURES["fill"] = "lama"
    clean = rgb.copy(); boxes = []
    if new_sub:
        boxes.append(_blend(rgb, A, pen_s - ax, C["base"] - ay, tc))
    if tail is not None:                                       # put the rest of the line back, shifted
        tx = xe + delta; ww = tail.shape[1]; tx0, tx1 = max(0, tx), min(W, tx + ww)
        if tx1 > tx0:
            a_ = st[:, tx0 - tx:tx1 - tx][..., None]
            reg = rgb[by0:by1, tx0:tx1].astype(np.float32); px = tail[:, tx0 - tx:tx1 - tx].astype(np.float32)
            if flat:
                rgb[by0:by1, tx0:tx1] = np.where(a_ > 0.02, px, reg).astype(np.uint8)
            else:                                              # unmix: recover ink colour, recomposite on the new background
                bg_old = np.array(L["bc"], np.float32)
                ink_col = np.where(a_ > 0.05, (px - (1 - a_) * bg_old) / np.maximum(a_, 0.05), np.array(L["tc"], np.float32))
                rgb[by0:by1, tx0:tx1] = np.clip(reg * (1 - a_) + np.clip(ink_col, 0, 255) * a_, 0, 255).astype(np.uint8)
            boxes.append((tx0, by0, tx1, by1))
    sig = _noise_sigma(orig, ring)
    if sig > 1.2:
        for (a0, b0, a1, b1) in boxes:
            if a1 > a0:
                diff = np.abs(rgb[b0:b1, a0:a1].astype(np.float32) - clean[b0:b1, a0:a1]).max(axis=-1, keepdims=True)
                k = np.clip(diff / 40, 0, 1)
                rgb[b0:b1, a0:a1] = np.clip(rgb[b0:b1, a0:a1] + np.random.normal(0, sig, rgb[b0:b1, a0:a1].shape) * k, 0, 255).astype(np.uint8)
    out = Image.fromarray(rgb); q = None
    if jpeg_hint or (not flat and sig > 0.8):
        right = max(ex1, int(pen_s + adv_new), x1 + max(0, delta)) + pad
        gx0, gy0 = max(0, (max(0, xs - pad) // 8) * 8), max(0, (by0 // 8) * 8)
        gx1, gy1 = min(W, -(-min(W, right) // 8) * 8), min(H, -(-by1 // 8) * 8)
        if gx1 > gx0 and gy1 > gy0:
            q, err = _jpeg_quality(Image.fromarray(orig[gy0:gy1, gx0:gx1]))
            if q and q < 97 and (jpeg_hint or err < 1.2):
                buf = io.BytesIO(); out.crop((gx0, gy0, gx1, gy1)).save(buf, "JPEG", quality=q)
                out.paste(Image.open(buf), (gx0, gy0))
    out.putalpha(alpha)
    fd = C["fd"]
    return out, {"font": f"{fd['family']} {fd['weight']}{' italic' if fd['italic'] else ''}", "size_px": round(C["size"], 1),
                 "match": round(float(C["score"]), 3), "color": "#%02x%02x%02x" % tc, "cleartype": C["sub"], "jpeg_q": q,
                 "shift_px": delta, "fill": "flat" if flat else FEATURES.get("fill"), "lama": FEATURES.get("lama")}


def _map_idx(a, b, i, is_start=True):
    """Map an index in string a to the same character position in b (b = a with extra spaces)."""
    j = 0; k = 0
    while k < i and j < len(b):
        if a[k] == b[j]: k += 1; j += 1
        elif b[j] == " ": j += 1
        else: k += 1; j += 1
    if is_start:
        while j < len(b) and b[j] == " " and (i >= len(a) or a[i] != " "): j += 1
    return j


def _char_diff(old, new):
    p = 0
    while p < min(len(old), len(new)) and old[p] == new[p]: p += 1
    s = 0
    while s < min(len(old), len(new)) - p and old[-1 - s] == new[-1 - s]: s += 1
    return p, len(old) - s, new[p:len(new) - s]


def smart_retext(img, box, old_line, new_line, color=None, jpeg_hint=None):
    """Editor entry: the user typed a whole new line; only the changed characters are redrawn."""
    if "\n" in str(new_line):
        return retext_image(img, box, new_line, orig_text=old_line, color=color, jpeg_hint=jpeg_hint)
    a, b_, rep = _char_diff(old_line, str(new_line))
    if a == b_ and not rep and not color: return img, {"font": None, "unchanged": True}
    if color and a == b_ and not rep: a, b_, rep = 0, len(old_line), old_line
    return edit_line(img, box, old_line, a, b_, rep, color=color, jpeg_hint=jpeg_hint)


def replace_in_image(img, find, rep, jpeg_hint=None):
    pat = _find_pattern(find); n = 0; fonts = set()
    for bx in ocr_boxes(img):
        if not pat.search(bx["text"]): continue
        matches = list(pat.finditer(bx["text"]))
        for mt in reversed(matches):                           # right-to-left keeps earlier positions valid
            img, info = edit_line(img, bx["bbox"], bx["text"], mt.start(), mt.end(), rep, jpeg_hint=jpeg_hint)
            n += 1; fonts.add(info.get("font") or "")
    return img, n, ", ".join(sorted(f for f in fonts if f))


# ---------- PDFs: images inside pages ----------
def _scan_images(page, min_frac=0.0):
    pr = page.rect; out = []
    for info in page.get_image_info(xrefs=True):
        bb = fitz.Rect(info["bbox"]) & pr
        if bb.is_empty or not info.get("xref") or (info.get("width") or 0) <= 2 or (info.get("height") or 0) <= 2: continue
        if bb.get_area() / pr.get_area() >= min_frac: out.append((info["xref"], bb))
    return sorted(out, key=lambda t: -t[1].get_area())


def _is_jpeg_xref(doc, xref):
    try: return doc.extract_image(xref).get("ext") in ("jpeg", "jpg", "jpx")
    except Exception: return False


def scan_replace_doc(doc, find, rep):
    total, fonts = 0, set()
    for page in doc:
        for xref, bb in _scan_images(page, 0.02):
            try:
                im = _image_pil(doc, xref)
            except Exception:
                continue
            out, n, f = replace_in_image(im, find, rep, jpeg_hint=_is_jpeg_xref(doc, xref))
            if n:
                _remove_image(doc, page, xref, bb); _insert_pil(page, bb, out, keep=False)
                total += n; fonts.add(f)
    return total, ", ".join(sorted(x for x in fonts if x))


def pdf_ocr_layout(doc, pno, img_bbox=None):
    page = doc[pno]; imgs = _scan_images(page)
    if not imgs: return {"boxes": [], "image": None}
    if img_bbox:
        want = _rect_of(img_bbox)
        xref, bb = max(imgs, key=lambda t: (t[1] & want).get_area())
    else:
        xref, bb = imgs[0]
    im = _image_pil(doc, xref)
    kx, ky = bb.width / im.width, bb.height / im.height
    import numpy as np, cv2
    rgb = np.array(im.convert("RGB")); gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    out = []
    for i, bx in enumerate(ocr_boxes(im)):
        tb, ink = _tight_box(gray, bx["bbox"])
        x0, y0, x1, y1 = [int(v) for v in tb]
        if ink is not None and ink.size:
            tc, bc, _ = _style_from_pixels(rgb[y0:y1, x0:x1], ink)
        else:
            tc, bc = (0, 0, 0), (255, 255, 255)
        pb = [bb.x0 + bx["bbox"][0] * kx, bb.y0 + bx["bbox"][1] * ky, bb.x0 + bx["bbox"][2] * kx, bb.y0 + bx["bbox"][3] * ky]
        out.append({"id": f"s{i}", "scan": True, "text": _respace(bx["text"], ink) if ink is not None else bx["text"],
                    "bbox": [round(v, 2) for v in pb], "size": round((y1 - y0) * ky / 0.72, 1),
                    "color": "#%02x%02x%02x" % tc, "bg": "#%02x%02x%02x" % bc,
                    "family": "sans", "bold": False, "italic": False, "font": "image text"})
    return {"boxes": out, "image": [round(v, 2) for v in bb]}


def scan_text_op(doc, page, o):
    target = _rect_of(o["bbox"])
    imgs = _scan_images(page)
    if not imgs: raise ValueError("No image under that text.")
    xref, bb = max(imgs, key=lambda t: (t[1] & target).get_area())
    im = _image_pil(doc, xref); jh = _is_jpeg_xref(doc, xref)
    kx, ky = im.width / bb.width, im.height / bb.height
    pbox = [(target.x0 - bb.x0) * kx, (target.y0 - bb.y0) * ky, (target.x1 - bb.x0) * kx, (target.y1 - bb.y0) * ky]
    if o.get("orig"):
        out, info = smart_retext(im, pbox, o["orig"], o.get("text", ""), color=o.get("color"), jpeg_hint=jh)
    else:
        out, info = retext_image(im, pbox, o.get("text", ""), color=o.get("color"), jpeg_hint=jh)
    _remove_image(doc, page, xref, bb); _insert_pil(page, bb, out, keep=False)
    return info


def magic_erase_op(doc, page, o):
    """Paint-to-remove (objects, people, stamps, watermarks, text) with LaMa."""
    import numpy as np, cv2
    pts = [(float(x), float(y)) for x, y in o.get("points", [])]
    r = float(o.get("radius") or 12)
    kind = "brush"
    if o.get("rect"):
        rr = _rect_of(o["rect"]); pts = [(rr.x0, rr.y0), (rr.x1, rr.y1)]; kind = "rect"
    if not pts: return None
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    area = fitz.Rect(min(xs) - r, min(ys) - r, max(xs) + r, max(ys) + r) & page.rect
    imgs = [(x, b) for x, b in _scan_images(page) if (b & area).get_area() > 0.5 * area.get_area()]

    def build_mask(Wd, Ht, ox, oy, kx, ky):
        mm = np.zeros((Ht, Wd), np.uint8)
        P = [(int((px - ox) * kx), int((py - oy) * ky)) for px, py in pts]
        if kind == "rect":
            cv2.rectangle(mm, P[0], P[1], 255, -1)
        else:
            rad = max(2, int(r * kx))
            for a_, b_ in zip(P, P[1:]): cv2.line(mm, a_, b_, 255, rad * 2)
            for p_ in P: cv2.circle(mm, p_, rad, 255, -1)
        return mm

    if imgs:                                                    # erase inside the photo itself
        xref, bb = max(imgs, key=lambda t: (t[1] & area).get_area())
        im = _image_pil(doc, xref); kx, ky = im.width / bb.width, im.height / bb.height
        alpha = im.getchannel("A") if "A" in im.getbands() else None
        rgb = np.array(im.convert("RGB"))
        res = Image.fromarray(smart_fill(rgb, build_mask(rgb.shape[1], rgb.shape[0], bb.x0, bb.y0, kx, ky)))
        if alpha: res.putalpha(alpha)
        _remove_image(doc, page, xref, bb); _insert_pil(page, bb, res, keep=False)
    else:                                                       # vector page: rasterise the spot, erase, lay it back
        clip = (area + (-3 * r, -3 * r, 3 * r, 3 * r)) & page.rect
        z = 3.0; pix = page.get_pixmap(matrix=fitz.Matrix(z, z), clip=clip, alpha=False)
        rgb = np.array(Image.open(io.BytesIO(pix.tobytes("png"))).convert("RGB"))
        mm = build_mask(rgb.shape[1], rgb.shape[0], clip.x0, clip.y0, z, z)
        res = Image.fromarray(smart_fill(rgb, mm))
        for w_ in page.get_text("words"):
            wr = fitz.Rect(w_[:4]); cx, cy = int(((wr.x0 + wr.x1) / 2 - clip.x0) * z), int(((wr.y0 + wr.y1) / 2 - clip.y0) * z)
            if 0 <= cy < mm.shape[0] and 0 <= cx < mm.shape[1] and mm[cy, cx]: page.add_redact_annot(wr, fill=False)
        _apply_redactions(page, **_redact_kw())
        _insert_pil(page, clip, res, keep=False)
    return {"lama": FEATURES.get("lama")}


# ---------- chat tools ----------
@tool("image_replace_text", "Image", "Replace text in image",
      "Change or remove words inside a photo, screenshot, poster or scanned page so it looks untouched (OCR, AI background rebuild, font matching). Leave 'replace' empty to remove the text.",
      ["image", "pdf"], params=[P("find", "Find", default=""), P("replace", "Replace with (empty = remove)", default="")])
def t_image_replace_text(recs, p):
    r = recs[0]; find, rep = _s(p, "find"), _s(p, "replace")
    if not find.strip(): raise ValueError("Tell me which text to find.")
    if r["kind"] == "pdf":
        d = _open_pdf(r); n, fonts = scan_replace_doc(d, find, rep)
        if not n: d.close(); raise ValueError(f"Couldn't find '{find}' in the PDF's images.")
        return _save_pdf(d, f"{_stem(r)}_edited.pdf"), f"Replaced {n} line(s) in images · {fonts or 'font matched'}"
    im = _load_img(r); ext = _src_ext(r)
    out, n, fonts = replace_in_image(im, find, rep, jpeg_hint=ext in ("jpg", "jpeg"))
    if not n: raise ValueError(f"Couldn't find '{find}' in the image (OCR read: " + "; ".join(b["text"] for b in ocr_boxes(im)[:6]) + ").")
    q = 95 if ext in ("jpg", "jpeg", "webp") else 92
    return _save_img(out, f"{_stem(r)}_edited", ext if ext != "gif" else "png", q), f"{'Removed' if not rep else 'Replaced'} {n} line(s) · {fonts or 'font matched'}"


@tool("img_ai_upscale", "Image", "AI upscale (Real-ESRGAN)", "Sharpen and enlarge a photo 2×/3×/4× with Real-ESRGAN on the GPU — restores detail instead of stretching pixels.", ["image"],
      params=[P("scale", "Scale", "select", "2", ["2", "3", "4"])])
def t_ai_upscale(recs, p):
    im = _load_img(recs[0]); s = int(_num(p, "scale", 2))
    if im.width * im.height > 2_500_000: raise ValueError("Image is already large — try 2× on a smaller crop.")
    out = ai_upscale(im, s)
    return _save_img(out, f"{_stem(recs[0])}_x{s}_ai", _src_ext(recs[0]), 95), f"{im.width}×{im.height} → {out.width}×{out.height} · Real-ESRGAN on {FEATURES.get('esrgan', 'cpu')}"
