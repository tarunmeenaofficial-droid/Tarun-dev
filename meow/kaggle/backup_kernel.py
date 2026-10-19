# 🐈 Meow — one-time MODEL BACKUP job (runs on a Kaggle CPU notebook, no GPU queue).
# Started by:  python start_meow.py backup
#
# 1. downloads the model GGUF from Hugging Face (~1 min on Kaggle)
# 2. saves it as YOUR private Kaggle dataset  <you>/meow-model   → Meow mounts it instantly on every start
# 3. (optional) uploads it to YOUR private GitHub repo as release parts (<2 GiB each) + manifest.json
# so Meow keeps working even if the original Hugging Face repo disappears.
# start_meow.py fills in CFG below and deletes this notebook when the backup is done (it contains your tokens).

CFG = {
    "KAGGLE_USERNAME": "",
    "KAGGLE_TOKEN": "",
    "GH_REPO": "",
    "GH_TOKEN": "",
    "NTFY": "",
}

REPO_ID = "HauhauCS/Qwen3.8-27B-Uncensored-HauhauCS-Aggressive-MTP-GGUF"   # keep in sync with src/p1.py
GGUF_FILENAME = "Qwen3.8-27B-Uncensored-HauhauCS-Aggressive-IQ4_XS.gguf"
DATASET_SLUG = "meow-model"
RELEASE_TAG = "model"                    # GitHub release that holds the parts
PART = 1900 * 1024 * 1024                # GitHub release files must be < 2 GiB

import os, re, sys, json, time, shutil, hashlib, subprocess

def say(*a): print(*a, flush=True)
def sh(cmd): return subprocess.run(cmd, shell=True, capture_output=True, text=True)

t0 = time.time()
sh(f"{sys.executable} -m pip install -q -U kaggle huggingface_hub hf_xet requests")
import requests

WORK = "/tmp/meow_model"
os.makedirs(WORK, exist_ok=True)
free = shutil.disk_usage(WORK).free / 2**30
say(f"💽 free disk: {free:.0f} GB")

# ---------- 1. download from Hugging Face ----------
path = os.path.join(WORK, GGUF_FILENAME)
if not os.path.exists(path):
    os.environ["HF_XET_HIGH_PERFORMANCE"] = "1"
    from huggingface_hub import hf_hub_download
    say(f"⬇️  Downloading {GGUF_FILENAME} from Hugging Face…")
    hf_hub_download(repo_id=REPO_ID, filename=GGUF_FILENAME, local_dir=WORK)
size = os.path.getsize(path)
say(f"✅ model downloaded: {size / 2**30:.2f} GiB in {time.time() - t0:.0f}s")

parts = []                                   # (name, offset, length, sha256)
whole = hashlib.sha256()
with open(path, "rb") as f:
    i = 0
    while True:
        off = f.tell(); h = hashlib.sha256(); n = 0
        while n < PART:
            b = f.read(min(64 << 20, PART - n))
            if not b: break
            h.update(b); whole.update(b); n += len(b)
        if not n: break
        parts.append((f"{GGUF_FILENAME}.part{i:02d}", off, n, h.hexdigest())); i += 1
manifest = {"file": GGUF_FILENAME, "size": size, "sha256": whole.hexdigest(), "source": REPO_ID,
            "parts": [{"name": p[0], "size": p[2], "sha256": p[3]} for p in parts]}
say(f"🔒 sha256 {manifest['sha256'][:16]}… ({len(parts)} parts for GitHub)")

results = {}

# ---------- 2. private Kaggle dataset ----------
def kaggle_backup():
    tok = CFG["KAGGLE_TOKEN"].strip()
    if re.fullmatch(r"[0-9a-f]{32}", tok):
        os.environ["KAGGLE_USERNAME"], os.environ["KAGGLE_KEY"] = CFG["KAGGLE_USERNAME"], tok
    else:
        os.environ["KAGGLE_API_TOKEN"] = tok
    from kaggle.api.kaggle_api_extended import KaggleApi
    api = KaggleApi(); api.authenticate()
    ref = f"{CFG['KAGGLE_USERNAME']}/{DATASET_SLUG}"
    try:
        files = api.dataset_list_files(ref).files or []
        if any(getattr(x, "name", "") == GGUF_FILENAME for x in files):
            say(f"✅ Kaggle dataset {ref} already has the model — skipping upload"); return ref
    except Exception:
        pass                                             # doesn't exist yet
    json.dump(manifest, open(os.path.join(WORK, "manifest.json"), "w"), indent=1)
    say(f"⬆️  Uploading to your PRIVATE Kaggle dataset {ref} (10-30 min)…")
    for lic in ("other", "unknown", "CC0-1.0"):           # private dataset; the license field is just required metadata
        json.dump({"title": "Meow model", "id": ref, "licenses": [{"name": lic}]},
                  open(os.path.join(WORK, "dataset-metadata.json"), "w"))
        try:
            r = api.dataset_create_new(WORK, public=False, quiet=True, convert_to_csv=False, dir_mode="skip")
        except Exception as e:
            if "licen" in str(e).lower(): continue
            raise
        err = getattr(r, "error", None)
        if not (err and "licen" in str(err).lower()): break
    if err and "already" in str(err).lower():           # exists but without the file → add a new version
        r = api.dataset_create_version(WORK, "model backup", quiet=True, convert_to_csv=False, dir_mode="skip")
        err = getattr(r, "error", None)
    if err: raise RuntimeError(err)
    for _ in range(120):                                 # wait until Kaggle has processed it
        st = str(api.dataset_status(ref)).lower()
        if "ready" in st: break
        time.sleep(30)
    say(f"✅ Kaggle dataset ready: https://www.kaggle.com/datasets/{ref}")
    return ref

