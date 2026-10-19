import os, io, time
os.environ["MEOW_CAPTIONS"]="0"
exec(open("/tmp/meow_tests/harness.py").read().split("from fastapi.testclient")[0])
from fastapi.testclient import TestClient
from PIL import Image, ImageDraw, ImageFont, ImageFilter
import numpy as np, pymupdf
c=TestClient(g["app"]); T="/tmp/meow_tests/"; LS="/usr/share/fonts/truetype/liberation/"
# realistic scan: A4 at 150dpi, greyish paper, slight noise, blur, jpeg
W,H=1240,1754
pg=Image.new("RGB",(W,H),(246,244,238)); d=ImageDraw.Draw(pg)
d.text((420,120),"Experiment 5",font=ImageFont.truetype(LS+"LiberationSerif-Bold.ttf",54),fill=(15,15,15))
d.text((120,260),"Student Name:",font=ImageFont.truetype(LS+"LiberationSerif-Bold.ttf",34),fill=(20,20,20))
d.text((390,266),"Rahul Sharma",font=ImageFont.truetype(LS+"LiberationSans-Regular.ttf",28),fill=(30,30,30))
d.text((760,260),"UID:",font=ImageFont.truetype(LS+"LiberationSerif-Bold.ttf",34),fill=(20,20,20))
d.text((850,266),"23BCS10001",font=ImageFont.truetype(LS+"LiberationSans-Regular.ttf",28),fill=(30,30,30))
d.text((120,330),"Branch: BE(CSE)",font=ImageFont.truetype(LS+"LiberationSerif-Regular.ttf",34),fill=(20,20,20))
a=np.array(pg).astype(float)+np.random.normal(0,4,(H,W,3)); pg=Image.fromarray(a.clip(0,255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(0.7))
pg.save(T+"scan.jpg",quality=85)
doc=pymupdf.open(); p=doc.new_page(width=595,height=842); p.insert_image(p.rect, filename=T+"scan.jpg"); doc.save(T+"scan.pdf")
up=c.post("/api/upload",files=[("files",("scan.pdf",open(T+"scan.pdf","rb"))),("files",("poster.jpg",open(T+"scan.jpg","rb")))]).json()["files"]
spdf, simg = up
print("scan pdf context:", g["FILES"][spdf["id"]]["text"][:160].replace("\n"," | "))
t0=time.time()
j=c.post("/api/tool",json={"op":"pdf_replace_text","files":[spdf["id"]],"params":{"find":"Rahul Sharma","replace":"Tarun Meena"}}).json(); print("AI replace (scan fallback):", j["ok"], j.get("message") or j.get("error"), f"{time.time()-t0:.1f}s")
out1=j["file"]["id"]
j=c.post("/api/tool",json={"op":"image_replace_text","files":[simg["id"]],"params":{"find":"23BCS10001","replace":"24BCS11991"}}).json(); print("AI image replace:", j["ok"], j.get("message") or j.get("error")); Image.open(g["FILES"][j["file"]["id"]]["path"]).crop((80,200,1200,400)).save(T+"img_after.png"); Image.open(T+"scan.jpg").crop((80,200,1200,400)).save(T+"img_before.png")
# editor flow on scanned pdf
o=c.post("/api/pdf/open",json={"file_id":out1}).json(); dr=o["draft"]["id"]
lay=c.get(f"/api/pdf/{dr}/layout/0").json(); print("runs on scan:", len(lay["runs"]), "images:", len(lay["images"]))
t0=time.time(); oc=c.get(f"/api/pdf/{dr}/ocr/0").json(); print("ocr boxes:", [(b["text"], b["size"], b["color"]) for b in oc["boxes"]], f"{time.time()-t0:.1f}s")
uid=[b for b in oc["boxes"] if "23BCS" in b["text"]][0]
j=c.post(f"/api/pdf/{dr}/edit",json={"ops":[{"op":"scan_text","page":0,"bbox":uid["bbox"],"text":uid["text"].replace("23BCS10001","24BCS11991"),"orig":uid["text"]}]}).json(); print("scan_text op:", j["ok"], j.get("error"))
dr=j["draft"]["id"]
pymupdf.open(g["FILES"][dr]["path"])[0].get_pixmap(dpi=110, clip=pymupdf.Rect(40,40,560,180)).save(T+"scan_after.png")
pymupdf.open(T+"scan.pdf")[0].get_pixmap(dpi=110, clip=pymupdf.Rect(40,40,560,180)).save(T+"scan_before.png")
# image in editor + save back to image
o=c.post("/api/pdf/open",json={"file_id":simg["id"]}).json(); di=o["draft"]["id"]; print("image opened as page:", o["pages"])
j=c.post(f"/api/pdf/{di}/edit",json={"ops":[{"op":"add_text","page":0,"x":60,"y":500,"text":"Approved ✔","size":30,"color":"#16a34a","family":"sans","bold":True}]}).json(); di=j["draft"]["id"]
sv=c.post(f"/api/pdf/{di}/save_image",json={"name":"poster_edited.jpg"}).json(); print("save_image:", sv["ok"], sv["file"]["name"], sv["file"]["meta"])
from PIL import Image as I2
a=I2.open(T+"scan_before.png"); b=I2.open(T+"scan_after.png"); cimg=I2.new("RGB",(a.width,a.height*2+8),(255,0,0)); cimg.paste(a,(0,0)); cimg.paste(b,(0,a.height+8)); cimg.save(T+"scan_cmp.png")
