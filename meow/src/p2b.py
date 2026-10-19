
# ==========================================================
# PRO PDF EDITING ENGINE (visual editor + AI tools)
# ==========================================================
FAM_CSS = {"serif": "serif", "mono": "monospace", "sans": "sans-serif"}


def _latin1(t):
    try:
        t.encode("latin-1"); return True
    except UnicodeEncodeError:
        return False


def _hex(c):
    if isinstance(c, int):
        return f"#{c >> 16 & 255:02x}{c >> 8 & 255:02x}{c & 255:02x}"
    return "#%02x%02x%02x" % tuple(int(max(0, min(1, v)) * 255) for v in c[:3])


def _family_of(font, flags):
    f = (font or "").lower()
    if (flags & 8) or any(k in f for k in ("courier", "mono", "consol")): return "mono"
    if "sans" in f or "arial" in f or "helvet" in f or "calibri" in f or "verdana" in f: return "sans"
    if (flags & 4) or any(k in f for k in ("times", "serif", "roman", "georgia", "garamond", "cambria", "book", "minion")): return "serif"
    return "sans"


def _style_of(sp):
    font, flags = sp.get("font", ""), sp.get("flags", 0)
    lf = font.lower()
    return dict(font=font, size=sp.get("size", 11), color=_hex(sp.get("color", 0)), family=_family_of(font, flags),
                bold=bool(flags & 16) or any(k in lf for k in ("bold", "black", "heavy", "semibold")),
                italic=bool(flags & 2) or "italic" in lf or "oblique" in lf)


def _b14(family, bold, italic):
    t = {"mono": ("cour", "cobo", "coit", "cobi"), "serif": ("tiro", "tibo", "tiit", "tibi"),
         "sans": ("helv", "hebo", "heit", "hebi")}[family if family in ("mono", "serif") else "sans"]
    return t[(1 if bold else 0) + (2 if italic else 0)]


def write_run(doc, page, origin, text, style, cache, keep_font=True):
    """Write text at a baseline origin in the given style. Reuses the PDF's own
    embedded font when possible; falls back to standard fonts, and to HTML
    rendering (full Unicode: Hindi, ₹, emoji-free scripts) when needed."""
    size = float(style.get("size") or 11)
    color = _rgb(style.get("color"), (0, 0, 0))
    lines = str(text).split("\n")
    lh = size * 1.2
    if all(_latin1(l) for l in lines):
        emb = _embedded_font(doc, page, style.get("font"), text, cache) if keep_font and style.get("font") else None
        if emb:
            page.insert_font(fontname=emb[0], fontbuffer=emb[1]); fname = emb[0]
        else:
            fname = _b14(style.get("family"), style.get("bold"), style.get("italic"))
        for i, l in enumerate(lines):
            if l:
                page.insert_text(fitz.Point(origin.x, origin.y + i * lh), l, fontname=fname, fontsize=size, color=color)
        return
    css = (f"* {{font-family: {FAM_CSS.get(style.get('family'), 'sans-serif')}; font-size: {size}px; line-height: 1.2;"
           f" color: {style.get('color') or '#000'}; font-weight: {'bold' if style.get('bold') else 'normal'};"
           f" font-style: {'italic' if style.get('italic') else 'normal'}; margin: 0; padding: 0; }}")
    top = origin.y - size * 0.95
    rect = fitz.Rect(origin.x, top, max(origin.x + 40, page.rect.x1 - 8), top + lh * len(lines) + size)
    page.insert_htmlbox(rect, html.escape(str(text)).replace("\n", "<br>"), css=css)


