<div align="center">

# AscendFlow VideoMaker

**Cloud-API fork of [HKUDS/VideoAgent](https://github.com/HKUDS/VideoAgent), with a CapCut-style web UI.**

[![License](https://img.shields.io/badge/license-Apache_2.0-blue)](./LICENSE)
[![Python](https://img.shields.io/badge/python-3.10%2B-blue)](#)
[![Status](https://img.shields.io/badge/status-MVP-orange)](#)

</div>

> **Heads up**: This is a heavy fork of [HKUDS/VideoAgent](https://github.com/HKUDS/VideoAgent).
> Where the upstream runs everything **locally on GPU** (Whisper, CosyVoice, ImageBind, fish-speech, seed-vc, DiffSinger), this fork **swaps every model for a cloud API** (Aliyun DashScope / 百炼 + MiniMax) and ships a CapCut-style web UI, so the whole thing runs on a CPU-only box with ~1 GB of RAM and zero model downloads.

---

## TL;DR

```bash
git clone https://github.com/84JujubeTree/VideoAgent.git
cd VideoAgent
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-runtime.txt
pip install pydub librosa numpy            # only needed for the singing pipeline
sudo apt install ffmpeg
cp .env.example .env && $EDITOR .env       # fill in DASHSCOPE_API_KEY (+ MINIMAX_API_KEY for singing)
uvicorn app:app --host 0.0.0.0 --port 8008
```

Open http://localhost:8008.

---

## What this fork changes vs. upstream

| Aspect | Upstream HKUDS/VideoAgent | This fork |
|---|---|---|
| **ASR** | Whisper large-v3-turbo (local, ~5 GB) | Bailian `paraformer-v2` (API) |
| **TTS** | CosyVoice (local) | Bailian `cosyvoice-v2` (API) |
| **LLM** | Claude / GPT-4o / DeepSeek / Gemini (4 separate keys) | Bailian `qwen-plus` (one key) |
| **Embedding** | ImageBind (local, ~5 GB) | Bailian text embedding (API) |
| **Singing voice** | DiffSinger + seed-vc (note-level, local) | MiniMax `music-2.6` (API, prompt-based) |
| **Entrypoint** | CLI: `python main.py` then type prompt | FastAPI: `uvicorn app:app`, web UI on `:8008` |
| **GPU required** | Yes, 8 GB+ VRAM | No |
| **Model downloads** | ~30 GB across 6 checkpoints | None |
| **Config** | `environment/config/config.yml` (4 LLM blocks + tool paths) | `.env` |
| **Auth / rate limit** | None | `X-API-Key` header + per-IP sliding window |

The original CLI agent (`main.py` + `environment/agents/multi.py`) and the local model `tools/` directory are **kept in the tree but not used by `app.py`**. If you need the upstream's MAD SVC / VideoRAG / ImageBind features, run them from upstream directly.

---

## Architecture

```
                    ┌──── /static/{index.html, app.js, styles.css}
                    │     CapCut-style web UI, vanilla JS, no build step
HTTP :8008 ──┐      │
             ├─► app.py  (FastAPI)
             │     │      ├── GET  /                  → serves index.html
             │     │      ├── POST /generate/from_video
             │     │      ├── GET  /task/{id}         → poll progress
             │     │      ├── GET  /tasks
             │     │      ├── GET  /download
             │     │      └── GET  /health
             │     │
             │     └─── BackgroundTasks → _run_pipeline:
             │            ① probe        ffprobe (audio stream + duration)
             │            ② extract      ffmpeg → 16 kHz mono wav
             │            ③ asr          BailianASRProvider (paraformer-v2)
             │            ④ llm | lyrics qwen-plus, prompt switches on `style`
             │            ⑤ tts | singing
             │                ├── BailianTTSProvider     (cosyvoice-v2)
             │                │     ↳ style ∈ {standup, crosstalk, highlight}
             │                └── MinimaxSingingProvider (music-2.6)
             │                      ↳ style == "singing"
             │            ⑥ mux          ffmpeg, copy video + new audio
             │
             └─► /files (StaticFiles, exposes tmp_videos/{task_id}/...)
```

---

## Providers (swappable)

All cloud calls go through small `Protocol`-style classes in `providers/`. To plug in a different vendor (Tencent, Volcengine, Whisper API, OpenAI TTS, …) implement the matching interface and flip the env var.

| Capability | Default class | Mock for offline tests | Env switch |
|---|---|---|---|
| ASR | `BailianASRProvider` | `MockASRProvider` | `ASR_PROVIDER=bailian` |
| TTS | `BailianTTSProvider` | `MockTTSProvider` | `TTS_PROVIDER=bailian` |
| Embedding | `BailianEmbeddingProvider` | `MockEmbeddingProvider` | `EMBEDDING_PROVIDER=bailian` |
| Singing | `MinimaxSingingProvider` | `MockSingingProvider` | `SINGING_PROVIDER=minimax` |

Provider tests live next to them: `test_asr_mock.py`, `test_voice_generator.py`, `test_minimax_singing.py`, etc.

---

## Web UI features

* **3 rewrite styles**: 🎤 脱口秀 (standup) · 🎭 相声 (crosstalk) · 🎵 歌声合成 (MiniMax music-2.6)
* **6-stage live progress bar** with shimmer animation: 接收 → 预处理 → 识别原声 → AI 改写 → 合成配音/歌唱 → 合成视频
* **Canvas aspect dropdown**: 16:9 / 9:16 / 1:1 / 4:3
* **Zoom dropdown**: 50 / 75 / 100 / 125 / 150 % / fit
* **Quick-tile** portrait/landscape toggle, two-way synced with the aspect dropdown
* **Transcript tab**: latest task's ASR text gets piped into a dedicated side panel
* **Drag-and-drop** video upload, project name auto-derived from filename
* **Result drawer**: side-by-side original transcript + rewritten script
* **API-key popover** (`X-API-Key`) with `localStorage` persistence
* Optional **back-link** to a companion FireRed-OpenStoryline instance on `:8005`

The frontend is intentionally three flat files (no React, no bundler) so iterating on layout means saving a file and refreshing the tab.

---

## Singing pipeline notes

* MiniMax music API has **no note-level (MIDI) input** unlike DiffSinger. The provider sends the rewritten lyrics with `[Verse]` / `[Chorus]` tags and a style prompt, gets a complete song back, then `librosa.effects.time_stretch`-es it to match the original video duration.
* For a workflow closer to the upstream MAD SVC ("preserve the original song's melody, swap lyrics + voice"), switch to **`music-cover`** / **`music-cover-free`** and set `MINIMAX_REF_AUDIO_URL` to a publicly reachable reference song URL.
* Lyrics quality is bounded by `qwen-plus`. Tweak the singing prompt in `app.py::generate_script()` if the rhyme/phrasing isn't to taste.
* Default `MINIMAX_PROMPT="流行, 男声, 慢节奏, 怀旧, 干净人声"` — change in `.env` to taste; `provider.__init__` reads env, so a service restart is required.

---

## API reference

### `POST /generate/from_video`

Multipart form. Auth: optional `X-API-Key` header (set `API_KEYS=k1,k2` in `.env` to enable).

| field | type | description |
|---|---|---|
| `file` | file | mp4 / mov / avi / mkv with a clean voice track |
| `style` | string | `standup` · `crosstalk` · `highlight` · `singing` |

Returns `202` with `{ task_id, status, poll_url }`.

### `GET /task/{task_id}`

```jsonc
{
  "task_id": "...",
  "status": "running" | "succeeded" | "failed",
  "stage": "asr" | "llm" | "lyrics" | "tts" | "singing" | "mux" | "done",
  "progress": 0,                  // 0–100
  "result": {                     // populated when status=succeeded
    "style": "singing",
    "transcript": "...",          // ASR text
    "segments": [...],            // ASR segments with timestamps
    "script": "[Verse]\n...",     // rewritten lyrics or script
    "output_video_url": "/files/.../foo_output.mp4",
    "audio_url": "/files/.../sung.wav",
    "audio_provider": "music-2.6",
    "metadata_url": "/files/.../metadata.json"
  },
  "error": null
}
```

### `GET /health`

```json
{ "status": "ok" }
```

---

## Environment variables (`.env`)

```env
# Aliyun DashScope (bailian) — required
DASHSCOPE_API_KEY=
BAILIAN_ASR_MODEL=paraformer-v2
BAILIAN_LLM_MODEL=qwen-plus
BAILIAN_TTS_MODEL=cosyvoice-v2
BAILIAN_TTS_VOICE=longxiaochun_v2

# MiniMax — required for the 'singing' style
MINIMAX_API_KEY=
MINIMAX_BASE_URL=https://api.minimaxi.com
MINIMAX_MUSIC_MODEL=music-2.6
MINIMAX_PROMPT=流行, 男声, 慢节奏, 怀旧, 干净人声
MINIMAX_OUTPUT_FORMAT=url
MINIMAX_REF_AUDIO_URL=                # only for music-cover models

# Provider switches
ASR_PROVIDER=bailian
TTS_PROVIDER=bailian
EMBEDDING_PROVIDER=bailian
SINGING_PROVIDER=minimax              # set to 'disabled' to drop the singing card

# Server
HOST=0.0.0.0
PORT=8008

# Auth & rate limit
API_KEYS=                             # comma-separated; empty = auth disabled (dev only)
RATE_LIMIT_MAX=20
RATE_LIMIT_WINDOW_SEC=3600
```

---

## What's intentionally missing from this fork

* MAD SVC pipeline (note-level singing voice synthesis with reference song melody)
* ImageBind cross-modal retrieval
* VideoRAG retrieval
* The 168-KB multi-agent graph router (kept on disk, not wired into `app.py`)
* Local model checkpoints under `tools/`

If you need any of those, see [HKUDS/VideoAgent](https://github.com/HKUDS/VideoAgent) directly. PRs that re-introduce them as a switchable provider are welcome.

---

## Acknowledgments

* Upstream: **[HKUDS/VideoAgent](https://github.com/HKUDS/VideoAgent)** — agentic video framework, Apache 2.0
* Cloud APIs: **[Aliyun DashScope / 百炼](https://dashscope.console.aliyun.com/)** (paraformer-v2 / cosyvoice-v2 / qwen-plus), **[MiniMax 海螺](https://platform.minimaxi.com/)** (music-2.6)
* Libraries: `fastapi`, `uvicorn`, `pydantic`, `librosa`, `pydub`, `dashscope`, `requests`, `python-dotenv`
* `ffmpeg` for the heavy lifting

---

## License

Apache 2.0, inherited from upstream.
