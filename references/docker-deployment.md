# AEON Movie Maker — Docker Deployment Notes

## Critical Bug: `_SEP` Hardcoded for Windows

`movie_maker_fast.py` line 69:
```python
_SEP = "\\"   # WRONG on Linux/Docker
```
Must be:
```python
_SEP = os.sep
```

Without this fix, all LoRA paths like `ltx2\Ltx2.3-Licon-VBVR-I2V-96000-R32.safetensors` fail with `FileNotFoundError` on Linux.

**Patch pending upstream submission.**

## Critical: AEON CLI Runs on Host, ComfyUI Inside Docker

The AEON `movie_maker_fast.py` CLI runs on the **host machine** but ComfyUI lives **inside a Docker container**. Output files are written to `/workspace/ComfyUI/output/` inside the container — they never appear on the host filesystem unless explicitly copied.

The script checks `os.path.exists(p_local)` looking for output files, but on a Docker setup the file is inside the container, not on the host. This causes:
```
ERROR: no output video file found in history
outputs: {"71": {"images": [{"filename": "clip_00001_.mp4", "subfolder": "movie_fast", ...}]}}
```

**Fix:** The output-finding block needs `docker cp` logic added. See the patched version in:
`/home/a/.hermes/skills/creative/aeon-movie-maker/scripts/movie_maker_fast.py`

**Workaround:** Manually copy from container:
```bash
docker cp comfyui-spark:/workspace/ComfyUI/output/movie_fast/<file> .
```

**Environment variable for container name:**
```bash
COMFYUI_CONTAINER=comfyui-spark python3 scripts/movie_maker_fast.py clip ...
```

## AEON Setup.sh — Wrong Model Filenames (Fixed in upstream)

AEON commit `3c5deb8` (May 1 2026) fixed 4 model path/filename mismatches in `setup.sh`:
- `ltxv-distilled` page → users downloaded `ltxv-2b-0.9.7-distilled-fp8` (wrong model, produces saturated/distorted output)
- Correct file: `ltx-2.3-22b-distilled-fp8.safetensors` (~22GB) from `huggingface.co/Lightricks/LTX-Video`

**Symptom of wrong model:** Saturated, distorted, plasticky output — looks like a diffusion artifact failure.

## LoRA Strengths — Default 0.7 (Reduced from 1.0)

As of May 1 2026 update:
- VBVR physics: default 0.7 (was 1.0 — oversaturated)
- IC-LoRA Union: default 0.7 (was 1.0)

Override at CLI:
```bash
--vbvr-strength 0.5 --ic-lora-strength 0.5   # further reduce if still saturated
```

## Verified Working on DGX Spark / GB10

Tested May 2 2026:
- Container: `comfyui-spark` (port 8188 → host)
- GPU: NVIDIA GB10, 40GB VRAM free during generation
- Model: `ltx-2.3-22b-distilled-fp8.safetensors` (27GB)
- 5s clip @ 832×480: ~126s generation (0.04× realtime)
- T2V mode: `--t2v` flag (no seed image required)
