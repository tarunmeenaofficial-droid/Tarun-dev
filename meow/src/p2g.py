
# ==========================================================
# MORE FILE TOOLS: PDF → Word, searchable scans, form filling, PDF compare, photo restore
# ==========================================================
import difflib


def _ocr_rows(img):
    """OCR lines grouped into reading-order rows (same baseline → one row), blank line between blocks."""
    boxes = sorted(ocr_boxes(img), key=lambda b: (b["bbox"][1] + b["bbox"][3]) / 2)
    rows = []
    for b in boxes:
        yc, h = (b["bbox"][1] + b["bbox"][3]) / 2, b["bbox"][3] - b["bbox"][1]
        if rows and abs(yc - rows[-1]["yc"]) < 0.55 * max(h, rows[-1]["h"]): rows[-1]["items"].append(b)
        else: rows.append({"yc": yc, "h": h, "items": [b]})
    out, prev = [], None
    for r in rows:
        if prev and r["yc"] - prev["yc"] > 2.2 * max(r["h"], prev["h"]): out.append("")
        out.append("    ".join(b["text"] for b in sorted(r["items"], key=lambda b: b["bbox"][0]))); prev = r
    return "\n".join(out)


@tool("pdf_to_word", "PDF", "PDF → Word", "Convert a PDF into an editable Word (.docx) file, keeping layout, tables and images. Scanned PDFs are OCR'd.",
      PDF, params=[P("pages", "Pages", default="all")])
def t_pdf_to_word(recs, p):
    rec = recs[0]; stem = _stem(rec)
    fid, path = new_path(f"{stem}.docx")
    with fitz.open(rec["path"]) as d:
        n = d.page_count; pages = parse_pages(p.get("pages"), n)
        scanned = sum(len(d[i].get_text("text").strip()) < 25 for i in pages) > len(pages) / 2
    if not scanned:
        try:
            try:
                from pdf2docx import Converter
            except ImportError:
                subprocess.run([_sys.executable, "-m", "pip", "install", "-q", "pdf2docx"], check=False)
                from pdf2docx import Converter
            cv = Converter(rec["path"])
            cv.convert(path, pages=pages); cv.close()
            return register(fid, path, f"{stem}.docx", "tool"), f"Converted {len(pages)} page(s) to Word with layout"
        except Exception as e:
            print("⚠️  pdf2docx:", e)
    import docx                                               # scanned (or fallback): OCR text → clean Word document
    doc = docx.Document()
    with fitz.open(rec["path"]) as d:
        for k, i in enumerate(pages):
            page = d[i]; t = page.get_text("text").strip()
            if len(t) < 25:
                pix = page.get_pixmap(dpi=200)
                t = _ocr_rows(Image.frombytes("RGB", (pix.width, pix.height), pix.samples))
            for para in re.split(r"\n\s*\n", t):
                if para.strip(): doc.add_paragraph(para.strip())
            if k < len(pages) - 1: doc.add_page_break()
    doc.save(path)
    return register(fid, path, f"{stem}.docx", "tool"), f"Converted {len(pages)} page(s) to Word" + (" (text read with OCR)" if scanned else "")


@tool("pdf_make_searchable", "PDF", "Make scan searchable", "OCR a scanned PDF and add an invisible text layer so you can search, select and copy text.",
      PDF, params=[P("pages", "Pages", default="all")])
def t_pdf_searchable(recs, p):
    d = _open_pdf(recs[0]); pages = parse_pages(p.get("pages"), d.page_count); done = words = 0
    for i in pages:
        page = d[i]
        if len(page.get_text("text").strip()) > 50: continue  # already has real text
        z = 200 / 72; pix = page.get_pixmap(matrix=fitz.Matrix(z, z))
        boxes = ocr_boxes(Image.frombytes("RGB", (pix.width, pix.height), pix.samples))
        for b in boxes:
            x0, y0, x1, y1 = [v / z for v in b["bbox"]]
            h = max(4.0, y1 - y0); txt = b["text"]
            fs = h * 0.82; w = fitz.get_text_length(txt, "helv", fs)
            if w > 0 and w > (x1 - x0) * 1.02: fs *= (x1 - x0) / w
            try:
                page.insert_text((x0, y1 - h * 0.2), txt, fontsize=max(3, fs), fontname="helv", render_mode=3)   # 3 = invisible
                words += len(txt.split())
            except Exception:
                pass
        done += 1
    rec = _save_pdf(d, f"{_stem(recs[0])}_searchable.pdf", garbage=3, deflate=True)
    return rec, (f"Added a searchable text layer to {done} page(s) (~{words} words)" if done else "This PDF already has selectable text — nothing to do")


