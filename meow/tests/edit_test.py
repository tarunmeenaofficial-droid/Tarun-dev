import os, io, json
os.environ["MEOW_CAPTIONS"]="0"
exec(open("/tmp/meow_tests/harness.py").read().split("from fastapi.testclient")[0])
from fastapi.testclient import TestClient
import pymupdf
from PIL import Image, ImageDraw
c=TestClient(g["app"])
T="/tmp/meow_tests/"
# build realistic doc: logo (alpha png), photo (jpg), serif text, 2 pages, one shared logo
logo=Image.new("RGBA",(200,200),(0,0,0,0)); ImageDraw.Draw(logo).ellipse((10,10,190,190),fill=(200,30,40,255)); logo.save(T+"logo.png")
photo=Image.new("RGB",(400,300),(30,120,200)); ImageDraw.Draw(photo).rectangle((50,50,350,250),fill=(250,200,40)); photo.save(T+"photo.jpg")
d=pymupdf.open()
for i in range(2):
    p=d.new_page()
    p.insert_image(pymupdf.Rect(40,30,100,90), filename=T+"logo.png")
    p.insert_text((120,70),"CHANDIGARH UNIVERSITY",fontname="tibo",fontsize=16,color=(0.6,0.1,0.1))
    p.insert_text((60,130),"Student Name:",fontname="tibo",fontsize=12); p.insert_text((150,130),"Rahul Sharma",fontname="tiro",fontsize=12)
    p.insert_text((60,150),"Aim - To solve ranking problems.",fontname="tiro",fontsize=12)
d[0].insert_image(pymupdf.Rect(300,200,500,350), filename=T+"photo.jpg")
d.save(T+"doc.pdf")
up=c.post("/api/upload",files=[("files",("doc.pdf",open(T+"doc.pdf","rb"))),("files",("new.jpg",open(T+"photo.jpg","rb"))),("files",("logo2.png",open(T+"logo.png","rb")))]).json()["files"]
pdf, img, img2 = up[0], up[1], up[2]
print("context images line:", [l for l in g["FILES"][pdf["id"]]["text"].splitlines() if "images" in l])
o=c.post("/api/pdf/open",json={"file_id":pdf["id"]}).json(); dr=o["draft"]["id"]; print("open", o["pages"], o["draft"]["name"])
lay=c.get(f"/api/pdf/{dr}/layout/0").json()
print("runs:", [(r["text"],r["family"],r["bold"],r["size"]) for r in lay["runs"]])
print("images:", lay["images"])
print("render", c.get(f"/api/pdf/{dr}/render/0?scale=1.2").status_code)
name_run=[r for r in lay["runs"] if r["text"]=="Rahul Sharma"][0]
photo_im=[m for m in lay["images"] if m["bbox"][0]>250][0]; logo_im=[m for m in lay["images"] if m["bbox"][0]<120][0]
def ed(ops):
    global dr
    j=c.post(f"/api/pdf/{dr}/edit",json={"ops":ops}).json()
    if not j["ok"]: print("  ERR", ops[0]["op"], j["error"]); return
    dr=j["draft"]["id"]; print("  ok", ops[0]["op"], len(j["pages"]),"pages")
ed([{"op":"edit_text","page":0,"bbox":name_run["bbox"],"text":"Tarun Meena"}])
ed([{"op":"add_text","page":0,"x":60,"y":180,"text":"Hello ₹500 नमस्ते","size":12,"color":"#1d4ed8","family":"serif"}])
ed([{"op":"add_text","page":0,"x":60,"y":200,"text":"Bold italic note","size":11,"color":"#000000","family":"sans","bold":True,"italic":True}])
ed([{"op":"image_filter","page":0,"xref":photo_im["xref"],"bbox":photo_im["bbox"],"action":"grayscale"}])
lay=c.get(f"/api/pdf/{dr}/layout/0").json(); photo_im=[m for m in lay["images"] if m["bbox"][0]>250][0]
ed([{"op":"move_image","page":0,"xref":photo_im["xref"],"bbox":photo_im["bbox"],"rect":[320,420,520,570]}])
lay=c.get(f"/api/pdf/{dr}/layout/0").json(); logo_im=[m for m in lay["images"] if m["bbox"][0]<120][0]
ed([{"op":"replace_image","page":0,"xref":logo_im["xref"],"bbox":logo_im["bbox"],"file_id":img["id"]}])
ed([{"op":"ink","page":0,"points":[[60,700],[100,680],[140,720],[180,690]],"color":"#dc2626","width":2}])
ed([{"op":"shape","page":0,"kind":"rect","rect":[50,120,300,140],"color":"#16a34a","width":1.5}])
ed([{"op":"shape","page":0,"kind":"ellipse","rect":[400,700,500,760],"color":"#9333ea","width":2,"fill":"#e9d5ff"}])
ed([{"op":"highlight","page":0,"rect":[55,140,300,155]}])
ed([{"op":"erase","page":1,"rect":[55,140,300,155]}])
ed([{"op":"add_image","page":1,"file_id":img2["id"],"rect":[400,40,460,100]}])
ed([{"op":"page_insert","after":1}])
ed([{"op":"page_duplicate","page":0}])
ed([{"op":"page_move","page":0,"to":3}])
ed([{"op":"page_rotate","page":2,"angle":90}])
ed([{"op":"page_delete","page":1}])
d2=g["FILES"][dr]
doc=pymupdf.open(d2["path"]); print("final pages", doc.page_count)
for i,pg in enumerate(doc): pg.get_pixmap(dpi=60).save(T+f"ed_p{i}.png")
# page 1 (orig page 1?) check logo on 2nd original page still exists after replacing shared logo on page 0
sv=c.post(f"/api/pdf/{dr}/save",json={"name":"doc_edited.pdf"}).json(); print("save", sv["ok"], sv["file"]["name"], sv["file"]["meta"])
print("img endpoint", c.get(f"/api/pdf/{dr}/image/{lay['images'][0]['xref']}").status_code)
# AI tools
for op,files,p in [("pdf_replace_image",[pdf["id"],img["id"]],{"page":"1","image":"2"}),("pdf_edit_image",[pdf["id"]],{"page":"1","image":"1","action":"sepia"}),
                   ("pdf_delete_image",[pdf["id"]],{"page":"2","image":"1"}),("pdf_add_image",[pdf["id"],img2["id"]],{"page":"1","position":"bottom-right","width":"80"}),
                   ("pdf_erase_area",[pdf["id"]],{"page":"1","x0":"55","y0":"140","x1":"300","y1":"155"}),("pdf_replace_text",[pdf["id"]],{"find":"Rahul Sharma","replace":"Tarun Meena"})]:
    j=c.post("/api/tool",json={"op":op,"files":files,"params":p}).json(); print("AI", op, j["ok"], j.get("message") or j.get("error"))
print("files listing hides drafts:", all(f["origin"]!="draft" for f in c.get("/api/files").json()["files"]))