def _redact_kw(images="none", graphics="none", text=True):
    kw = {"images": {"none": getattr(fitz, "PDF_REDACT_IMAGE_NONE", 0), "pixels": getattr(fitz, "PDF_REDACT_IMAGE_PIXELS", 2),
                     "remove": getattr(fitz, "PDF_REDACT_IMAGE_REMOVE", 1)}[images]}
    if hasattr(fitz, "PDF_REDACT_LINE_ART_NONE"):
        kw["graphics"] = {"none": fitz.PDF_REDACT_LINE_ART_NONE,
                          "covered": getattr(fitz, "PDF_REDACT_LINE_ART_REMOVE_IF_COVERED", 1)}[graphics]
    if not text and hasattr(fitz, "PDF_REDACT_TEXT_NONE"):
        kw["text"] = fitz.PDF_REDACT_TEXT_NONE
    return kw


def _apply_redactions(page, **kw):
    for drop in (None, "text", "graphics"):
        if drop: kw.pop(drop, None)
        try:
            return page.apply_redactions(**kw)
        except TypeError:
            continue
    page.apply_redactions()


def page_layout(page):
    """Editable text runs (merged spans of identical style) + placed images."""
    runs = []
    try:
        flags = fitz.TEXTFLAGS_DICT & ~fitz.TEXT_PRESERVE_IMAGES
    except Exception:
        flags = 0
    data = page.get_text("dict", flags=flags) if flags else page.get_text("dict")
    for b in data["blocks"]:
        if b.get("type") != 0: continue
        for l in b["lines"]:
            d = l.get("dir", (1, 0))
            if abs(d[0] - 1) > 0.01 or abs(d[1]) > 0.01: continue        # skip rotated text
            cur = None
            for sp in l["spans"]:
                t = sp["text"]
                st = _style_of(sp)
                key = (sp["font"], round(sp["size"], 1), sp["color"], st["bold"], st["italic"])
                if not t.strip():
                    if cur: cur["text"] += t
                    continue
                if cur and cur["key"] == key and abs(sp["origin"][1] - cur["origin"][1]) < 1 and sp["bbox"][0] - cur["bbox"][2] < sp["size"] * 0.9:
                    if sp["bbox"][0] - cur["bbox"][2] > sp["size"] * 0.15 and not cur["text"].endswith(" "): cur["text"] += " "
                    cur["text"] += t
                    cur["bbox"] = [min(cur["bbox"][0], sp["bbox"][0]), min(cur["bbox"][1], sp["bbox"][1]),
                                   max(cur["bbox"][2], sp["bbox"][2]), max(cur["bbox"][3], sp["bbox"][3])]
                else:
                    if cur: runs.append(cur)
                    cur = dict(key=key, text=t, bbox=list(sp["bbox"]), origin=list(sp["origin"]), **st)
            if cur: runs.append(cur)
    out = []
    for i, r in enumerate(runs):
        r.pop("key"); r["text"] = r["text"].rstrip()
        if r["text"]:
            r["id"] = i; r["bbox"] = [round(v, 2) for v in r["bbox"]]; out.append(r)
    imgs = []
    pr = page.rect
    for info in page.get_image_info(xrefs=True):
        bb = fitz.Rect(info["bbox"]) & pr
        if bb.is_empty or bb.width < 4 or bb.height < 4 or (info.get("width") or 9) <= 2: continue
        imgs.append(dict(xref=info.get("xref", 0), bbox=[round(v, 2) for v in bb], w=info.get("width"), h=info.get("height")))
    imgs.sort(key=lambda m: (round(m["bbox"][1] / 10), m["bbox"][0]))
    for i, m in enumerate(imgs, 1): m["index"] = i
    return {"runs": out, "images": imgs, "w": pr.width, "h": pr.height}


def _xref_uses(doc, xref):
    return sum(1 for pg in doc for i in pg.get_image_info(xrefs=True) if i.get("xref") == xref)


def _image_pil(doc, xref):
    base = fitz.Pixmap(doc, xref)
    if base.n - base.alpha >= 4:
        base = fitz.Pixmap(fitz.csRGB, base)
    try:
        smask = doc.extract_image(xref).get("smask", 0)
        if smask:
            base = fitz.Pixmap(base, fitz.Pixmap(doc, smask))
    except Exception:
        pass
    im = Image.open(io.BytesIO(base.tobytes("png"))); im.load()
    return im