# ---------- 3. private GitHub release ----------
class Slice:                                             # a file range that requests can stream with a Content-Length
    def __init__(self, f, off, n): self.f, self.left = f, n; f.seek(off)
    def __len__(self): return self.left
    def read(self, k=-1):
        k = self.left if k is None or k < 0 else min(k, self.left)
        b = self.f.read(k); self.left -= len(b); return b

def github_backup():
    repo, tok = CFG["GH_REPO"], CFG["GH_TOKEN"]
    api = "https://api.github.com"
    H = {"Authorization": f"Bearer {tok}", "Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
    r = requests.get(f"{api}/repos/{repo}", headers=H, timeout=30)
    if r.status_code == 404:                             # create it (needs a classic token with the repo scope)
        say(f"📁 Creating private repo {repo}…")
        r = requests.post(f"{api}/user/repos", headers=H, timeout=30,
                          json={"name": repo.split("/")[1], "private": True, "auto_init": True,
                                "description": "Private backup of Meow's model"})
        if r.status_code >= 300: raise RuntimeError(f"couldn't create {repo}: {r.status_code} {r.text[:200]}")
        time.sleep(3)
    elif r.status_code >= 300:
        raise RuntimeError(f"can't open {repo}: {r.status_code} {r.text[:200]}")
    elif not r.json().get("private"):
        raise RuntimeError(f"{repo} is PUBLIC — make it private first (Settings → Danger zone → Change visibility)")
    r = requests.get(f"{api}/repos/{repo}/releases/tags/{RELEASE_TAG}", headers=H, timeout=30)
    if r.status_code == 404:
        r = requests.post(f"{api}/repos/{repo}/releases", headers=H, timeout=30,
                          json={"tag_name": RELEASE_TAG, "name": "Meow model",
                                "body": f"`{GGUF_FILENAME}` split into {len(parts)} parts. Meow downloads and joins them by itself."})
        if r.status_code >= 300: raise RuntimeError(f"couldn't create the release: {r.status_code} {r.text[:200]}")
    rel = r.json()
    upload = rel["upload_url"].split("{")[0]
    have = {a["name"]: a for a in rel.get("assets", [])}

    def put(name, data, n):
        old = have.get(name)
        if old and old.get("state") == "uploaded" and old.get("size") == n:
            say(f"   ✓ {name} already uploaded"); return
        for attempt in range(4):
            if old or attempt:                           # remove a broken/partial copy first
                for a in requests.get(f"{api}/repos/{repo}/releases/{rel['id']}/assets?per_page=100", headers=H, timeout=30).json():
                    if a["name"] == name:
                        requests.delete(f"{api}/repos/{repo}/releases/assets/{a['id']}", headers=H, timeout=30)
            try:
                body = data() if callable(data) else data
                rr = requests.post(f"{upload}?name={name}", data=body, timeout=(30, 1800),
                                   headers={**H, "Content-Type": "application/octet-stream", "Content-Length": str(n)})
                if rr.status_code < 300:
                    say(f"   ⬆️  {name} ({n / 2**30:.2f} GiB)"); return
                say(f"   retry {name}: {rr.status_code} {rr.text[:150]}")
            except Exception as e:
                say(f"   retry {name}: {str(e)[:150]}")
            time.sleep(10 * (attempt + 1))
        raise RuntimeError(f"upload of {name} failed")

    say(f"⬆️  Uploading {len(parts)} parts to the private GitHub release {repo} @ {RELEASE_TAG}…")
    with open(path, "rb") as f:
        for name, off, n, _ in parts:
            put(name, lambda off=off, n=n: Slice(f, off, n), n)
    m = json.dumps(manifest, indent=1).encode()
    have.pop("manifest.json", None)
    put("manifest.json", m, len(m))
    say(f"✅ GitHub backup ready: https://github.com/{repo}/releases/tag/{RELEASE_TAG}")
    return repo

ok = True
for label, fn, on in (("kaggle", kaggle_backup, True), ("github", github_backup, bool(CFG["GH_REPO"] and CFG["GH_TOKEN"]))):
    if not on: continue
    try:
        results[label] = fn()
        say(f"BACKUP_{label.upper()}_OK {results[label]}")
    except Exception as e:
        ok = False; say(f"BACKUP_{label.upper()}_FAILED {str(e)[:300]}")

msg = "Model backup done: " + ", ".join(f"{k} → {v}" for k, v in results.items()) if results else "Model backup failed — run: python start_meow.py backup"
if CFG["NTFY"]:
    try: requests.post(f"https://ntfy.sh/{CFG['NTFY']}", data=msg.encode(), headers={"Title": "🐈 Meow backup", "Tags": "floppy_disk"}, timeout=15)
    except Exception: pass
shutil.rmtree(WORK, ignore_errors=True)                  # nothing big is left in this notebook's output
say(f"BACKUP_DONE {'ok' if ok else 'partial'} in {(time.time() - t0) / 60:.0f} min")
