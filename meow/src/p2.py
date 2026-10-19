
# ==========================================================
# FILE TOOLS (used by the Tools panel AND by the model)
# ==========================================================
TOOLS = {}


def P(name, label, type="text", default="", options=None, hint=""):
    d = dict(name=name, label=label, type=type, default=default, hint=hint)
    if options: d["options"] = options
    return d


def tool(op, group, label, desc, accepts=(), multi=False, params=()):
    def deco(fn):
        TOOLS[op] = dict(op=op, group=group, label=label, desc=desc, accepts=list(accepts),
                         multi=multi, params=list(params), fn=fn)
        return fn
    return deco


def _num(p, k, d):
    try: return float(p.get(k, d))
    except Exception: return float(d)


def _s(p, k, d=""):
    v = p.get(k, d)
    return str(d if v is None else v)


def _rgb(h, d=(0.5, 0.5, 0.5)):
    h = str(h or "").strip().lstrip("#")
    if len(h) == 3: h = "".join(c * 2 for c in h)
    try: return tuple(int(h[i:i+2], 16) / 255 for i in (0, 2, 4))
    except Exception: return d


def _stem(rec): return os.path.splitext(rec["name"])[0]


def parse_pages(spec, n):
    spec = str(spec or "").replace(" ", "").lower()
    if spec in ("", "all"): return list(range(n))
    res = []
    for part in spec.split(","):
        if not part: continue
        if "-" in part:
            a, b = part.split("-", 1)
            a = int(a) if a else 1
            b = int(b) if b else n
            res += list(range(a - 1, b))
        else:
            res.append(int(part) - 1)
    res = [x for x in res if 0 <= x < n]
    if not res: raise ValueError(f"No valid pages in '{spec}' (document has {n} pages).")
    return res


def _open_pdf(rec, pw=""):
    d = fitz.open(rec["path"])
    if d.needs_pass and not d.authenticate(pw):
        raise ValueError(f"{rec['name']} is password-protected — use 'Unlock PDF' first.")
    return d


def _save_pdf(doc, name, **kw):
    fid, path = new_path(name)
    opts = dict(garbage=3, deflate=True); opts.update(kw)
    doc.save(path, **opts); doc.close()
    return register(fid, path, name, origin="tool")


def _img_as_pdf(path):
    im = ImageOps.exif_transpose(Image.open(path))
    im = _flatten(im)
    buf = io.BytesIO(); im.save(buf, "JPEG", quality=92)
    with fitz.open(stream=buf.getvalue(), filetype="jpg") as idoc:
        return fitz.open("pdf", idoc.convert_to_pdf())


def _flatten(im):
    if im.mode in ("RGBA", "LA", "P"):
        im = im.convert("RGBA")
        bg = Image.new("RGB", im.size, (255, 255, 255)); bg.paste(im, mask=im.getchannel("A"))
        return bg
    return im.convert("RGB") if im.mode != "RGB" else im


PDF, IMG = ["pdf"], ["image"]

# ---------------- PDF ----------------
@tool("pdf_merge", "PDF", "Merge PDFs", "Combine several PDFs (and images) into one PDF, in the order given.", ["pdf", "image"], multi=True)
def t_merge(recs, p):
    out = fitz.open()
    for r in recs:
        src = _img_as_pdf(r["path"]) if r["kind"] == "image" else _open_pdf(r)
        out.insert_pdf(src); src.close()
    n = out.page_count
    return _save_pdf(out, "merged.pdf"), f"Merged {len(recs)} files · {n} pages"


@tool("pdf_extract_pages", "PDF", "Extract pages", "Keep only the chosen pages, e.g. 1-3,7.", PDF,
      params=[P("pages", "Pages", default="1", hint="e.g. 1-3,7,10-")])
def t_extract(recs, p):
    d = _open_pdf(recs[0]); keep = parse_pages(p.get("pages"), d.page_count); d.select(keep)
    return _save_pdf(d, f"{_stem(recs[0])}_pages.pdf"), f"Extracted {len(keep)} pages"


@tool("pdf_delete_pages", "PDF", "Delete pages", "Remove the chosen pages.", PDF,
      params=[P("pages", "Pages to delete", default="1", hint="e.g. 2,5-6")])