def _remove_image(doc, page, xref, bbox):
    if xref and _xref_uses(doc, xref) == 1 and hasattr(page, "delete_image"):
        page.delete_image(xref)
    else:
        page.add_redact_annot(fitz.Rect(bbox), fill=False)
        _apply_redactions(page, **_redact_kw(images="pixels", text=False))


def _insert_pil(page, rect, im, keep=True):
    buf = io.BytesIO()
    if "A" in im.getbands() or im.mode == "P":
        im.convert("RGBA").save(buf, "PNG", optimize=True)
    else:
        im.convert("RGB").save(buf, "JPEG", quality=92)
    page.insert_image(fitz.Rect(rect), stream=buf.getvalue(), keep_proportion=keep, overlay=True)


IMG_ACTIONS = ["grayscale", "brighter", "darker", "contrast", "sharpen", "blur", "rotate", "flip_h", "flip_v",
               "invert", "auto_enhance", "sepia", "remove_bg"]


def filter_image(im, action, amount=None):
    a = action
    rgba = im.convert("RGBA"); alpha = rgba.getchannel("A"); rgb = rgba.convert("RGB")
    amt = float(amount) if amount not in (None, "") else None
    if a == "grayscale": rgb = ImageOps.grayscale(rgb).convert("RGB")
    elif a == "brighter": rgb = ImageEnhance.Brightness(rgb).enhance(amt or 1.2)
    elif a == "darker": rgb = ImageEnhance.Brightness(rgb).enhance(amt or 0.8)
    elif a == "contrast": rgb = ImageEnhance.Contrast(rgb).enhance(amt or 1.25)
    elif a == "sharpen": rgb = rgb.filter(ImageFilter.UnsharpMask(radius=2, percent=int((amt or 1.5) * 100), threshold=2))
    elif a == "blur": rgb = rgb.filter(ImageFilter.GaussianBlur(amt or 2))
    elif a == "invert": rgb = ImageOps.invert(rgb)
    elif a == "auto_enhance":
        rgb = ImageOps.autocontrast(rgb, cutoff=1); rgb = ImageEnhance.Color(rgb).enhance(1.1)
        rgb = rgb.filter(ImageFilter.UnsharpMask(radius=1.5, percent=60, threshold=2))
    elif a == "sepia":
        g = ImageOps.grayscale(rgb); rgb = ImageOps.colorize(g, "#2e1f0f", "#f3e3c3")
    elif a == "remove_bg":
        try:
            from rembg import remove
        except Exception:
            raise ValueError("Remove background needs: !pip install -q rembg onnxruntime")
        return remove(im.convert("RGBA"))
    elif a in ("rotate", "flip_h", "flip_v"):
        rgba = Image.merge("RGBA", (*rgb.split(), alpha))
        if a == "rotate": rgba = rgba.rotate(-(amt or 90), expand=True)
        elif a == "flip_h": rgba = ImageOps.mirror(rgba)
        else: rgba = ImageOps.flip(rgba)
        return rgba
    else:
        raise ValueError(f"Unknown image action '{a}'. Try: {', '.join(IMG_ACTIONS)}")
    rgb.putalpha(alpha)
    return rgb


def _rect_of(v):
    r = fitz.Rect(*[float(x) for x in v])
    r.normalize()
    return r


def _resolve_image(page, xref, bbox):
    """Find the image actually placed at bbox (xrefs can change between saves)."""
    best, score = None, 0
    for info in page.get_image_info(xrefs=True):
        r = fitz.Rect(info["bbox"]); ov = r & bbox
        if ov.is_empty: continue
        sc = ov.get_area() / max(1e-6, (r | bbox).get_area()) + (0.5 if info.get("xref") == xref else 0)
        if sc > score: best, score = info, sc
    if not best: raise ValueError("Couldn't find that image on the page any more — reload and try again.")
    return best.get("xref", 0), fitz.Rect(best["bbox"]) & page.rect