@tool("pdf_fill_form", "PDF", "Fill PDF form", "Fill a fillable PDF form. values = JSON object {field name: value}; checkboxes take true/false. Field names are listed in the file's content.",
      PDF, params=[P("values", "Values (JSON)", "textarea", "{}"), P("flatten", "Flatten (lock) after filling", "select", "no", ["no", "yes"])])
def t_pdf_fill(recs, p):
    vals = p.get("values") or {}
    if isinstance(vals, str):
        try: vals = json.loads(vals or "{}")
        except Exception: raise ValueError("values must be a JSON object like {\"Name\": \"Tarun\"}")
    norm = lambda s: re.sub(r"[\s_:.-]+", "", str(s).lower())
    want = {norm(k): v for k, v in vals.items()}
    d = _open_pdf(recs[0]); filled, missing = [], set(want)
    for page in d:
        for w in page.widgets() or []:
            key = norm(w.field_name)
            if key not in want: continue
            v = want[key]
            if w.field_type in (fitz.PDF_WIDGET_TYPE_CHECKBOX, fitz.PDF_WIDGET_TYPE_RADIOBUTTON):
                on = v if isinstance(v, bool) else str(v).strip().lower() in ("1", "true", "yes", "on", "x", "✓", "checked")
                w.field_value = w.on_state() if on else "Off"
            else:
                w.field_value = str(v)
            w.update(); filled.append(w.field_name); missing.discard(key)
    if not filled:
        names = [w.field_name for pg in d for w in (pg.widgets() or [])]
        raise ValueError("No matching fields. This form's fields are: " + (", ".join(names[:40]) or "none (not a fillable form — use pdf_add_text instead)"))
    if _s(p, "flatten", "no") == "yes":
        try: d.bake()
        except Exception: pass
    rec = _save_pdf(d, f"{_stem(recs[0])}_filled.pdf")
    return rec, f"Filled {len(filled)} field(s)" + (f"; not found: {', '.join(sorted(missing))}" if missing else "")


def _words(doc):
    out = []
    for i, page in enumerate(doc):
        for w in page.get_text("words", sort=True):
            out.append((w[4], i, fitz.Rect(w[:4])))
    return out


@tool("pdf_compare", "PDF", "Compare two PDFs", "Find every difference between two versions of a document: side-by-side PDF with removed text in red and added text in green, plus a summary.",
      PDF, multi=True)
def t_pdf_compare(recs, p):
    if len(recs) < 2: raise ValueError("Pick two PDFs: the old version first, then the new one.")
    A, B = fitz.open(recs[0]["path"]), fitz.open(recs[1]["path"])
    wa, wb = _words(A), _words(B)
    sm = difflib.SequenceMatcher(None, [w[0].lower() for w in wa], [w[0].lower() for w in wb], autojunk=False)
    red, green, changes = [], [], []
    for op, a0, a1, b0, b1 in sm.get_opcodes():
        if op == "equal": continue
        if op in ("replace", "delete"): red += wa[a0:a1]
        if op in ("replace", "insert"): green += wb[b0:b1]
        old = " ".join(w[0] for w in wa[a0:a1]); new = " ".join(w[0] for w in wb[b0:b1])
        pg = (wb[b0][1] if b0 < len(wb) else wa[a0][1] if a0 < len(wa) else 0) + 1
        changes.append({"replace": f"p{pg}: “{old[:80]}” → “{new[:80]}”", "delete": f"p{pg}: removed “{old[:100]}”",
                        "insert": f"p{pg}: added “{new[:100]}”"}[op])
    out = fitz.open()
    gap = 24
    for i in range(max(A.page_count, B.page_count)):
        ra = A[i].rect if i < A.page_count else fitz.Rect(0, 0, 0, 0)
        rb = B[i].rect if i < B.page_count else fitz.Rect(0, 0, 0, 0)
        W, H = ra.width + gap + rb.width, max(ra.height, rb.height) + 30
        pg = out.new_page(width=W, height=H)
        pg.insert_text((10, 18), f"OLD · {recs[0]['name']} · page {i+1}", fontsize=9, color=(0.75, 0.1, 0.1))
        pg.insert_text((ra.width + gap + 10, 18), f"NEW · {recs[1]['name']} · page {i+1}", fontsize=9, color=(0.05, 0.5, 0.2))
        if i < A.page_count: pg.show_pdf_page(fitz.Rect(0, 30, ra.width, 30 + ra.height), A, i)
        if i < B.page_count: pg.show_pdf_page(fitz.Rect(ra.width + gap, 30, ra.width + gap + rb.width, 30 + rb.height), B, i)
        pg.draw_line((ra.width + gap / 2, 30), (ra.width + gap / 2, H), color=(0.6, 0.6, 0.6), width=0.6)
        for _, pi, r in red:
            if pi == i: pg.draw_rect(r + (0, 30, 0, 30), color=None, fill=(1, 0.25, 0.25), fill_opacity=0.3, overlay=True)
        for _, pi, r in green:
            if pi == i: pg.draw_rect(r + (ra.width + gap, 30, ra.width + gap, 30), color=None, fill=(0.1, 0.8, 0.3), fill_opacity=0.3, overlay=True)
    fid, path = new_path(f"compare_{_stem(recs[0])}_vs_{_stem(recs[1])}.pdf")
    out.save(path, garbage=3, deflate=True); A.close(); B.close(); out.close()
    rec = register(fid, path, os.path.basename(path).split("_", 1)[1], "tool")
    if not changes: return rec, "The two PDFs have identical text"
    sim = sm.ratio() * 100
    return rec, f"{len(changes)} change(s) · {sim:.1f}% text similarity. " + " | ".join(changes[:12]) + (" …" if len(changes) > 12 else "")