def t_delete(recs, p):
    d = _open_pdf(recs[0]); n = d.page_count; rm = sorted(set(parse_pages(p.get("pages"), n)))
    if len(rm) >= n: raise ValueError("That would delete every page.")
    d.delete_pages(rm)
    return _save_pdf(d, f"{_stem(recs[0])}_edited.pdf"), f"Deleted {len(rm)} pages · {n-len(rm)} left"


@tool("pdf_reorder", "PDF", "Reorder pages", "Rearrange pages into a new order (pages may repeat).", PDF,
      params=[P("order", "New order", default="", hint="e.g. 3,1,2,4-")])
def t_reorder(recs, p):
    d = _open_pdf(recs[0]); order = parse_pages(p.get("order"), d.page_count); d.select(order)
    return _save_pdf(d, f"{_stem(recs[0])}_reordered.pdf"), f"Reordered → {len(order)} pages"


@tool("pdf_rotate", "PDF", "Rotate pages", "Rotate pages clockwise by 90/180/270°.", PDF,
      params=[P("pages", "Pages", default="all"), P("angle", "Angle", "select", "90", ["90", "180", "270"])])
def t_rotate(recs, p):
    d = _open_pdf(recs[0]); ang = int(_num(p, "angle", 90)) % 360
    pages = parse_pages(p.get("pages"), d.page_count)
    for i in pages: d[i].set_rotation((d[i].rotation + ang) % 360)
    return _save_pdf(d, f"{_stem(recs[0])}_rotated.pdf"), f"Rotated {len(pages)} pages by {ang}°"


@tool("pdf_watermark", "PDF", "Watermark", "Stamp diagonal text across every page.", PDF,
      params=[P("text", "Text", default="CONFIDENTIAL"), P("opacity", "Opacity (0-1)", "number", "0.18"),
              P("size", "Font size", "number", "60"), P("color", "Color", default="#7c3aed")])
def t_watermark(recs, p):
    d = _open_pdf(recs[0]); text = _s(p, "text", "CONFIDENTIAL")
    fs, op, col = _num(p, "size", 60), max(0.02, min(1, _num(p, "opacity", 0.18))), _rgb(p.get("color"), (0.5, 0.5, 0.5))
    tw = fitz.get_text_length(text, fontname="helv", fontsize=fs)
    for page in d:
        r = page.rect; c = fitz.Point(r.x0 + r.width / 2, r.y0 + r.height / 2)
        page.insert_text(fitz.Point(c.x - tw / 2, c.y + fs / 3), text, fontsize=fs, fontname="helv",
                         color=col, fill_opacity=op, morph=(c, fitz.Matrix(45)), overlay=True)
    n = d.page_count
    return _save_pdf(d, f"{_stem(recs[0])}_watermarked.pdf"), f"Watermarked {n} pages"


@tool("pdf_add_text", "PDF", "Add text", "Write text onto a page at x,y (points from top-left; A4 ≈ 595×842).", PDF,
      params=[P("page", "Page", "number", "1"), P("text", "Text", "textarea", "", hint="Text to add"),
              P("x", "X", "number", "72"), P("y", "Y", "number", "72"), P("size", "Font size", "number", "12"),
              P("color", "Color", default="#000000")])
def t_add_text(recs, p):
    d = _open_pdf(recs[0]); i = int(_num(p, "page", 1)) - 1
    if not 0 <= i < d.page_count: raise ValueError(f"Page must be 1–{d.page_count}")
    d[i].insert_text(fitz.Point(_num(p, "x", 72), _num(p, "y", 72)), _s(p, "text"), fontsize=_num(p, "size", 12),
                     fontname="helv", color=_rgb(p.get("color"), (0, 0, 0)))
    return _save_pdf(d, f"{_stem(recs[0])}_edited.pdf"), f"Added text on page {i+1}"


@tool("pdf_page_numbers", "PDF", "Page numbers", "Add 'Page X of N' to every page.", PDF,
      params=[P("position", "Position", "select", "bottom-center", ["bottom-center", "bottom-right", "top-right"]),
              P("size", "Font size", "number", "10")])
