# Meow 🐈

Tarun's own ChatGPT/Claude-style assistant. It runs a Qwen GGUF model on a free Kaggle GPU, with:

- **Answering:** Fast and Think modes
- **Search:** web search, Reddit deep search (several rounds), YouTube transcripts, Wikipedia, research papers, GitHub, Stack Overflow and Hacker News; it also reads any link you paste
- **Code interpreter:** runs Python and draws charts
- **Editors:** a visual PDF/image editor, photo-real text replacement inside images, a magic eraser, and 40+ file tools
- **Extras:** voice mode, Mermaid diagrams, live HTML preview, and a galaxy UI

## Start Meow with one click (recommended)

Meow starts on a Kaggle GPU through the Kaggle API, sends a notification to your phone with the link, and **turns itself off when you stop using it**, so GPU hours aren't wasted.

**On your laptop (Windows):**
1. Download `start_meow.py` and `Start Meow.bat` into one folder. You need Python from python.org.
2. Double-click **Start Meow.bat**. The first time, it asks for:
   - your Kaggle username and API token (kaggle.com → Settings → API → *Generate New Token*)
   - your ngrok / Serper / Tavily keys
   - a password for Meow

   These are saved in `meow_config.json` next to the script. That file is private: never upload it.
3. Meow opens in your browser when it's ready, in about 5 min (Kaggle downloads the model in about a minute each time). If Kaggle is busy, it may queue for a few minutes first.

**On your phone:**
- Install the **ntfy** app and subscribe to the topic shown by the script (`meow-…`). You get a notification with an *Open Meow* button every time it starts.
- To start Meow from the phone, use the GitHub button: copy [`github/meow.yml`](github/meow.yml) to `.github/workflows/` on the `main` branch, then add the repo secrets listed at the top of that file. After that: GitHub app → Actions → **Meow** → *Run workflow*.

**Commands:** `python start_meow.py` (start) · `status` · `logs` · `stop` · `reset` (deletes Meow's Kaggle notebooks for a completely fresh start). In the app, **Power off Meow** in the sidebar releases the GPU right away.

## Run it on Kaggle (one cell)

1. Create a Kaggle notebook. In the right panel set **Accelerator: GPU T4 ×2** and **Internet: ON**.
2. Paste the whole of [`kaggle_launcher.py`](kaggle_launcher.py) into **one cell** and fill in your keys at the top. Or leave the keys empty and add them under *Add-ons → Secrets* with the same names.
3. Run the cell and open the link it prints.

Every run downloads the **newest `meow.py` from this branch**, so updates reach you automatically. Re-running the cell keeps the model loaded on the GPU, so it restarts in seconds.

### Faster starts (optional)

- **Model:** add the GGUF file as a Kaggle Model or Dataset input. Meow finds it under `/kaggle/input` and skips the ~15 GB download.
- **llama-cpp-python:** if the launcher has to compile it (15–25 min), it saves the wheel in `/kaggle/working/wheels`. Upload that folder as a private Kaggle Dataset and attach it, and later sessions install it in seconds.

### Keys (never commit them)

The launcher passes these to Meow as environment variables. Kaggle Secrets with the same names also work.

| Name | What for |
|---|---|
| `NGROK_AUTH_TOKEN` | public link (without it Meow uses a Cloudflare tunnel) |
| `SERPER_API_KEY` | Google results, YouTube videos and image search |
| `TAVILY_API_KEY` | pages that block Kaggle, extra Reddit coverage |
| `REDDIT_CLIENT_ID` / `REDDIT_CLIENT_SECRET` | optional official Reddit API |
| `GITHUB_TOKEN` | optional: higher GitHub search limits, or a private repo |
| `MEOW_PASSWORD` | password for the Meow page (strongly recommended with one-click start) |
| `MEOW_NTFY_TOPIC` | your ntfy topic for "Meow is live" notifications |
| `MEOW_IDLE_MIN` / `MEOW_MAX_HOURS` | auto power-off after this many idle minutes / hours in total (defaults: 40 min / 8 h) |

## For developers: how to update Meow

`meow.py` is **generated** from the files in [`src/`](src). Edit those, never `meow.py` directly.

| File | Contents |
|---|---|
| `p1.py` | config, model loading, file store, text extraction, OCR |
| `p2.py` | tool registry and basic PDF/image tools |
| `p2b.py` | visual editor engine (PDF ops, images, pages) |
| `p2c.py` | photo-real text editing (font matching, inpainting, LaMa/ESRGAN) and the magic eraser |
| `p2d.py` | web search engines, Reddit (official/archive/Tavily), page reading, ranking, planner, rules for answering from results |
| `p2e.py` | Python code interpreter (persistent kernel per chat) |
| `p2f.py` | specialist sources, link reader, multi-round deep research (`web_research`) |
| `p2g.py` | PDF→Word, searchable scans, form filling, PDF compare, photo restore |
| `p3.py` | system prompt, prompt building, FastAPI routes, chat streaming loop, launch |
| `p3b.py` | editor API routes |
| `h1.html`, `h2.html` | chat UI (CSS + JS) |
| `h1b.html`, `ed.js` | visual editor UI |

To build and test:

```bash
python meow/src/build.py            # writes meow/meow.py (refuses if a private key slipped in)
node --check /tmp/meow.js           # syntax-check the page's JavaScript
python meow/tests/run_tests.py      # offline tests: fake model, mocked internet
```

For each release:
1. Bump `MEOW_VERSION` and add an entry to `MEOW_CHANGELOG` in `src/p1.py`. Users see it under *What's new*.
2. Rebuild, then commit and push to the `meow` branch.

Every start picks the update up automatically.
