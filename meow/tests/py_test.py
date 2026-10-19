import os, time, json, re
os.environ["MEOW_CAPTIONS"]="0"
class FakeLLM:
    metadata={"tokenizer.chat_template":"<|im_start|>"}
    calls=[]
    def n_ctx(self): return 16384
    def tokenize(self,b,add_bos=False,special=False): return list(range(len(b)//4+1))
    def detokenize(self,t): return b"x"*(len(t)*4)
    def create_completion(self, prompt, **kw):
        FakeLLM.calls.append((prompt[-300:], kw.get("stop")))
        tail = prompt.split("<|im_start|>assistant\n")[-1]
        if "meow-output" not in tail:
            text = "Let me compute that.\n\n```meow-python\nimport numpy as np, pandas as pd, matplotlib.pyplot as plt\ndf = pd.read_csv(FILES['d.csv'])\nprint('rows', len(df))\nplt.plot(df.iloc[:,1]); plt.title('Trend')\ndf.to_excel(f'{OUT_DIR}/summary.xlsx')\ndf.iloc[:,1].sum()\n```\n\nThe output will be... (should never be reached)"
        elif tail.count("meow-output") == 1:
            text = "Now an error check:\n```meow-python\n1/0\n```\nignored"
        else:
            text = "Done. The total is shown above.\n\n<<followups: plot by month? | export as PDF?>>"
        for i in range(0,len(text),5): yield {"choices":[{"text":text[i:i+5]}]}
g={"__name__":"x","llm":FakeLLM()}
exec(compile(open("/tmp/meow_tests/meow.py").read(),"meow.py","exec"), g)
from fastapi.testclient import TestClient
c=TestClient(g["app"])
up=c.post("/api/upload",files=[("files",("d.csv",open("/tmp/meow_tests/d.csv","rb")))]).json()["files"][0]
t=time.time()
r=c.post("/api/chat",json={"prompt":"sum column 2 and chart it","mode":"fast","web":"off","history":[],"file_ids":[up["id"]],"rid":"p1","chat_id":"chatA"})
ev=[json.loads(l[6:]) for l in r.text.split("\n") if l.startswith("data: {")]
txt="".join(e.get("t","") for e in ev)
print(f"{time.time()-t:.1f}s rounds={len(FakeLLM.calls)} stop has output-guard:", "```meow-output" in FakeLLM.calls[0][1])
print(txt)
print("files events:", [f["name"] for e in ev if "files" in e for f in e["files"]])
print("never reached text excluded:", "should never be reached" not in txt)
# persistence of variables across messages in same chat
FakeLLM.calls.clear()
k=g["kernel_for"]("chatA"); print("persist:", k.run("df.shape", {})["result"])
print("timeout:", g["PyKernel"](g["WORK_DIR"]+"/py/t").run("import time; time.sleep(5)", {}, timeout=2)["error"])