def t_pagenum(recs, p):
    d = _open_pdf(recs[0]); n = d.page_count; fs = _num(p, "size", 10); pos = _s(p, "position", "bottom-center")
    for i, page in enumerate(d):
        r = page.rect; label = f"Page {i+1} of {n}"; w = fitz.get_text_length(label, "helv", fs)
        x = r.width - w - 36 if "right" in pos else (r.width - w) / 2
        y = 30 if pos.startswith("top") else r.height - 24
        page.insert_text(fitz.Point(x, y), label, fontsize=fs, fontname="helv", color=(0.35, 0.35, 0.35))
    return _save_pdf(d, f"{_stem(recs[0])}_numbered.pdf"), f"Numbered {n} pages"


def _find_hits(page, find):
    return page.search_for(find) if find else []


def _span_style(page, rect):
    """Font, size, colour and baseline of the original text under `rect`."""
    best, area = None, 0
    for b in page.get_text("dict", clip=rect + (-2, -2, 2, 2))["blocks"]:
        for l in b.get("lines", []):
            for sp in l["spans"]:
                if not sp["text"].strip(): continue
                ov = fitz.Rect(sp["bbox"]) & rect
                a = ov.get_area() if not ov.is_empty else 0
                if a > area: best, area = sp, a
    return best


def _base14(font, flags):
    f = (font or "").lower()
    bold = bool(flags & 16) or any(k in f for k in ("bold", "black", "heavy", "semibold"))
    ital = bool(flags & 2) or "italic" in f or "oblique" in f
    if (flags & 8) or any(k in f for k in ("courier", "mono", "consol")):
        return {(0, 0): "cour", (1, 0): "cobo", (0, 1): "coit", (1, 1): "cobi"}[(bold, ital)]
    if (flags & 4) or any(k in f for k in ("times", "serif", "roman", "georgia", "garamond", "cambria", "book")) and "sans" not in f:
        return {(0, 0): "tiro", (1, 0): "tibo", (0, 1): "tiit", (1, 1): "tibi"}[(bold, ital)]
    return {(0, 0): "helv", (1, 0): "hebo", (0, 1): "heit", (1, 1): "hebi"}[(bold, ital)]


def _embedded_font(doc, page, span_font, text, cache):
    """Reuse the PDF's own embedded font when it contains every needed glyph."""
    norm = lambda n: re.sub(r"[\s_\-,]", "", (n or "").split("+")[-1]).lower()
    want = norm(span_font)
    for xref, ext, ftype, basefont, *_ in page.get_fonts():
        if norm(basefont) != want or ext in ("n/a", ""): continue
        key = (xref, text)
        if key in cache: return cache[key]
        try:
            buf = doc.extract_font(xref)[-1]
            f = fitz.Font(fontbuffer=buf)
            ok = buf and all(f.has_glyph(ord(c)) for c in text if not c.isspace())
            cache[key] = (f"MW{xref}", buf) if ok else None
        except Exception:
            cache[key] = None
        return cache[key]
    return None


@tool("pdf_replace_text", "PDF", "Find & replace text", "Replace a phrase everywhere, keeping the original font, size and colour (text PDFs, not scans).", PDF,
      params=[P("find", "Find", default=""), P("replace", "Replace with", default="")])
def t_replace(recs, p):
    d = _open_pdf(recs[0]); find, rep = _s(p, "find"), _s(p, "replace")
    if not find: raise ValueError("Tell me what text to find.")
    total, matched_fonts, cache = 0, set(), {}
    for page in d:
        hits = _find_hits(page, find)
        if not hits: continue
        jobs = []
        for r in hits:
            sp = _span_style(page, r) or {}
            st = _style_of(sp) if sp else dict(font=None, size=r.height * 0.8, color="#000000", family="sans", bold=False, italic=False)
            origin = fitz.Point(r.x0, sp["origin"][1]) if sp.get("origin") else fitz.Point(r.x0, r.y1 - st["size"] * 0.22)
            jobs.append((origin, st))
            matched_fonts.add((sp.get("font") or "?").split("+")[-1])
            page.add_redact_annot(r, fill=False)
        _apply_redactions(page, **_redact_kw())
        for origin, st in jobs:
            write_run(d, page, origin, rep, st, cache, keep_font=True)
        total += len(hits)
    if not total:                                   # scanned / image-only PDF → edit the text inside the images
        n, fonts = scan_replace_doc(d, find, rep)
        if not n: d.close(); raise ValueError(f"'{find}' wasn't found in the PDF (text or images).")
        return _save_pdf(d, f"{_stem(recs[0])}_replaced.pdf"), f"Replaced {n} line(s) inside page images · font ≈ {fonts or 'matched'}"
    return _save_pdf(d, f"{_stem(recs[0])}_replaced.pdf"), f"Replaced {total} occurrence(s) · matched font: {', '.join(sorted(matched_fonts))}"


