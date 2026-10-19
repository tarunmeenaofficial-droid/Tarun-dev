
# ==========================================================
# VISUAL PDF EDITOR API
# ==========================================================
class EditReq(BaseModel):
    ops: list = []


class SaveReq(BaseModel):
    name: str = ""


def _need_pdf(fid, allow_image=False):
    rec = FILES.get(fid)
    if not rec or rec["kind"] not in (("pdf", "image") if allow_image else ("pdf",)) or not os.path.exists(rec["path"]):
        raise HTTPException(404, "PDF not found (server may have restarted)")
    return rec


@app.post("/api/pdf/open")
async def pdf_open(d: dict):
    rec = _need_pdf(d.get("file_id", ""), allow_image=True)
    try:
        dr = await run_in_threadpool(open_draft, rec)
    except Exception as e:
        raise HTTPException(400, str(e))
    return {"draft": public(dr), "pages": await run_in_threadpool(pages_info, dr), "source": public(rec)}


@app.get("/api/pdf/{fid}/render/{n}")
def pdf_render(fid: str, n: int, scale: float = 1.5):
    rec = _need_pdf(fid)
    scale = max(0.1, min(float(scale), 5.0))
    tp = os.path.join(WORK_DIR, f".r_{fid}_{n}_{scale:.2f}.png")
    if not os.path.exists(tp):
        with fitz.open(rec["path"]) as d:
            if not 0 <= n < d.page_count: raise HTTPException(404)
            d[n].get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=False, annots=True).save(tp)
    return FileResponse(tp, media_type="image/png", headers={"Cache-Control": "public, max-age=86400"})


@app.get("/api/pdf/{fid}/layout/{n}")
def pdf_layout(fid: str, n: int):
    rec = _need_pdf(fid)
    with fitz.open(rec["path"]) as d:
        if not 0 <= n < d.page_count: raise HTTPException(404)
        return page_layout(d[n])


@app.get("/api/pdf/{fid}/image/{xref}")
def pdf_image(fid: str, xref: int):
    rec = _need_pdf(fid)
    with fitz.open(rec["path"]) as d:
        try:
            im = _image_pil(d, xref)
        except Exception:
            raise HTTPException(404)
    buf = io.BytesIO(); im.save(buf, "PNG")
    tp = os.path.join(WORK_DIR, f".img_{fid}_{xref}.png"); open(tp, "wb").write(buf.getvalue())
    return FileResponse(tp, media_type="image/png", filename=f"image_{xref}.png")


@app.post("/api/pdf/{fid}/edit")
async def pdf_edit(fid: str, req: EditReq):
    rec = _need_pdf(fid)
    try:
        dr = await run_in_threadpool(edit_draft, rec, req.ops)
    except Exception as e:
        return {"ok": False, "error": str(e)}
    return {"ok": True, "draft": public(dr), "pages": await run_in_threadpool(pages_info, dr)}


@app.post("/api/pdf/{fid}/save")
def pdf_save(fid: str, req: SaveReq):
    rec = _need_pdf(fid)
    name = safe_name(req.name or rec["name"])
    if not name.lower().endswith(".pdf"): name += ".pdf"
    nid, path = new_path(name)
    with fitz.open(rec["path"]) as d:
        d.save(path, garbage=4, deflate=True, clean=True)
    out = register(nid, path, name, origin="tool")
    extract(out)
    return {"ok": True, "file": public(out)}


@app.get("/api/pdf/{fid}/ocr/{n}")
async def pdf_ocr(fid: str, n: int, x0: float = None, y0: float = None, x1: float = None, y1: float = None):
    rec = _need_pdf(fid)
    def run():
        with fitz.open(rec["path"]) as d:
            if not 0 <= n < d.page_count: raise HTTPException(404)
            return pdf_ocr_layout(d, n, [x0, y0, x1, y1] if x0 is not None else None)
    try:
        return await run_in_threadpool(run)
    except HTTPException:
        raise
    except Exception as e:
        return {"boxes": [], "image": None, "error": str(e)}


@app.post("/api/pdf/{fid}/save_image")
def pdf_save_image(fid: str, req: SaveReq):
    """Export the edited page back to an image at the original resolution."""
    rec = _need_pdf(fid)
    name = safe_name(req.name or rec["name"])
    ext = os.path.splitext(name)[1].lower().lstrip(".") or "png"
    if ext not in ("png", "jpg", "jpeg", "webp"): ext = "png"; name = os.path.splitext(name)[0] + ".png"
    with fitz.open(rec["path"]) as d:
        pg = d[0]; px = rec["meta"].get("image_px") or [int(pg.rect.width / 0.75), int(pg.rect.height / 0.75)]
        z = px[0] / pg.rect.width
        pix = pg.get_pixmap(matrix=fitz.Matrix(z, z), alpha=False)
        im = Image.open(io.BytesIO(pix.tobytes("png"))); im.load()
    out = _save_img(im, os.path.splitext(name)[0], ext, 95)
    return {"ok": True, "file": public(out)}