def apply_ops(doc, ops):
    """Run editor operations on an open document. Each op is a dict with 'op'."""
    cache = {}
    notes = []
    for o in ops:
        kind = o.get("op")
        pno = int(o.get("page", 0))
        if kind not in ("page_insert",) and not 0 <= pno < doc.page_count:
            raise ValueError(f"Page {pno + 1} doesn't exist.")
        page = doc[pno] if 0 <= pno < doc.page_count else None

        if kind == "edit_text":
            bbox = _rect_of(o["bbox"])
            sp = _span_style(page, bbox) or {}
            base = _style_of(sp) if sp else dict(font=None, size=bbox.height * 0.8, color="#000000", family="sans", bold=False, italic=False)
            style = {**base, **{k: o[k] for k in ("size", "color", "family", "bold", "italic") if o.get(k) not in (None, "")}}
            keep = all(style.get(k) == base.get(k) for k in ("family", "bold", "italic"))
            origin = fitz.Point(sp["origin"][0], sp["origin"][1]) if sp.get("origin") else fitz.Point(bbox.x0, bbox.y1 - style["size"] * 0.22)
            if sp.get("bbox"): origin.x = min(origin.x, bbox.x0 + 0.5)
            page.add_redact_annot(bbox + (0.3, 0.3, -0.3, -0.3), fill=False)
            _apply_redactions(page, **_redact_kw())
            if str(o.get("text", "")).strip():
                write_run(doc, page, origin, o["text"], style, cache, keep_font=keep)

        elif kind == "scan_text":
            notes.append(scan_text_op(doc, page, o))

        elif kind == "magic_erase":
            notes.append(magic_erase_op(doc, page, o))

        elif kind == "delete_text":
            page.add_redact_annot(_rect_of(o["bbox"]) + (0.3, 0.3, -0.3, -0.3), fill=False)
            _apply_redactions(page, **_redact_kw())

        elif kind == "add_text":
            size = float(o.get("size") or 12)
            style = dict(size=size, color=o.get("color") or "#000000", family=o.get("family") or "sans",
                         bold=bool(o.get("bold")), italic=bool(o.get("italic")))
            write_run(doc, page, fitz.Point(float(o["x"]), float(o["y"])), o.get("text", ""), style, cache, keep_font=False)

        elif kind in ("move_image", "replace_image", "image_filter", "delete_image"):
            xref, bbox = _resolve_image(page, int(o.get("xref") or 0), _rect_of(o["bbox"]))
            if kind == "replace_image":
                rec = FILES.get(o.get("file_id"))
                if not rec or rec["kind"] != "image": raise ValueError("Pick an image file to replace with.")
                new = ImageOps.exif_transpose(Image.open(rec["path"])); new.load()
                _remove_image(doc, page, xref, bbox)
                _insert_pil(page, bbox, new, keep=o.get("fit", "contain") != "stretch")
                continue
            if kind == "delete_image":
                _remove_image(doc, page, xref, bbox); continue
            if not xref:
                pix = page.get_pixmap(clip=bbox, dpi=200)
                im = Image.open(io.BytesIO(pix.tobytes("png"))); im.load()
            else:
                im = _image_pil(doc, xref)
            if kind == "image_filter":
                im = filter_image(im, o.get("action"), o.get("amount"))
                target = bbox
                keep = o.get("action") in ("rotate",)
            else:
                target, keep = _rect_of(o["rect"]), False
            if xref:
                _remove_image(doc, page, xref, bbox)
            else:
                page.add_redact_annot(bbox, fill=(1, 1, 1)); _apply_redactions(page, **_redact_kw(images="pixels", text=False))
            _insert_pil(page, target, im, keep=keep)

        elif kind == "add_image":
            rec = FILES.get(o.get("file_id"))
            if not rec or rec["kind"] != "image": raise ValueError("Image file not found.")
            im = ImageOps.exif_transpose(Image.open(rec["path"])); im.load()
            if o.get("rect"):
                r = _rect_of(o["rect"])
            else:
                pr = page.rect; w = float(o.get("width") or pr.width * 0.4); h = w * im.height / max(1, im.width)
                r = fitz.Rect((pr.width - w) / 2, (pr.height - h) / 2, (pr.width + w) / 2, (pr.height + h) / 2)
            _insert_pil(page, r, im, keep=True)

        elif kind == "ink":
            pts = [fitz.Point(float(x), float(y)) for x, y in o.get("points", [])]
            if len(pts) < 2: continue
            sh = page.new_shape()
            sh.draw_polyline(pts)
            sh.finish(color=_rgb(o.get("color"), (0, 0, 0)), width=float(o.get("width") or 2), closePath=False,
                      lineCap=1, lineJoin=1, stroke_opacity=float(o.get("opacity") or 1))
            sh.commit()

        elif kind == "shape":
            r = _rect_of(o["rect"]); sh = page.new_shape(); k = o.get("kind", "rect")
            if k == "ellipse": sh.draw_oval(r)
            elif k == "line": sh.draw_line(fitz.Point(*o["rect"][:2]), fitz.Point(*o["rect"][2:]))
            else: sh.draw_rect(r)
            fill = _rgb(o.get("fill")) if o.get("fill") else None
            sh.finish(color=_rgb(o.get("color"), (0, 0, 0)), fill=fill, width=float(o.get("width") or 1.5),
                      fill_opacity=float(o.get("fill_opacity") or 1), stroke_opacity=float(o.get("opacity") or 1))
            sh.commit()

        elif kind == "highlight":
            r = _rect_of(o["rect"])
            words = []
            for w in page.get_text("words"):
                wr = fitz.Rect(w[:4]); c = fitz.Point((wr.x0 + wr.x1) / 2, (wr.y0 + wr.y1) / 2)
                if r.contains(c): words.append(wr)
            if words:
                a = page.add_highlight_annot(words)
                a.set_colors(stroke=_rgb(o.get("color"), (1, 0.85, 0.1))); a.update()
            else:
                sh = page.new_shape(); sh.draw_rect(r)
                sh.finish(color=None, fill=_rgb(o.get("color"), (1, 0.85, 0.1)), fill_opacity=0.35); sh.commit()

        elif kind == "erase":
            r = _rect_of(o["rect"])
            page.add_redact_annot(r, fill=_rgb(o.get("fill"), (1, 1, 1)) if o.get("fill") else (1, 1, 1))
            _apply_redactions(page, **_redact_kw(images="pixels", graphics="covered"))

        elif kind == "page_rotate":
            page.set_rotation((page.rotation + int(o.get("angle") or 90)) % 360)
            try: page.remove_rotation()
            except Exception: pass
        elif kind == "page_delete":
            if doc.page_count <= 1: raise ValueError("A PDF needs at least one page.")
            doc.delete_page(pno)
        elif kind == "page_insert":
            after = int(o.get("after", doc.page_count - 1))
            ref = doc[max(0, min(after, doc.page_count - 1))].rect
            doc.new_page(after + 1, width=ref.width, height=ref.height)
        elif kind == "page_duplicate":
            doc.fullcopy_page(pno, pno + 1) if hasattr(doc, "fullcopy_page") else doc.copy_page(pno, pno + 1)
        elif kind == "page_move":
            to = int(o.get("to", pno))
            if 0 <= to < doc.page_count and to != pno:
                doc.move_page(pno, to if to < pno else (to + 1 if to + 1 < doc.page_count else -1))
        else:
            raise ValueError(f"Unknown edit '{kind}'.")
    return notes