@tool("pdf_redact", "PDF", "Redact text", "Black out every occurrence of a phrase (removes it permanently).", PDF,
      params=[P("find", "Text to redact", default="")])
def t_redact(recs, p):
    d = _open_pdf(recs[0]); find = _s(p, "find"); total = 0
    if not find: raise ValueError("Tell me what text to redact.")
    for page in d:
        hits = _find_hits(page, find)
        for r in hits: page.add_redact_annot(r, fill=(0, 0, 0))
        if hits: page.apply_redactions(); total += len(hits)
    if not total: d.close(); raise ValueError(f"'{find}' wasn't found.")
    return _save_pdf(d, f"{_stem(recs[0])}_redacted.pdf"), f"Redacted {total} occurrence(s)"


@tool("pdf_highlight", "PDF", "Highlight text", "Highlight every occurrence of a phrase.", PDF,
      params=[P("find", "Text to highlight", default="")])
def t_highlight(recs, p):
    d = _open_pdf(recs[0]); find = _s(p, "find"); total = 0
    for page in d:
        hits = _find_hits(page, find)
        if hits: page.add_highlight_annot(hits); total += len(hits)
    if not total: d.close(); raise ValueError(f"'{find}' wasn't found.")
    return _save_pdf(d, f"{_stem(recs[0])}_highlighted.pdf"), f"Highlighted {total} occurrence(s)"


@tool("pdf_compress", "PDF", "Compress PDF", "Shrink file size (downsamples big images).", PDF,
      params=[P("quality", "Image quality", "select", "medium", ["high", "medium", "low"])])
def t_compress(recs, p):
    d = _open_pdf(recs[0]); q = _s(p, "quality", "medium")
    dpi, jq = {"high": (150, 80), "medium": (110, 65), "low": (80, 45)}.get(q, (110, 65))
    try: d.rewrite_images(dpi_threshold=dpi + 30, dpi_target=dpi, quality=jq)
    except Exception: pass
    rec = _save_pdf(d, f"{_stem(recs[0])}_compressed.pdf", garbage=4, clean=True, deflate_images=True, deflate_fonts=True)
    before, after = recs[0]["size"], rec["size"]
    return rec, f"{before/1e6:.2f} MB → {after/1e6:.2f} MB ({100 - after*100//max(before,1)}% smaller)"


@tool("pdf_to_images", "PDF", "PDF → images", "Render pages as PNG images (zip for multiple pages).", PDF,
      params=[P("pages", "Pages", default="all"), P("dpi", "DPI", "number", "150")])
def t_pdf2img(recs, p):
    d = _open_pdf(recs[0]); pages = parse_pages(p.get("pages"), d.page_count); dpi = int(max(50, min(400, _num(p, "dpi", 150))))
    stem = _stem(recs[0])
    if len(pages) == 1:
        fid, path = new_path(f"{stem}_p{pages[0]+1}.png"); d[pages[0]].get_pixmap(dpi=dpi).save(path); d.close()
        return register(fid, path, f"{stem}_p{pages[0]+1}.png", "tool"), "Rendered 1 page"
    fid, path = new_path(f"{stem}_images.zip")
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        for i in pages: z.writestr(f"{stem}_p{i+1}.png", d[i].get_pixmap(dpi=dpi).tobytes("png"))
    d.close()
    return register(fid, path, f"{stem}_images.zip", "tool"), f"Rendered {len(pages)} pages"


@tool("pdf_to_text", "PDF", "PDF → text", "Export all text as a .txt file.", PDF)
def t_pdf2txt(recs, p):
    r = recs[0]; txt = r["text"] if r.get("text") else extract(r)
    fid, path = new_path(f"{_stem(r)}.txt"); open(path, "w", encoding="utf-8").write(txt)
    return register(fid, path, f"{_stem(r)}.txt", "tool"), f"{len(txt):,} characters"


