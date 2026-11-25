# StoryTube Studio

A local, full-stack web application (Windows & Mac/Linux) that automates end-to-end YouTube story-video production using Google Gemini (topics, scripts, scenes, TTS, YouTube SEO), **FastSD CPU + Real-ESRGAN** (100% local `1920×1080` anime watercolor scene art & thumbnail backgrounds), FFmpeg, MoviePy, Pillow, FastAPI, and React.

---

## One-Command Local Setup

**Prerequisites**: Python 3.10+, Node.js 18+, Git, and FFmpeg (`winget install Gyan.FFmpeg` on Windows / `brew install ffmpeg` on macOS).  
**Expected Disk Space**: **~5–10 GB** (FastSD CPU Python environment + SD 1.5 `Lykon/dreamshaper-8` + `latent-consistency/lcm-lora-sdv1-5` + TAESD + Real-ESRGAN portable CLI).

### Windows
```bat
setup_local.bat
```
### macOS / Linux
```bash
chmod +x setup_local.sh start.sh
./setup_local.sh
```

What `setup_local` does automatically:
1. Verifies Python 3.10+, Git, FFmpeg, and `uv`.
2. Clones `https://github.com/rupeshs/fastsdcpu` into `./tools/fastsdcpu` and runs its official installer (`install.bat` / `install.sh` / `install-mac.sh`).
3. Downloads SD 1.5 (`Lykon/dreamshaper-8`), LCM-LoRA (`latent-consistency/lcm-lora-sdv1-5`), and `madebyollin/taesd` into the Hugging Face cache.
4. Downloads the portable **Real-ESRGAN ncnn Vulkan CLI (`v0.2.5.0`)** (the same engine used by Upscayl, including `realesrgan-x4plus-anime`) into `./tools/upscayl/`.
5. Creates `.env` with `DEFAULT_PROVIDER=local_sd`, `FASTSD_URL=http://127.0.0.1:8000`, and `UPSCAYL_BIN` configured.
6. Runs a self-test generating a `512×288` image, upscaling 4× to `1920×1080`, and printing `PASS/FAIL`.

---

## How to Run

1. Edit `.env` and add your **`GEMINI_API_KEY`** (used for topics, scripts, scene splits, short SD 1.5 prompt rewrites, TTS, and YouTube SEO).
2. Start **FastSD CPU + StoryTube Backend + React Frontend** together:
   - **Windows**: Double-click `start.bat` (or run `.\start.bat`)
   - **macOS / Linux**: `./start.sh`
3. Open **`http://localhost:5173`** in your browser.
   - StoryTube Backend runs on `http://127.0.0.1:8001` so FastSD CPU can use `http://127.0.0.1:8000`.
   - If FastSD CPU isn't running when you click **Generate** or **Test One Image** on Step 6, the backend also auto-starts it from `./tools/fastsdcpu`.

---

## Models & Local Image Pipeline

| Task | Engine / Model | Details |
| :--- | :--- | :--- |
| **Text (Topics, Script, Scenes, SD 1.5 Rewrite, YouTube SEO)** | `gemini-3.5-flash` *(fallback: `gemini-3.8-flash`)* | Rewrites each scene prompt under 60 words for SD 1.5 |
| **TTS Voiceover** | `gemini-3.8-flash-tts` *(fallback: `edge-tts`)* | Exact per-scene WAV timing |
| **Images (Local SD — Default)** | **FastSD CPU** (`Lykon/dreamshaper-8` + `lcm-lora-sdv1-5`) + **Real-ESRGAN** | `512×288` (`4–6` steps, CFG `1.0–1.5`), upscaled 4× via `realesrgan-x4plus-anime`, fitted to `1920×1080` via Pillow `LANCZOS` |
| **Images (Fallback)** | `gemini-3.1-flash-image` | Selectable in **Settings** or Step 6 dropdown |

---

## Loading a Custom Watercolor / Anime SD 1.5 Checkpoint or LoRA from Civitai

You can customize the visual style by loading a painterly anime SD 1.5 checkpoint or LoRA from Civitai into FastSD CPU:

1. **Using a Civitai SD 1.5 LoRA (`.safetensors`)**:
   - Download a **Stable Diffusion 1.5** LoRA `.safetensors` file from Civitai.
   - Copy it into `./tools/fastsdcpu/lora_models/`.
   - Start FastSD CPU Web UI (`tools/fastsdcpu/start-webui.bat` or `./start-webui.sh`), open the **LoRA** tab/settings, enable the LoRA with weight `0.5–0.8`, or configure it in FastSD CPU's `configs/settings.yaml`.
2. **Using a Civitai SD 1.5 Checkpoint**:
   - Place a Diffusers-format SD 1.5 model folder inside `./tools/fastsdcpu/models/` (or convert a single-file `.safetensors` checkpoint using Diffusers' `from_single_file` and save it locally), then set that local folder path as `base_model_id` in FastSD CPU's `configs/lcm-lora-models.txt` / settings.
   - Keep StoryTube Studio's scene prompts free of copyrighted studio or character names—let the model weights and watercolor style prompt provide the aesthetic.

---

## Troubleshooting

- **Service not reachable (`FastSD CPU is not reachable at http://127.0.0.1:8000`)**:
  - Ensure you ran `setup_local.bat` / `./setup_local.sh` so `./tools/fastsdcpu` exists.
  - Check `./projects/fastsdcpu.log` or start FastSD CPU manually (`cd tools/fastsdcpu && start-webserver.bat` on Windows, or `./start-webserver.sh` on Mac/Linux) and verify `http://127.0.0.1:8000/api/docs` loads.
- **Vulkan not supported / Upscaler falls back to Pillow LANCZOS**:
  - `realesrgan-ncnn-vulkan` requires a Vulkan-capable GPU driver. Update your GPU drivers, or simply keep working—StoryTube Studio automatically falls back to Pillow `LANCZOS` resizing (`1920×1080`) and displays a notice in Step 6, or you can toggle **Upscale** off in **Settings**.
- **Out of Memory (RAM / VRAM)**:
  - Close heavy browser tabs or GPU apps, switch **4× Upscaling** off in **Settings**, and use **Test One Image** on Step 6 first.
- **Slow generation on CPU**:
  - Lower **LCM-LoRA Steps** to `4` in **Settings** (`4–6` range).
  - First-time generation downloads/warms model weights (~1–3 minutes once); subsequent `512×288` scenes are much faster.
  - Start with **15s Quick Test Mode** (2–3 scenes) before running a 60–75 scene video.