def open_draft(rec):
    """Copy a PDF (or wrap an image as a 1-page PDF) into an editable draft."""
    if rec["kind"] == "image":
        im = _load_img(rec); k = 0.75 if max(im.size) <= 4000 else 3000 / max(im.size)
        d = fitz.open(); pg = d.new_page(width=im.width * k, height=im.height * k)
        _insert_pil(pg, pg.rect, im, keep=False)
        name = f"{_stem(rec)}_edited.pdf"; fid, path = new_path(name)
        d.save(path, garbage=3, deflate=True); d.close()
        r = register(fid, path, name, origin="draft")
        r["meta"].update(source=rec["id"], image_px=[im.width, im.height])
        return r
    d = _open_pdf(rec)
    for pg in d:
        if pg.rotation:
            try: pg.remove_rotation()
            except Exception: pass
    name = f"{_stem(rec)}_edited.pdf" if not rec["name"].endswith("_edited.pdf") else rec["name"]
    fid, path = new_path(name)
    d.save(path, garbage=3, deflate=True); d.close()
    r = register(fid, path, name, origin="draft")
    r["meta"]["source"] = rec["id"]
    return r


def edit_draft(rec, ops):
    d = fitz.open(rec["path"])
    apply_ops(d, ops)
    fid, path = new_path(rec["name"])
    d.save(path, garbage=3, deflate=True); d.close()
    r = register(fid, path, rec["name"], origin="draft")
    r["meta"]["source"] = rec["meta"].get("source")
    if rec["meta"].get("image_px"): r["meta"]["image_px"] = rec["meta"]["image_px"]
    return r