@tool("pdf_protect", "PDF", "Password-protect", "Encrypt the PDF with a password (AES-256).", PDF,
      params=[P("password", "Password", "password", "")])
def t_protect(recs, p):
    pw = _s(p, "password")
    if not pw: raise ValueError("Enter a password.")
    d = _open_pdf(recs[0])
    return _save_pdf(d, f"{_stem(recs[0])}_protected.pdf", encryption=fitz.PDF_ENCRYPT_AES_256, owner_pw=pw, user_pw=pw), "Encrypted with AES-256"


@tool("pdf_unlock", "PDF", "Unlock PDF", "Remove the password from a PDF you know the password to.", PDF,
      params=[P("password", "Current password", "password", "")])
def t_unlock(recs, p):
    d = fitz.open(recs[0]["path"])
    if d.needs_pass and not d.authenticate(_s(p, "password")): d.close(); raise ValueError("Wrong password.")
    rec = _save_pdf(d, f"{_stem(recs[0])}_unlocked.pdf", encryption=fitz.PDF_ENCRYPT_NONE)
    extract(rec)
    return rec, "Password removed"


@tool("images_to_pdf", "PDF", "Images → PDF", "Turn images into a PDF, one per page, in order.", IMG, multi=True)
def t_img2pdf(recs, p):
    out = fitz.open()
    for r in recs:
        src = _img_as_pdf(r["path"]); out.insert_pdf(src); src.close()
    n = out.page_count
    return _save_pdf(out, "images.pdf"), f"{n} pages"


# ---------------- IMAGES ----------------
EXT_FMT = {"jpg": "JPEG", "jpeg": "JPEG", "png": "PNG", "webp": "WEBP", "bmp": "BMP", "gif": "GIF", "tiff": "TIFF"}


def _load_img(rec):
    im = Image.open(rec["path"]); im = ImageOps.exif_transpose(im); im.load(); return im


def _src_ext(rec):
    e = os.path.splitext(rec["name"])[1].lstrip(".").lower()
    return e if e in EXT_FMT else ("jpg" if e in ("heic", "heif") else "png")


def _save_img(im, stem, ext, quality=92):
    ext = ext.lower().replace("jpeg", "jpg")
    if ext not in EXT_FMT: ext = "png"
    fmt = EXT_FMT[ext]; name = f"{stem}.{ext}"
    if fmt in ("JPEG", "BMP"): im = _flatten(im)
    elif im.mode not in ("RGB", "RGBA", "L", "LA", "P"): im = im.convert("RGBA")
    fid, path = new_path(name)
    kw = {"quality": int(quality), "optimize": True} if fmt in ("JPEG", "WEBP") else ({"optimize": True} if fmt == "PNG" else {})
    im.save(path, fmt, **kw)
    return register(fid, path, name, origin="tool")


@tool("img_resize", "Image", "Resize", "Resize to a width/height (leave one blank to keep proportions).", IMG,
      params=[P("width", "Width px", "number", "1080"), P("height", "Height px", "number", "")])
def t_resize(recs, p):
    im = _load_img(recs[0]); w = p.get("width") or ""; h = p.get("height") or ""
    w = int(float(w)) if str(w).strip() else 0; h = int(float(h)) if str(h).strip() else 0
    if not w and not h: raise ValueError("Give a width or a height.")
    if not h: h = round(im.height * w / im.width)
    if not w: w = round(im.width * h / im.height)
    out = im.resize((w, h), Image.LANCZOS)
    return _save_img(out, f"{_stem(recs[0])}_{w}x{h}", _src_ext(recs[0])), f"{im.width}×{im.height} → {w}×{h}"


@tool("img_crop", "Image", "Crop", "Crop to a box in pixels (left, top, right, bottom).", IMG,
      params=[P("left", "Left", "number", "0"), P("top", "Top", "number", "0"), P("right", "Right", "number", ""), P("bottom", "Bottom", "number", "")])
def t_crop(recs, p):
    im = _load_img(recs[0])
    box = (int(_num(p, "left", 0)), int(_num(p, "top", 0)),
           int(_num(p, "right", im.width) or im.width), int(_num(p, "bottom", im.height) or im.height))
    out = im.crop(box)
    return _save_img(out, f"{_stem(recs[0])}_crop", _src_ext(recs[0])), f"Cropped to {out.width}×{out.height}"


