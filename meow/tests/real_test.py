import os, io, time, glob
os.environ["MEOW_CAPTIONS"]="0"
exec(open("/tmp/meow_tests/harness.py").read().split("from fastapi.testclient")[0])
from PIL import Image, ImageDraw, ImageFont, ImageFilter
import numpy as np, cv2
T="/tmp/meow_tests/"; F="/tmp/meow_files/fonts/"
rng=np.random.default_rng(1)
cases=[]
# 1) light UI screenshot (Roboto, small, PNG)
im=Image.new("RGB",(820,300),(245,246,248)); d=ImageDraw.Draw(im)
d.rounded_rectangle((20,20,800,280),18,fill=(255,255,255),outline=(225,228,232))
d.text((50,60),"Payment to Rahul Sharma",font=ImageFont.truetype(F+"roboto__500Medium.ttf",28),fill=(32,33,36))
d.text((50,110),"Order ID 4471209 · 16 Oct 2026",font=ImageFont.truetype(F+"roboto__400Regular.ttf",20),fill=(95,99,104))
d.text((50,170),"Delivered to Sector 70, Mohali",font=ImageFont.truetype(F+"roboto__400Regular.ttf",22),fill=(60,64,67))
im.save(T+"r1.png"); cases.append(("r1.png",[("Rahul Sharma","Tarun Meena"),("4471209","5582310"),("Sector 70","Sector 82")]))
# 2) dark mode phone screenshot (Inter, semibold white)
im=Image.new("RGB",(900,360),(28,28,30)); d=ImageDraw.Draw(im)
d.text((40,50),"Good morning, Rahul",font=ImageFont.truetype(F+"inter__600SemiBold.ttf",44),fill=(250,250,250))
d.text((40,130),"Your meeting starts at 10:30 AM",font=ImageFont.truetype(F+"inter__400Regular.ttf",30),fill=(170,170,176))
im.save(T+"r2.png"); cases.append(("r2.png",[("Rahul","Tarun"),("10:30","11:45")]))
# 3) photo-like poster: textured gradient + bold Montserrat + JPEG
h,w=480,960; yy,xx=np.mgrid[0:h,0:w]
base=np.stack([120+60*np.sin(xx/90)+30*yy/h, 70+40*np.cos(yy/70), 140+50*np.sin((xx+yy)/150)],-1)
tex=cv2.GaussianBlur(rng.normal(0,18,(h,w,3)).astype(np.float32),(0,0),3)+rng.normal(0,5,(h,w,3))
img=Image.fromarray(np.clip(base+tex,0,255).astype(np.uint8)); d=ImageDraw.Draw(img)
d.text((80,120),"MEGA SALE",font=ImageFont.truetype(F+"montserrat__800ExtraBold.ttf",110),fill=(255,244,214))
d.text((84,270),"Flat 50% off this weekend",font=ImageFont.truetype(F+"montserrat__500Medium.ttf",44),fill=(255,255,255))
img=img.filter(ImageFilter.GaussianBlur(0.5)); img.save(T+"r3.jpg",quality=82); cases.append(("r3.jpg",[("50%","70%"),("weekend","Sunday")]))
# 4) scanned doc from before
cases.append(("scan.jpg",[("Rahul Sharma","Tarun Meena"),("23BCS10001","24BCS11991")]))
for name, edits in cases:
    src=Image.open(T+name); out=src.copy(); t0=time.time(); infos=[]
    for f_,r_ in edits:
        out,n,fonts=g["replace_in_image"](out,f_,r_, jpeg_hint=name.endswith(".jpg"))
        infos.append(f"{f_}->{r_}:{n}[{fonts}]")
    print(name, f"{time.time()-t0:.1f}s", " | ".join(infos), "lama:", g["FEATURES"].get("lama"))
    ext="png" if name.endswith("png") else "jpg"
    out.convert("RGB").save(T+"o_"+name.split(".")[0]+"."+ext, **({"quality":95} if ext=="jpg" else {}))
