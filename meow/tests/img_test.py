import os, io, time
os.environ["MEOW_CAPTIONS"]="0"
exec(open("/tmp/meow_tests/harness.py").read().split("from fastapi.testclient")[0])
from PIL import Image, ImageDraw, ImageFont, ImageFilter
import numpy as np, pymupdf
T="/tmp/meow_tests/"
LS="/usr/share/fonts/truetype/liberation/"
# 1 clean doc image
im=Image.new("RGB",(1100,260),"white"); d=ImageDraw.Draw(im)
d.text((40,60),"Student Name:",font=ImageFont.truetype(LS+"LiberationSerif-Bold.ttf",34),fill=(0,0,0))
d.text((300,64),"Rahul Sharma",font=ImageFont.truetype(LS+"LiberationSans-Regular.ttf",30),fill=(20,20,20))
d.text((40,150),"UID: 23BCS10001   Section: 703 A",font=ImageFont.truetype(LS+"LiberationSerif-Regular.ttf",32),fill=(10,10,90))
im.save(T+"t1.png")
# 2 photo-like banner
w,h=1000,360; G=np.zeros((h,w,3),np.uint8)
for y in range(h): g[y,:]=[int(200-80*y/h), int(40+60*y/h), int(120+100*y/h)]
G=(G+np.random.normal(0,6,G.shape)).clip(0,255).astype(np.uint8); ban=Image.fromarray(G); d=ImageDraw.Draw(ban)
d.text((70,110),"SALE 50% OFF",font=ImageFont.truetype(LS+"LiberationSans-Bold.ttf",110),fill=(255,250,235))
ban=ban.filter(ImageFilter.GaussianBlur(0.6)); ban.save(T+"t2.jpg",quality=88)

t0=time.time()
for name,find,rep in [("t1.png","Rahul Sharma","Tarun Meena"),("t1.png","23BCS10001","24BCS11991"),("t2.jpg","50%","70%")]:
    src=Image.open(T+name)

    out,n,fonts=g["replace_in_image"](src.copy(), find, rep)
    print(name, find,"->",rep, "count",n,"font",fonts, f"{time.time()-t0:.1f}s")
    out.convert("RGB").save(T+f"out_{name.split('.')[0]}_{find[:3]}.png")
