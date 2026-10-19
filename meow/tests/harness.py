import os, sys, json, io
os.environ["MEOW_CAPTIONS"]="0"
class FakeLLM:
    metadata={"tokenizer.chat_template":"{% <|im_start|> %}"}
    last_prompt=None
    def n_ctx(self): return 16384
    def tokenize(self,b,add_bos=False,special=False): return list(range(len(b)//4+1))
    def detokenize(self,t): return b"x"*(len(t)*4)
    def create_completion(self, prompt, **kw):
        FakeLLM.last_prompt=prompt
        ans = "Here you go.\n\n```meow-tool\n{\"op\": \"pdf_watermark\", \"files\": [\"%s\"], \"params\": {\"text\": \"DRAFT\"}}\n```\n" % os.environ.get("FID","x")
        for w in (["thinking...","</think>\n"] if prompt.endswith("<think>\n") else [])+list(ans):
            yield {"choices":[{"text":w}]}
g={"__name__":"meow_test","llm":FakeLLM()}
exec(compile(open("/tmp/meow_tests/meow.py").read(),"meow.py","exec"), g)
from fastapi.testclient import TestClient
c=TestClient(g["app"])
import fitz
from PIL import Image
# make sample files
d=fitz.open(); 
for i in range(3):
    p=d.new_page(); p.insert_text((72,100),f"Hello page {i+1}. Invoice total 500 rupees.",fontsize=14)
d.save("/tmp/meow_tests/s.pdf")
Image.new("RGBA",(300,200),(120,80,200,255)).save("/tmp/meow_tests/a.png")
open("/tmp/meow_tests/d.csv","w").write("a,b\n1,2\n3,4\n")
import docx; dd=docx.Document(); dd.add_paragraph("Docx hello"); dd.save("/tmp/meow_tests/w.docx")
files=[("files",(n,open("/tmp/meow_tests/"+n,"rb"))) for n in ["s.pdf","a.png","d.csv","w.docx"]]
r=c.post("/api/upload",files=files); print("upload",r.status_code)
recs={f["name"]:f for f in r.json()["files"]}
for n,f in recs.items(): print(" ",n,f["kind"],f["meta"],repr(f["preview"][:60]))
pid=recs["s.pdf"]["id"]; iid=recs["a.png"]["id"]
print("index",c.get("/").status_code, "__USER_NAME__" in c.get("/").text)
print("health",c.get("/api/health").json())
print("thumb pdf",c.get(f"/api/thumb/{pid}").status_code, "img",c.get(f"/api/thumb/{iid}").status_code)
print("tools",len(c.get("/api/tools").json()["tools"]))
tests=[("pdf_merge",[pid,iid],{}),("pdf_extract_pages",[pid],{"pages":"1-2"}),("pdf_delete_pages",[pid],{"pages":"2"}),
("pdf_reorder",[pid],{"order":"3,1,2"}),("pdf_rotate",[pid],{"pages":"all","angle":"90"}),("pdf_watermark",[pid],{"text":"CONF"}),
("pdf_add_text",[pid],{"page":"1","text":"Hi","x":"72","y":"200"}),("pdf_page_numbers",[pid],{}),("pdf_replace_text",[pid],{"find":"500","replace":"750"}),
("pdf_redact",[pid],{"find":"Invoice"}),("pdf_highlight",[pid],{"find":"Hello"}),("pdf_compress",[pid],{}),("pdf_to_images",[pid],{"pages":"all"}),
("pdf_to_images",[pid],{"pages":"1"}),("pdf_to_text",[pid],{}),("pdf_protect",[pid],{"password":"abc"}),("images_to_pdf",[iid],{}),
("img_resize",[iid],{"width":"150","height":""}),("img_crop",[iid],{"left":"10","top":"10","right":"100","bottom":"100"}),("img_rotate",[iid],{"angle":"45"}),
("img_flip",[iid],{"direction":"vertical"}),("img_convert",[iid],{"format":"jpg"}),("img_convert",[iid],{"format":"pdf"}),("img_compress",[iid],{"quality":"60","format":"webp","max_side":""}),
("img_grayscale",[iid],{}),("img_enhance",[iid],{}),("img_upscale",[iid],{"scale":"2"}),("img_remove_bg",[iid],{}),
("make_pdf",[],{"title":"Test Doc","content":"# Hi\n\n- a\n- b\n\n| x | y |\n|---|---|\n| 1 | 2 |\n\n```py\nprint(1)\n```"}),("make_file",[],{"filename":"n.md","content":"hey"})]
locked=None
for op,f,p in tests:
    j=c.post("/api/tool",json={"op":op,"files":f,"params":p}).json()
    print(("OK " if j["ok"] else "ERR"),op,j.get("message") or j.get("error"))
    if op=="pdf_protect" and j["ok"]: locked=j["file"]["id"]
j=c.post("/api/tool",json={"op":"pdf_unlock","files":[locked],"params":{"password":"abc"}}).json(); print("unlock",j["ok"],j.get("message") or j.get("error"))
j=c.post("/api/tool",json={"raw":'{"op":"pdf_watermark","files":["$last"],"params":{"text":"multi\nline"}}',"last":pid}).json(); print("raw",j["ok"],j.get("message") or j.get("error"))
print("dl",c.get(f"/api/files/{pid}?dl=1").headers.get("content-disposition"))
os.environ["FID"]=pid
for mode in ("fast","think"):
    r=c.post("/api/chat",json={"prompt":"watermark it","mode":mode,"history":[{"role":"user","content":"hi"},{"role":"assistant","content":"<think>x</think>hello"}],"file_ids":[pid,iid],"rid":"r1"})
    evs=[l for l in r.text.split("\n\n") if l]
    toks="".join(json.loads(e[6:]).get("t","") for e in evs if e.startswith("data: {"))
    print(mode, r.status_code, len(evs), repr(toks[:40]), evs[-1])
lp=FakeLLM.last_prompt
print("prompt has file block:", '<file name="s.pdf"' in lp, "think stripped:", "<think>x</think>" not in lp, "ends:", repr(lp[-30:]))