def pages_info(rec):
    with fitz.open(rec["path"]) as d:
        return [{"w": round(p.rect.width, 2), "h": round(p.rect.height, 2)} for p in d]


# ---------- AI chat tools that edit images inside PDFs ----------
def _pdf_and_img(recs):
    pdf = next((r for r in recs if r["kind"] == "pdf"), None)
    img = next((r for r in recs if r["kind"] == "image"), None)
    if not pdf: raise ValueError("Include the PDF's file id.")
    return pdf, img


def _pick_image(doc, p):
    pno = int(_num(p, "page", 1)) - 1
    if not 0 <= pno < doc.page_count: raise ValueError(f"Page must be 1–{doc.page_count}.")
    imgs = page_layout(doc[pno])["images"]
    if not imgs: raise ValueError(f"No images found on page {pno + 1}.")
    idx = int(_num(p, "image", 1))
    if not 1 <= idx <= len(imgs): raise ValueError(f"Page {pno + 1} has {len(imgs)} image(s); pick 1–{len(imgs)}.")
    return pno, imgs[idx - 1]


def _run_pdf_ops(pdf, ops, suffix):
    d = _open_pdf(pdf)
    apply_ops(d, ops)
    return _save_pdf(d, f"{_stem(pdf)}_{suffix}.pdf")


@tool("pdf_replace_image", "PDF", "Replace image in PDF", "Swap an image inside a PDF for another image, in the same spot (images are numbered per page, top to bottom).",
      ["pdf", "image"], multi=True,
      params=[P("page", "Page", "number", "1"), P("image", "Image # on page", "number", "1"), P("fit", "Fit", "select", "contain", ["contain", "stretch"])])
def t_pdf_replace_image(recs, p):
    pdf, img = _pdf_and_img(recs)
    if not img: raise ValueError("Also include the new image's file id.")
    with fitz.open(pdf["path"]) as d: pno, m = _pick_image(d, p)
    rec = _run_pdf_ops(pdf, [dict(op="replace_image", page=pno, xref=m["xref"], bbox=m["bbox"], file_id=img["id"], fit=_s(p, "fit", "contain"))], "image_replaced")
    return rec, f"Replaced image {m['index']} on page {pno + 1}"