@tool("img_rotate", "Image", "Rotate", "Rotate clockwise by any angle.", IMG, params=[P("angle", "Degrees", "number", "90")])
def t_irotate(recs, p):
    a = _num(p, "angle", 90); im = _load_img(recs[0]).rotate(-a, expand=True, resample=Image.BICUBIC)
    return _save_img(im, f"{_stem(recs[0])}_rot", _src_ext(recs[0])), f"Rotated {a:g}°"


@tool("img_flip", "Image", "Flip / mirror", "Mirror horizontally or vertically.", IMG,
      params=[P("direction", "Direction", "select", "horizontal", ["horizontal", "vertical"])])
def t_flip(recs, p):
    im = _load_img(recs[0])
    im = ImageOps.mirror(im) if _s(p, "direction", "horizontal") == "horizontal" else ImageOps.flip(im)
    return _save_img(im, f"{_stem(recs[0])}_flip", _src_ext(recs[0])), "Flipped"


@tool("img_convert", "Image", "Convert format", "Convert to PNG, JPG, WEBP or PDF (great for iPhone HEIC).", IMG,
      params=[P("format", "Format", "select", "png", ["png", "jpg", "webp", "pdf"])])
def t_convert(recs, p):
    fmt = _s(p, "format", "png").lower()
    if fmt == "pdf":
        src = _img_as_pdf(recs[0]["path"]); return _save_pdf(src, f"{_stem(recs[0])}.pdf"), "Converted to PDF"
    return _save_img(_load_img(recs[0]), _stem(recs[0]), fmt), f"Converted to {fmt.upper()}"


@tool("img_compress", "Image", "Compress image", "Reduce file size with adjustable quality.", IMG,
      params=[P("quality", "Quality (10-95)", "number", "70"), P("format", "Format", "select", "jpg", ["jpg", "webp"]),
              P("max_side", "Max side px (optional)", "number", "")])
def t_icompress(recs, p):
    im = _load_img(recs[0]); ms = p.get("max_side")
    if str(ms or "").strip(): im.thumbnail((int(float(ms)), int(float(ms))), Image.LANCZOS)
    rec = _save_img(im, f"{_stem(recs[0])}_small", _s(p, "format", "jpg"), int(max(10, min(95, _num(p, "quality", 70)))))
    return rec, f"{recs[0]['size']/1e6:.2f} MB → {rec['size']/1e6:.2f} MB"


@tool("img_grayscale", "Image", "Black & white", "Convert to grayscale.", IMG)
def t_gray(recs, p):
    return _save_img(ImageOps.grayscale(_load_img(recs[0])), f"{_stem(recs[0])}_bw", _src_ext(recs[0])), "Converted to grayscale"


@tool("img_enhance", "Image", "Enhance", "Adjust brightness, contrast, sharpness, saturation (1 = unchanged).", IMG,
      params=[P("brightness", "Brightness", "number", "1.05"), P("contrast", "Contrast", "number", "1.1"),
              P("sharpness", "Sharpness", "number", "1.3"), P("saturation", "Saturation", "number", "1.1")])
def t_enhance(recs, p):
    im = _load_img(recs[0])
    base = im.convert("RGBA") if "A" in im.getbands() else im.convert("RGB")
    alpha = base.getchannel("A") if base.mode == "RGBA" else None
    rgb = base.convert("RGB")
    for k, E in (("brightness", ImageEnhance.Brightness), ("contrast", ImageEnhance.Contrast),
                 ("sharpness", ImageEnhance.Sharpness), ("saturation", ImageEnhance.Color)):
        rgb = E(rgb).enhance(max(0, _num(p, k, 1)))
    if alpha: rgb.putalpha(alpha)
    return _save_img(rgb, f"{_stem(recs[0])}_enhanced", _src_ext(recs[0])), "Enhanced"


@tool("img_upscale", "Image", "Upscale", "Enlarge 2× / 3× / 4× with sharpening.", IMG,
      params=[P("scale", "Scale", "select", "2", ["2", "3", "4"])])
def t_upscale(recs, p):
    im = _load_img(recs[0]); s = int(_num(p, "scale", 2))
    out = im.resize((im.width * s, im.height * s), Image.LANCZOS).filter(ImageFilter.UnsharpMask(radius=2, percent=80, threshold=2))
    return _save_img(out, f"{_stem(recs[0])}_x{s}", _src_ext(recs[0])), f"{im.width}×{im.height} → {out.width}×{out.height}"