@tool("image_restore", "Image", "Restore photo", "One-click photo fix: removes noise and JPEG blockiness, fixes colour cast, recovers shadows/contrast, sharpens, and optionally AI-upscales small photos.",
      IMG, params=[P("strength", "Strength", "select", "medium", ["light", "medium", "strong"]), P("upscale", "AI upscale if small", "select", "yes", ["yes", "no"])])
def t_image_restore(recs, p):
    import numpy as np, cv2
    im = _load_img(recs[0]); alpha = im.getchannel("A") if "A" in im.getbands() else None
    rgb = np.array(im.convert("RGB"))
    st = {"light": 0.6, "medium": 1.0, "strong": 1.6}.get(_s(p, "strength", "medium"), 1.0)
    sig = _noise_sigma(rgb, np.ones(rgb.shape[:2], bool))
    h = float(np.clip(sig * 1.3 * st, 2, 14))
    bgr = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
    bgr = cv2.fastNlMeansDenoisingColored(bgr, None, h, h, 7, 21)
    lab = cv2.cvtColor(bgr, cv2.COLOR_BGR2LAB).astype(np.float32)
    for c in (1, 2):                                          # grey-world white balance (gentle)
        lab[..., c] = lab[..., c] - (lab[..., c].mean() - 128) * min(1.0, 0.7 * st)
    lo, hi = np.percentile(lab[..., 0], (0.5, 99.5))           # auto levels: real blacks and whites
    if hi - lo > 40: lab[..., 0] = lab[..., 0] * 0.4 + np.clip((lab[..., 0] - lo) * 255.0 / (hi - lo), 0, 255) * 0.6
    L = np.clip(lab[..., 0], 0, 255).astype(np.uint8)
    L = cv2.createCLAHE(clipLimit=1.4 + 0.8 * st, tileGridSize=(8, 8)).apply(L)
    lab[..., 0] = L
    out = cv2.cvtColor(np.clip(lab, 0, 255).astype(np.uint8), cv2.COLOR_LAB2RGB)
    blur = cv2.GaussianBlur(out, (0, 0), 1.2)
    out = cv2.addWeighted(out, 1 + 0.45 * st, blur, -0.45 * st, 0)
    res = Image.fromarray(out); note = f"denoised (σ≈{sig:.1f}), colour-balanced, contrast recovered, sharpened"
    if _s(p, "upscale", "yes") == "yes" and max(res.size) < 1400:
        try:
            res = ai_upscale(res, 2); note += ", AI-upscaled 2×"
            if alpha: alpha = alpha.resize(res.size, Image.LANCZOS)
        except Exception as e:
            print("⚠️  upscale:", e)
    if alpha: res.putalpha(alpha)
    return _save_img(res, f"{_stem(recs[0])}_restored", _src_ext(recs[0])), note.capitalize()