@tool("pdf_edit_image", "PDF", "Edit image in PDF", "Apply an effect to an image inside a PDF: " + ", ".join(IMG_ACTIONS) + ".", PDF,
      params=[P("page", "Page", "number", "1"), P("image", "Image # on page", "number", "1"),
              P("action", "Effect", "select", "auto_enhance", IMG_ACTIONS), P("amount", "Amount (optional)", "number", "")])
def t_pdf_edit_image(recs, p):
    pdf = recs[0]
    with fitz.open(pdf["path"]) as d: pno, m = _pick_image(d, p)
    act = _s(p, "action", "auto_enhance")
    rec = _run_pdf_ops(pdf, [dict(op="image_filter", page=pno, xref=m["xref"], bbox=m["bbox"], action=act, amount=p.get("amount"))], "image_edited")
    return rec, f"{act.replace('_', ' ').title()} → image {m['index']}, page {pno + 1}"


@tool("pdf_delete_image", "PDF", "Delete image in PDF", "Remove an image from a PDF page.", PDF,
      params=[P("page", "Page", "number", "1"), P("image", "Image # on page", "number", "1")])
def t_pdf_delete_image(recs, p):
    pdf = recs[0]
    with fitz.open(pdf["path"]) as d: pno, m = _pick_image(d, p)
    rec = _run_pdf_ops(pdf, [dict(op="delete_image", page=pno, xref=m["xref"], bbox=m["bbox"])], "image_removed")
    return rec, f"Removed image {m['index']} from page {pno + 1}"


@tool("pdf_add_image", "PDF", "Add image to PDF", "Place an image (logo, photo, signature) on a PDF page.", ["pdf", "image"], multi=True,
      params=[P("page", "Page", "number", "1"),
              P("position", "Position", "select", "bottom-right", ["top-left", "top-center", "top-right", "center", "bottom-left", "bottom-center", "bottom-right"]),
              P("width", "Width (pt)", "number", "120"), P("margin", "Margin (pt)", "number", "36")])
def t_pdf_add_image(recs, p):
    pdf, img = _pdf_and_img(recs)
    if not img: raise ValueError("Also include the image's file id.")
    with Image.open(img["path"]) as im: ar = im.height / max(1, im.width)
    with fitz.open(pdf["path"]) as d:
        pno = int(_num(p, "page", 1)) - 1
        if not 0 <= pno < d.page_count: raise ValueError(f"Page must be 1–{d.page_count}.")
        pr = d[pno].rect
    w = _num(p, "width", 120); h = w * ar; m = _num(p, "margin", 36); pos = _s(p, "position", "bottom-right")
    x = m if "left" in pos else (pr.width - w - m if "right" in pos else (pr.width - w) / 2)
    y = m if pos.startswith("top") else (pr.height - h - m if pos.startswith("bottom") else (pr.height - h) / 2)
    rec = _run_pdf_ops(pdf, [dict(op="add_image", page=pno, file_id=img["id"], rect=[x, y, x + w, y + h])], "image_added")
    return rec, f"Added {img['name']} on page {pno + 1} ({pos})"


@tool("pdf_erase_area", "PDF", "Erase area", "White-out and permanently remove everything inside a box on a page (points from top-left).", PDF,
      params=[P("page", "Page", "number", "1"), P("x0", "Left", "number", "0"), P("y0", "Top", "number", "0"),
              P("x1", "Right", "number", "100"), P("y1", "Bottom", "number", "100")])
def t_pdf_erase(recs, p):
    pno = int(_num(p, "page", 1)) - 1
    rect = [_num(p, "x0", 0), _num(p, "y0", 0), _num(p, "x1", 100), _num(p, "y1", 100)]
    rec = _run_pdf_ops(recs[0], [dict(op="erase", page=pno, rect=rect)], "erased")
    return rec, f"Erased area on page {pno + 1}"