@tool("img_remove_bg", "Image", "Remove background", "Cut out the subject to a transparent PNG (needs: pip install rembg).", IMG)
def t_rembg(recs, p):
    try:
        from rembg import remove
    except Exception:
        raise ValueError("Background removal needs one extra package — run: !pip install -q rembg onnxruntime")
    out = remove(_load_img(recs[0]))
    return _save_img(out, f"{_stem(recs[0])}_nobg", "png"), "Background removed"


# ---------------- CREATE ----------------
PDF_CSS = """
body { font-family: sans-serif; font-size: 11pt; line-height: 1.5; color: #1f2937; }
h1 { font-size: 22pt; color: #4c1d95; margin-bottom: 4pt; }
h2 { font-size: 15pt; color: #5b21b6; margin-top: 14pt; }
h3 { font-size: 12.5pt; color: #374151; margin-top: 10pt; }
p { margin: 5pt 0; }
li { margin: 2pt 0; }
code { font-family: monospace; background-color: #f3f4f6; }
pre { font-family: monospace; font-size: 9pt; background-color: #f3f4f6; padding: 6pt; }
table { border-collapse: collapse; }
th, td { border: 1px solid #d1d5db; padding: 4pt 6pt; }
th { background-color: #ede9fe; }
blockquote { color: #4b5563; margin-left: 12pt; }
"""


def _md_to_html(md_text):
    try:
        import markdown
        return markdown.markdown(md_text, extensions=["tables", "fenced_code", "sane_lists"])
    except Exception:
        return "<pre>" + html.escape(md_text) + "</pre>"


@tool("make_pdf", "Create", "Create PDF", "Write a nicely formatted PDF from Markdown content (reports, notes, letters).",
      params=[P("title", "Title", default="Meow Report"), P("content", "Content (Markdown)", "textarea", "", hint="# Heading\nYour text…")])
def t_make_pdf(recs, p):
    title, body = _s(p, "title", "Document"), _s(p, "content")
    if not body.strip(): raise ValueError("No content given.")
    doc_html = f"<h1>{html.escape(title)}</h1>" + _md_to_html(body) if title.strip() else _md_to_html(body)
    fname = safe_name((title.strip() or "document")[:60]) + ".pdf"
    fid, path = new_path(fname)
    story = fitz.Story(html=doc_html, user_css=PDF_CSS)
    writer = fitz.DocumentWriter(path)
    mediabox = fitz.paper_rect("a4"); where = mediabox + (56, 56, -56, -56)
    more = True
    while more:
        dev = writer.begin_page(mediabox)
        more, _ = story.place(where)
        story.draw(dev)
        writer.end_page()
    writer.close()
    rec = register(fid, path, fname, "tool")
    return rec, f"{rec['meta'].get('pages', '?')} page PDF created"


@tool("make_file", "Create", "Create text file", "Save any text file — .md, .py, .csv, .html, .json, .txt …",
      params=[P("filename", "Filename", default="notes.md"), P("content", "Content", "textarea", "")])
def t_make_file(recs, p):
    name = safe_name(_s(p, "filename", "file.txt"))
    if "." not in name: name += ".txt"
    fid, path = new_path(name)
    open(path, "w", encoding="utf-8").write(_s(p, "content"))
    rec = register(fid, path, name, "tool"); rec["text"] = _s(p, "content")[:MAX_FILE_CHARS]
    return rec, f"{rec['size']:,} bytes"


def run_tool(op, file_ids, params):
    spec = TOOLS.get(op)
    if not spec: raise ValueError(f"Unknown tool '{op}'.")
    recs = [FILES[i] for i in (file_ids or []) if i in FILES]
    if spec["accepts"]:
        if not recs: raise ValueError("This tool needs a file — the file id wasn't found (was the server restarted?).")
        bad = [r["name"] for r in recs if r["kind"] not in spec["accepts"]]
        if bad: raise ValueError(f"{', '.join(bad)} can't be used with {spec['label']} (needs {'/'.join(spec['accepts'])}).")
        if not spec["multi"]: recs = recs[:1]
    rec, msg = spec["fn"](recs, params or {})
    return rec, msg

