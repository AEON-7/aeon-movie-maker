#!/usr/bin/env python3
"""Movie Maker Fast — LTX 2.3 based cinematic video generator.

DISTINCT from the WAN MultiTalk pipeline (`render_all_acts.py` / `multitalk_workflow.py`),
which is preserved as "Movie Maker Slow WAN". That tool optimizes for tight lip-sync
at ~20–30 min per shot. This tool optimizes for speed and motion coherence at ~30–60 s
per clip, using LTX 2.3 distilled + abliterated Gemma encoder + VBVR physics LoRA +
IC-LoRA union control for character consistency, and per-scene LoRA routing driven
by screenplay tags.

Typical speeds on RTX 5090 (for a 3-minute drama ≈ 25 × 7s clips):
  - Movie Maker Slow WAN:  4–6 hours
  - Movie Maker Fast:      15–25 minutes  (10–15× speedup)

Pipeline:
  1. Parse screenplay (same schema as produce.py / AGENT_CINEMA_AUTOPILOT).
  2. Per scene: render each clip via LTX 2.3 I2V, ≤7 s each; long scenes auto-chunk
     with seeded continuity.
  3. Per-scene LoRA stack:
       always: distill (0.5) + IC union control (1.0) + VBVR physics (1.0)
       plus:   pose / camera / motion / reasoning / transition / style by tag
  4. Character consistency: IC-LoRA reference image + per-character seed offset
     + optional talkvid LoRA on close-ups.
  5. Three-pass audio (all in scene_production_tool/music_tool modules):
       dialogue: Qwen3-TTS VoiceDesign + Three-Lock
       music:    music_maker.build_ace_workflow(variant=xl_base)
       SFX:      radio_drama.generate_sfx() MMAudio → SAO → ACE priority
  6. Stitch with 0.8 s xfade between clips, sidechain-ducked music, loudnorm -16 LUFS.

Models (canonical comfyui-aeon-spark asset layout — see download_models.py for sources):

  Base (fast):    models/checkpoints/ltx-2.3-22b-distilled-fp8.safetensors  (default — distilled FP8, fewer steps)
  Base (quality): models/checkpoints/ltx-2.3-22b-dev-fp8.safetensors        (non-distilled FP8, more steps, higher fidelity)
  Video VAE:      models/vae/LTX23_video_vae_bf16.safetensors
  Text enc:       models/text_encoders/gemma_3_12B_it.safetensors           (Comfy-Org/ltx-2 split)
  Heretic LoRA:   models/loras/gemma-3-12b-it-abliterated_heretic_lora_rank64_bf16.safetensors
                  (abliterated CLIP LoRA — present on disk for workflows that wire it in;
                   NOT auto-loaded by this script because always_on_loras targets the
                   diffusion model only. See README §Abliteration for manual wiring.)
  Distill LoRA:   models/loras/ltx-2.3-22b-distilled-lora-384.safetensors   (quality mode — distillation assist on the non-distilled base)
  Union LoRA:     models/loras/ltx-2.3-22b-ic-lora-union-control-ref0.5.safetensors
  VBVR LoRA:      models/loras/ltx2/Ltx2.3-Licon-VBVR-I2V-96000-R32.safetensors
"""
import argparse, json, os, random, shutil, subprocess, sys, tempfile, time
import urllib.request, urllib.error, urllib.parse

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, ".."))
# COMFYUI_ROOT must point at the user's actual ComfyUI install — that's where
# the script writes intermediate frames into input/_movie_fast_frames/ (so the
# ComfyUI VAE encoder can read them) and where output/ lands. Default to the
# repo root if unset (creates input/ + output/ under the repo).
COMFYUI_ROOT = os.environ.get("COMFYUI_ROOT", REPO_ROOT)
FFMPEG = shutil.which("ffmpeg") or os.environ.get("FFMPEG", "ffmpeg")
FFPROBE = shutil.which("ffprobe") or os.environ.get("FFPROBE", "ffprobe")
COMFYUI_URL = os.environ.get("COMFYUI_URL", "http://127.0.0.1:8188")
OUTPUT_ROOT = os.environ.get("OUTPUT_DIR", os.path.join(COMFYUI_ROOT, "output"))


# ============================================================================
# Model stack — canonical defaults, mirrored from VBVR_EROS workflow
# ============================================================================

# Path separator inside ComfyUI's `filename` field for nested model subdirectories.
# ComfyUI normalises both `/` and `\` internally, but the model lookup compares the
# request value against a list of registered model paths that use the host OS's
# native separator. So Linux/macOS hosts need `/` and Windows hosts need `\`.
# Auto-detect from os.sep so `fast` and `quality` modes work cross-platform without
# editing this constant. (Previous hard-coded `\\` broke every non-Windows host with
# `value_not_in_list` errors on the `ltx2/Ltx2.3-...` LoRA — bug fix 2026-05-03.)
import os as _os
_SEP = _os.sep

# Two render modes — both video-only; choose based on speed vs. fidelity:
#
#   "fast"    — ltx-2.3-22b-distilled-fp8.safetensors (~22 GB).
#               Distilled checkpoint, low CFG, ~24 steps. ~2× faster than quality
#               mode. Best for narrative / character-driven content. DEFAULT.
#
#   "quality" — ltx-2.3-22b-dev-fp8.safetensors (~29 GB).
#               Non-distilled FP8 base. Slower per step, higher prompt-fidelity
#               and motion variety. Distill LoRA at 0.5 strength applied for
#               partial step compression. Use when fast-mode output looks too
#               "average" or when you need stronger prompt adherence.
#
# Either mode accepts the same per-scene LoRA routing.
# joint_av is retained as a flag for forward-compat with future audio-capable
# checkpoints; no currently-shipped model exercises that branch.
MODES = {
    "fast": {
        # Default for narrative / character-driven content.
        # Drops the distill LoRA (already baked in), keeps union control + VBVR physics.
        # LoRA strengths defaulted at 0.7 — tuned for clean realistic output.
        # If your renders look over-saturated or distorted, lower further to 0.5;
        # if they look too "neutral" / under-stylized, bump up toward 1.0.
        # CLI overrides: --vbvr-strength, --ic-lora-strength, --distill-strength.
        "checkpoint":   "ltx-2.3-22b-distilled-fp8.safetensors",
        "video_vae":    "LTX23_video_vae_bf16.safetensors",
        # Canonical Comfy-Org/ltx-2 split-files layout (matches comfyui-aeon-spark
        # download_models.py). Note: this is the BASE Gemma encoder. Abliteration
        # (uncensored output) requires applying gemma-3-12b-it-abliterated_heretic_lora_rank64_bf16.safetensors
        # ON TOP of this encoder — that LoRA is downloaded by comfyui-aeon-spark
        # but is NOT auto-loaded here because always_on_loras targets the diffusion
        # model only (LoraLoaderModelOnly). Wire it in via a custom workflow if you
        # need uncensored prompting; the file is at models/loras/ for that purpose.
        "text_encoder": "gemma_3_12B_it.safetensors",
        "joint_av":     False,
        "always_on_loras": [
            ("ltx-2.3-22b-ic-lora-union-control-ref0.5.safetensors", 0.7),
            (f"ltx2{_SEP}Ltx2.3-Licon-VBVR-I2V-96000-R32.safetensors", 0.7),
        ],
    },
    "quality": {
        # Non-distilled FP8 base — slower per step, higher prompt-fidelity vs fast mode.
        # Distill LoRA at 0.5 partially compresses step count without fully baking
        # in the distilled behaviour, giving more motion variety than pure fast mode.
        "checkpoint":   "ltx-2.3-22b-dev-fp8.safetensors",
        "video_vae":    "LTX23_video_vae_bf16.safetensors",
        "text_encoder": "gemma_3_12B_it.safetensors",
        "joint_av":     False,
        "always_on_loras": [
            # Distill LoRA lives at the root of loras/ in the canonical
            # comfyui-aeon-spark download layout (no ltx2/ subdirectory).
            ("ltx-2.3-22b-distilled-lora-384.safetensors", 0.5),
            ("ltx-2.3-22b-ic-lora-union-control-ref0.5.safetensors", 0.7),
            (f"ltx2{_SEP}Ltx2.3-Licon-VBVR-I2V-96000-R32.safetensors", 0.7),
        ],
    },
    "abstract": {
        # For fractals, geometry, artwork-in-motion, psychedelic visuals.
        # Drops VBVR (physics constraints hurt abstract content) and IC-LoRA union
        # control (no real-world reference semantics). Uses euler_ancestral for
        # more variation per step (non-physical morphing), higher CFG + more steps
        # for tighter prompt adherence on unfamiliar content.
        "checkpoint":   "ltx-2.3-22b-distilled-fp8.safetensors",
        "video_vae":    "LTX23_video_vae_bf16.safetensors",
        "text_encoder": "gemma_3_12B_it.safetensors",
        "joint_av":     False,
        "always_on_loras": [],  # pure: no physics, no reference control
        "default_cfg":    5.0,
        "default_steps":  30,
        "default_sampler": "euler_ancestral",
    },
}

DEFAULT_MODE = "fast"

# Back-compat shims — old callers used these constants directly
DEFAULT_MODELS = {k: MODES[DEFAULT_MODE][k] for k in ("checkpoint", "video_vae", "text_encoder")}
ALWAYS_ON_LORAS = MODES[DEFAULT_MODE]["always_on_loras"]


def _override_lora_strength(loras_list, lora_filename_substr, new_strength):
    """Return a new list with the strength rewritten for any LoRA whose path
    contains the given case-insensitive substring. No-op if `new_strength` is None
    or no entry matches."""
    if new_strength is None:
        return loras_list
    needle = lora_filename_substr.lower()
    out = []
    for path, strength in loras_list:
        if needle in path.lower():
            out.append((path, float(new_strength)))
        else:
            out.append((path, strength))
    return out


def apply_cli_lora_overrides(args):
    """If the user passed --vbvr-strength or --ic-lora-strength, mutate the
    relevant MODES[*]['always_on_loras'] in place so all downstream renders
    pick up the new strength. Idempotent — safe to call once per main()."""
    vbvr = getattr(args, "vbvr_strength", None)
    iclo = getattr(args, "ic_lora_strength", None)
    if vbvr is None and iclo is None:
        return
    for mode_name, cfg in MODES.items():
        new = cfg["always_on_loras"]
        new = _override_lora_strength(new, "vbvr", vbvr)
        new = _override_lora_strength(new, "ic-lora-union", iclo)
        cfg["always_on_loras"] = new
    # Refresh module-level constant too
    global ALWAYS_ON_LORAS
    ALWAYS_ON_LORAS = MODES[DEFAULT_MODE]["always_on_loras"]

# Per-scene LoRAs — selected by screenplay tags on the scene or dialogue.
# `tag` match is case-insensitive substring against the scene's tag list
# (see `select_loras` for details).
SCENE_LORAS = {
    # tag                           :  (path,                                                   strength)
    "pose":                           (f"ltx2{_SEP}ltx23__demopose_d3m0p0s3.safetensors",        1.0),
    "zoomout":                        (f"ltx2{_SEP}ltx23_zoomout_z00m047.safetensors",           0.9),
    "camera: dolly-left":             ("ltx-2-19b-lora-camera-control-dolly-left.safetensors",   0.8),
    "camera: jib-down":               (f"ltx2{_SEP}ltx-2-19b-lora-camera-control-jib-down.safetensors", 0.8),
    "transition":                     ("ltx2.3-transition.safetensors",                          1.0),
    "style: claymation":              (f"ltx2{_SEP}Claymation.safetensors",                      0.8),
    "style: ghibli":                  ("StudioGhibli.Redmond-StdGBRRedmAF-StudioGhibli.safetensors", 0.7),
    "style: ghibli_offset":           ("ghibli_style_offset.safetensors",                        0.6),
    "style: galaxy":                  (f"ltx2{_SEP}LTX23-GalaxyAce.safetensors",                 0.9),
    "style: tribal":                  ("Smooth_Tribal.safetensors",                              0.7),
    "style: illustration":            ("Illustration concept Variant 3A.safetensors",            0.7),
    "style: cyberpunk":               ("CyberPunkAI.safetensors",                                0.8),
    "character: talkinghead":         ("ltx-2.3-id-lora-talkvid-3k.safetensors",                 0.8),
}

# 7-second max enforced; LTX 2.3 coherence degrades noticeably past ~8 s
MAX_CLIP_SECONDS = 7.0
DEFAULT_FPS = 24   # LTX native; set 25 for film, 30 for broadcast
# LTX likes width/height divisible by 32 and resolutions close to its training set
DEFAULT_WIDTH = 832
DEFAULT_HEIGHT = 480
DEFAULT_STEPS = 24       # distilled checkpoint converges fast
DEFAULT_CFG = 3.0        # LTX distilled prefers low CFG
DEFAULT_NEGATIVE = (
    "ugly, deformed, bad anatomy, extra limbs, extra fingers, morphing, "
    "blurry, low quality, watermark, subtitles, text, cartoon, jpeg artifacts"
)


# ============================================================================
# ComfyUI client (with transient-retry)
# ============================================================================

def comfy_request(path, data=None, timeout=30):
    url = f"{COMFYUI_URL}{path}"
    if data is not None:
        req = urllib.request.Request(url, data=json.dumps(data).encode(),
            headers={"Content-Type": "application/json"}, method="POST")
    else:
        req = urllib.request.Request(url)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def comfy_fetch_view(filename, subfolder="", file_type="output", timeout=120):
    """Download a ComfyUI output via its /view endpoint and return the bytes.

    Used as a fallback when the script can't locate the file on a shared
    filesystem (e.g. running in a container without COMFYUI_ROOT pointed at
    the right place, or running over pure HTTP from a separate host with no
    NFS / bind mount to ComfyUI's output dir). Works with any deployment
    topology since it's just an HTTP GET against the ComfyUI API.
    """
    qs = urllib.parse.urlencode({
        "filename": filename, "subfolder": subfolder, "type": file_type,
    })
    url = f"{COMFYUI_URL}/view?{qs}"
    with urllib.request.urlopen(url, timeout=timeout) as r:
        return r.read()


def comfy_upload_image(local_path, target_subfolder="_movie_fast_frames",
                       overwrite=True, timeout=60):
    """Upload a local image to ComfyUI's input/ via /upload/image.

    Returns the filename ComfyUI assigned (suitable for LoadImage's `image`
    field). Eliminates the COMFYUI_ROOT-detection problem when the script
    runs anywhere ComfyUI's filesystem isn't directly visible (separate host,
    container without bind mount, etc.).

    Returns the relative path that LoadImage expects: 'subfolder/filename.png'
    when a subfolder is set, or just 'filename.png' for the input root.
    """
    fn = os.path.basename(local_path)
    with open(local_path, "rb") as f:
        body = f.read()
    boundary = "----movieFastBoundary" + str(int(time.time() * 1000))

    def _part(name, value, content_type=None, filename=None):
        h = f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"'
        if filename is not None:
            h += f'; filename="{filename}"'
        h += "\r\n"
        if content_type:
            h += f"Content-Type: {content_type}\r\n"
        h += "\r\n"
        return h.encode("utf-8") + (value if isinstance(value, bytes) else str(value).encode("utf-8")) + b"\r\n"

    payload = b""
    payload += _part("image", body, content_type="image/png", filename=fn)
    payload += _part("type", "input")
    payload += _part("subfolder", target_subfolder)
    payload += _part("overwrite", "true" if overwrite else "false")
    payload += f"--{boundary}--\r\n".encode("utf-8")

    req = urllib.request.Request(
        f"{COMFYUI_URL}/upload/image",
        data=payload,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        resp = json.loads(r.read())
    # Response shape: {"name": "<saved_fn>", "subfolder": "<sf>", "type": "input"}
    saved_name = resp.get("name", fn)
    saved_sub  = resp.get("subfolder", target_subfolder)
    return f"{saved_sub}/{saved_name}" if saved_sub else saved_name


SUBMIT_RETRY_DELAYS_S = (2, 5, 10)


def _submit_prompt(wf, client_id):
    """Submit with bounded retries on transient HTTP errors (same pattern as music_maker)."""
    delays = list(SUBMIT_RETRY_DELAYS_S)
    last_exc = None
    for i in range(len(delays) + 1):
        try:
            res = comfy_request("/prompt", {"prompt": wf, "client_id": client_id})
            node_errors = res.get("node_errors") or {}
            if node_errors:
                raise RuntimeError(f"ComfyUI rejected workflow: {list(node_errors)[:3]}")
            pid = res.get("prompt_id")
            if not pid:
                raise RuntimeError(f"Submit succeeded but no prompt_id: {res}")
            if i > 0:
                print(f"    submit succeeded after {i} retr{'y' if i == 1 else 'ies'}")
            return pid
        except urllib.error.HTTPError as e:
            last_exc = e
            if e.code in (404, 413):
                raise
            if i < len(delays):
                body = e.read().decode("utf-8", "replace")[:200] if hasattr(e, "read") else ""
                print(f"    submit HTTP {e.code} — retrying in {delays[i]}s… {body}")
                time.sleep(delays[i])
            else:
                raise
        except (urllib.error.URLError, ConnectionError, TimeoutError) as e:
            last_exc = e
            if i < len(delays):
                print(f"    submit connection error ({e}) — retrying in {delays[i]}s…")
                time.sleep(delays[i])
            else:
                raise
    raise RuntimeError(f"submit_prompt exhausted retries: {last_exc}")


def submit_and_wait(wf, client_id, poll_timeout=1200, poll_every=3):
    pid = _submit_prompt(wf, client_id)
    start = time.time()
    while time.time() - start < poll_timeout:
        h = comfy_request(f"/history/{pid}")
        if pid in h:
            return h[pid], pid
        time.sleep(poll_every)
    raise TimeoutError(f"{pid} timed out after {poll_timeout}s")


# ============================================================================
# LoRA router — map screenplay tags → LoRA stack
# ============================================================================

def select_loras(tags):
    """Pick per-scene LoRAs from a list of tags.

    Tags are free-text, matched case-insensitively. Always-on LoRAs are
    unconditionally applied; scene LoRAs are additive (cap ~3 to avoid
    model interference).
    """
    picks = list(ALWAYS_ON_LORAS)
    tags_lower = [t.lower().strip() for t in (tags or []) if t]

    # Match first N matches, cap at 3 additional for stability
    extras = []
    for pattern, (path, strength) in SCENE_LORAS.items():
        if any(pattern in t for t in tags_lower):
            extras.append((path, strength))
    extras = extras[:3]
    picks.extend(extras)
    return picks


# ============================================================================
# Workflow builder — LTX 2.3 I2V via node-ID JSON
# ============================================================================

def build_ltx_i2v_workflow(
    image_path, prompt, filename_prefix,
    negative_prompt=DEFAULT_NEGATIVE,
    duration_s=7.0, fps=DEFAULT_FPS,
    width=DEFAULT_WIDTH, height=DEFAULT_HEIGHT,
    steps=DEFAULT_STEPS, cfg=DEFAULT_CFG, seed=None,
    loras=None,
    models=None,
    mode=DEFAULT_MODE,
    scheduler_name="linear_quadratic",
    sampler_name="euler",
    persistence=None,
    t2v=False,
    # --- A2V (audio-to-video) ---
    # When audio_reference is set AND a joint_av MODES entry exists, LoadAudio +
    # LTXVReferenceAudio are wired into the workflow so audio conditions video
    # generation. No currently-shipped MODES entry sets joint_av=True; this
    # parameter is preserved for forward-compat with future audio-capable
    # checkpoints. Today, --audio-reference is a no-op with a warning.
    audio_reference=None,
    audio_guidance_scale=0.5,
    audio_start_percent=0.0,
    audio_end_percent=1.0,
):
    """Assemble the LTX 2.3 I2V workflow as a ComfyUI API-format dict.

    Mirrors the stage-2-alone pattern from a known-good community LTX 2.3
    workflow. The joint-AV branches (LTXVAudioVAELoader, LTXVConcatAVLatent,
    LTXVSeparateAVLatent) are dormant unless a future MODES entry sets
    joint_av=True. Today the workflow is video-only; audio is muxed in at
    stitch time from the separate audio stack (Qwen3-TTS / ACE-Step / MMAudio).

    Signal flow (node IDs as strings — ComfyUI API format):
       [10] CheckpointLoader  → MODEL0, CLIP0, VAE0 (ignored — we load all three fresh)
       [11] VAELoader(video)  → VAE
       [12] LTXAVTextEncoderLoader(gemma_3_12B_it, ltx-2.3-22b-*-fp8) → CLIP
       [20..] LoraLoaderModelOnly chain on MODEL0 → MODEL
       [30] CLIPTextEncode(positive) → COND_POS
       [31] CLIPTextEncode(negative) → COND_NEG
       [32] LTXVConditioning(pos, neg, fps)  → LTX_POS, LTX_NEG

       [40] LoadImage → IMAGE
       [41] EmptyLTXVLatentVideo(w, h, length, 1) → EMPTY_V_LATENT
       [42] LTXVImgToVideoInplace(vae, image, empty_v_latent, strength=1, bypass=False) → V_LATENT_W_IMG
       [43] LTXVEmptyLatentAudio(length, fps, 1) → A_LATENT
       [44] LTXVConcatAVLatent(V_LATENT_W_IMG, A_LATENT) → AV_LATENT

       [50] RandomNoise(seed) → NOISE
       [51] KSamplerSelect('euler') → SAMPLER
       [52] BasicScheduler(MODEL, 'beta57', steps, 1.0) → SIGMAS
       [53] CFGGuider(MODEL, LTX_POS, LTX_NEG, cfg) → GUIDER
       [54] SamplerCustomAdvanced(noise, guider, sampler, sigmas, AV_LATENT) → SAMPLED_LATENT

       [60] LTXVSeparateAVLatent(sampled) → V_LATENT, A_LATENT (we drop audio here)
       [61] LTXVSpatioTemporalTiledVAEDecode(vae, V_LATENT, 4, 4, 16, 4, False, auto, auto) → IMAGES
       [70] CreateVideo(images, fps) → VIDEO
       [71] SaveVideo(video, prefix, 'mp4', 'h264') → file on disk
    """
    if mode not in MODES:
        raise ValueError(f"Unknown mode '{mode}'. Choices: {list(MODES)}")
    # A2V (audio-conditioned video) requires a joint-AV checkpoint. No currently
    # shipped MODES entry sets joint_av=True — the EROS model that previously
    # supplied this capability is not part of the canonical asset set. If a
    # caller still passes --audio-reference, ignore it with a clear warning
    # rather than silently producing broken workflows. The downstream joint_av
    # branches remain in place so re-enabling is a single MODES edit away.
    if audio_reference is not None and not MODES[mode]["joint_av"]:
        print(f"  [warn] --audio-reference requires a joint-AV checkpoint; "
              f"none configured in MODES. Ignoring audio reference and "
              f"rendering video-only.", file=sys.stderr)
        audio_reference = None
    mode_cfg = MODES[mode]
    models = {**{k: mode_cfg[k] for k in ("checkpoint", "video_vae", "text_encoder")},
              **(models or {})}
    joint_av = mode_cfg["joint_av"]
    if loras is None:
        loras = mode_cfg["always_on_loras"]

    if seed is None:
        seed = random.randint(0, 2**31 - 1)
    duration_s = min(MAX_CLIP_SECONDS, max(1.0, float(duration_s)))
    # LTX expects frame counts of (n*8 + 1). Compute closest valid at or below target.
    target_frames = int(round(duration_s * fps))
    frame_count = max(9, ((target_frames - 1) // 8) * 8 + 1)

    # --- Model stack ---
    wf = {
        "10": {"class_type": "CheckpointLoaderSimple",
               "inputs": {"ckpt_name": models["checkpoint"]}},
        "11": {"class_type": "VAELoader",
               "inputs": {"vae_name": models["video_vae"]}},
        "12": {"class_type": "LTXAVTextEncoderLoader",
               "inputs": {
                   "text_encoder": models["text_encoder"],
                   "ckpt_name": models["checkpoint"],
                   "device": "default",
               }},
    }
    # Audio VAE loader only needed in joint-AV (quality) mode
    if joint_av:
        wf["13"] = {"class_type": "LTXVAudioVAELoader",
                    "inputs": {"ckpt_name": models["checkpoint"]}}

    # --- LoRA chain on the MODEL output ---
    lora_chain_last_id = "10"
    for i, (lora_name, strength) in enumerate(loras, start=20):
        wf[str(i)] = {
            "class_type": "LoraLoaderModelOnly",
            "inputs": {
                "model": [lora_chain_last_id, 0],
                "lora_name": lora_name,
                "strength_model": float(strength),
            },
        }
        lora_chain_last_id = str(i)
    model_node = lora_chain_last_id

    # --- Text conditioning ---
    wf["30"] = {"class_type": "CLIPTextEncode",
                "inputs": {"text": prompt, "clip": ["12", 0]}}
    wf["31"] = {"class_type": "CLIPTextEncode",
                "inputs": {"text": negative_prompt, "clip": ["12", 0]}}
    wf["32"] = {"class_type": "LTXVConditioning",
                "inputs": {
                    "positive": ["30", 0],
                    "negative": ["31", 0],
                    "frame_rate": float(fps),
                }}

    # --- Image + latent prep ---
    # T2V mode: skip LoadImage + LTXVImgToVideoInplace entirely. Just use the
    # empty latent as sampler input. Motion/content comes purely from the text
    # prompt — useful for abstract / procedural / purely-generative content.
    # I2V mode: load an image, run LTXVImgToVideoInplace to bake image conditioning
    # into the latent, then sampler continues from there.
    wf["41"] = {"class_type": "EmptyLTXVLatentVideo",
                "inputs": {
                    "width": int(width), "height": int(height),
                    "length": int(frame_count), "batch_size": 1,
                }}
    if not t2v:
        wf["40"] = {"class_type": "LoadImage",
                    "inputs": {"image": image_path}}
        # LTXVImgToVideoInplace `strength` is the I2V conditioning strength.
        # Paradoxically, HIGHER strength → less preservation of input; LOWER →
        # more persistence. Expose an intuitive 0..1 `persistence` value and
        # invert it for the node.
        if persistence is None:
            i2v_strength = 1.0
        else:
            i2v_strength = max(0.1, min(1.0, 1.0 - float(persistence) * 0.6))
        wf["42"] = {"class_type": "LTXVImgToVideoInplace",
                    "inputs": {
                        "vae": ["11", 0],
                        "image": ["40", 0],
                        "latent": ["41", 0],
                        "strength": i2v_strength,
                        "bypass": False,
                    }}
    # Video latent source: T2V uses empty latent directly (no image conditioning),
    # I2V uses the LTXVImgToVideoInplace output with image baked in.
    video_latent_for_sampler = ["41", 0] if t2v else ["42", 0]

    # Joint-AV mode (quality only): add empty audio latent + concat video+audio
    if joint_av:
        wf["43"] = {"class_type": "LTXVEmptyLatentAudio",
                    "inputs": {
                        "frames_number": int(frame_count),
                        "frame_rate": float(fps),
                        "batch_size": 1,
                        "audio_vae": ["13", 0],
                    }}
        wf["44"] = {"class_type": "LTXVConcatAVLatent",
                    "inputs": {
                        "video_latent": video_latent_for_sampler,
                        "audio_latent": ["43", 0],
                    }}
        sampler_input_latent = ["44", 0]
    else:
        sampler_input_latent = video_latent_for_sampler

    # --- Advanced-sampler chain ---
    wf["50"] = {"class_type": "RandomNoise",
                "inputs": {"noise_seed": int(seed)}}
    wf["51"] = {"class_type": "KSamplerSelect",
                "inputs": {"sampler_name": sampler_name}}
    wf["52"] = {"class_type": "BasicScheduler",
                "inputs": {
                    "model": [model_node, 0],
                    "scheduler": scheduler_name,
                    "steps": int(steps),
                    "denoise": 1.0,
                }}
    # --- A2V conditioning chain (optional) ---
    # If audio_reference provided: feed LoadAudio → LTXVReferenceAudio which
    # wraps the MODEL and updates CONDITIONING with audio-derived guidance.
    # Downstream CFGGuider then uses the audio-aware model + conds.
    if audio_reference is not None:
        # Strip any path prefix — LoadAudio expects a bare filename from input/
        audio_filename = os.path.basename(audio_reference) if audio_reference else ""
        wf["55"] = {"class_type": "LoadAudio",
                    "inputs": {"audio": audio_filename}}
        # LTXVReferenceAudio takes the LoRA'd model + LTX-conditioning outputs
        # from [32], plus the audio + audio_vae, plus guidance params.
        # Output: (wrapped MODEL, new POS cond, new NEG cond).
        wf["56"] = {"class_type": "LTXVReferenceAudio",
                    "inputs": {
                        "model": [model_node, 0],
                        "positive": ["32", 0],
                        "negative": ["32", 1],
                        "reference_audio": ["55", 0],
                        "audio_vae": ["13", 0],
                        "identity_guidance_scale": float(audio_guidance_scale),
                        "start_percent": float(audio_start_percent),
                        "end_percent": float(audio_end_percent),
                    }}
        # After A2V wrapping, model+conds come from node 56 instead of the
        # plain LoRA chain + LTXVConditioning outputs.
        guider_model_ref  = ["56", 0]
        guider_positive   = ["56", 1]
        guider_negative   = ["56", 2]
    else:
        guider_model_ref  = [model_node, 0]
        guider_positive   = ["32", 0]
        guider_negative   = ["32", 1]

    wf["53"] = {"class_type": "CFGGuider",
                "inputs": {
                    "model": guider_model_ref,
                    "positive": guider_positive,
                    "negative": guider_negative,
                    "cfg": float(cfg),
                }}
    wf["54"] = {"class_type": "SamplerCustomAdvanced",
                "inputs": {
                    "noise": ["50", 0],
                    "guider": ["53", 0],
                    "sampler": ["51", 0],
                    "sigmas": ["52", 0],
                    "latent_image": sampler_input_latent,
                }}

    # --- Decode: joint AV needs separator, fast mode goes direct ---
    if joint_av:
        wf["60"] = {"class_type": "LTXVSeparateAVLatent",
                    "inputs": {"av_latent": ["54", 0]}}
        video_latent_src = ["60", 0]
    else:
        video_latent_src = ["54", 0]
    # Tiled decode — auto-tune tile count by resolution. For 480p/720p we don't
    # need the 4×4 spatial tiling the VBVR_EROS workflow uses for 1536×... — that
    # setting was tuned for larger frames and costs ~30% speed on sub-1024 resolutions.
    max_dim = max(width, height)
    if max_dim <= 768:
        spatial_tiles = 2
    elif max_dim <= 1024:
        spatial_tiles = 3
    else:
        spatial_tiles = 4
    wf["61"] = {"class_type": "LTXVSpatioTemporalTiledVAEDecode",
                "inputs": {
                    "vae": ["11", 0],
                    "latents": video_latent_src,
                    "spatial_tiles": spatial_tiles,
                    "spatial_overlap": 4,
                    "temporal_tile_length": 16,
                    "temporal_overlap": 4,
                    "last_frame_fix": False,
                    "working_device": "auto",
                    "working_dtype": "auto",
                }}

    # --- Assemble + save ---
    wf["70"] = {"class_type": "CreateVideo",
                "inputs": {"images": ["61", 0], "fps": float(fps)}}
    wf["71"] = {"class_type": "SaveVideo",
                "inputs": {
                    "video": ["70", 0],
                    "filename_prefix": filename_prefix,
                    "format": "mp4",
                    "codec": "h264",
                }}
    return wf, seed


# ============================================================================
# Phase 1b — LTX 2.3 Prompt Relay (timeline of prompts → continuous joint A/V)
# ============================================================================
#
# Mirrors comfyui-aeon-spark workflow `10_ltx2.3_prompt_relay.json`. Builds a
# single LTX 2.3 forward pass that morphs through a TIMELINE of prompts inside
# one render — versus the sequential-clip approach in build_ltx_i2v_workflow
# which renders each scene separately and stitches.
#
# Headline node: `PromptRelayEncodeTimeline` (custom node from the AEON-Spark
# `ComfyUI-PromptRelay` pack). It takes a list of (prompt, length_in_frames)
# segments + a global "wrapper" anchor prompt, and outputs ONE positive
# conditioning that drives the model differently across the timeline.
#
# Why this matters for screenplay:
#   - Smooth morphing between scenes within the same shot/sequence (vs hard
#     cuts you'd get from stitching separate clips together).
#   - One shared internal context across the whole timeline → motion and
#     character consistency are model-native, not post-hoc.
#   - Joint A/V output: same render produces the audio track via
#     LTXVAudioVAEDecode + LTXVConcatAVLatent + LTXVSeparateAVLatent. Opens
#     the door to actual lipsync (vs current stitch-time audio mux).
#
# Constraints:
#   - Single seed image for the whole pass (LTXVImgToVideoInplaceKJ takes one
#     image_1). Character/location changes within a sequence morph from that
#     anchor — works for "same character, varied actions"; for hard cuts to a
#     different scene, build a new sequence with a new seed image.
#   - Frame budget per pass is bounded by VRAM. Validated default is 489 frames
#     @ 640×640 = ~20s @ 24 fps on Spark (matches the canonical example
#     workflow). For longer films, chunk into multiple sequences and stitch.
#   - Different model body than build_ltx_i2v_workflow:
#     * UNET: ltx-2.3-22b-distilled-1.1_transformer_only_fp8_scaled (transformer-only fp8)
#     * Optional LoRA: ltxv/ltx2/ltx-2.3-22b-distilled-lora-384-1.1 @ 0.5
#       (bypassed in canonical example; expose as a flag, off by default)
#     * DualCLIP: gemma_3_12B_it + ltx-2.3_text_projection_bf16 (loader type "ltxv")
#     * Video VAE: LTX23_video_vae_bf16
#     * Audio VAE: LTX23_audio_vae_bf16  (REQUIRED — joint A/V is structural here)
#
# Signal flow (API-format node IDs as strings):
#   [100] UNETLoader → MODEL0
#   [101] (opt) LoraLoaderModelOnly(MODEL0) → MODEL1
#   [102] PathchSageAttentionKJ(MODEL1) → MODEL2
#   [103] DualCLIPLoader → CLIP
#   [104] VAELoader(video) → VIDEO_VAE
#   [105] LTXVAudioVAELoader → AUDIO_VAE
#
#   [110] EmptyLTXVLatentVideo(w, h, total_frames, 1) → EMPTY_V_LATENT
#   [111] LoadImage(seed_image) → IMAGE  (or skipped for T2V)
#   [112] LTXVPreprocess(image, 30) → IMAGE_PRE
#   [113] LTXVImgToVideoInplaceKJ(VIDEO_VAE, EMPTY_V_LATENT, IMAGE_PRE) → V_LATENT_W_IMG
#   [114] LTXVEmptyLatentAudio(AUDIO_VAE, total_frames, 25) → A_LATENT
#   [115] LTXVConcatAVLatent(V_LATENT_W_IMG, A_LATENT) → AV_LATENT
#
#   [120] PromptRelayEncodeTimeline(MODEL2, CLIP, EMPTY_V_LATENT, total_frames,
#                                   wrapper, segments_json, ...) → MODEL3, POS
#   [121] ConditioningZeroOut(POS) → NEG
#   [122] LTXVConditioning(POS, NEG, fps) → POS_LTX, NEG_LTX
#
#   [130] KSamplerSelect(euler_ancestral) → SAMPLER
#   [131] BasicScheduler(MODEL3, linear_quadratic, steps, 1.0) → SIGMAS
#   [132] SamplerCustom(MODEL3, POS_LTX, NEG_LTX, SAMPLER, SIGMAS, AV_LATENT,
#                       add_noise=True, seed, control_after_generate, cfg=1)
#                       → AV_SAMPLED
#
#   [140] LTXVSeparateAVLatent(AV_SAMPLED) → V_LATENT, A_LATENT
#   [141] VAEDecode(V_LATENT, VIDEO_VAE) → IMAGES
#   [142] LTXVAudioVAEDecode(A_LATENT, AUDIO_VAE) → AUDIO
#   [143] VHS_VideoCombine(IMAGES, fps, AUDIO) → file on disk

PROMPT_RELAY_DEFAULTS = {
    "unet":       "ltx-2.3-22b-distilled-1.1_transformer_only_fp8_scaled.safetensors",
    "video_vae":  "LTX23_video_vae_bf16.safetensors",
    "audio_vae":  "LTX23_audio_vae_bf16.safetensors",
    "clip_a":     "gemma_3_12B_it.safetensors",
    "clip_b":     "ltx-2.3_text_projection_bf16.safetensors",
    "clip_type":  "ltxv",
    "lora":       f"ltxv{_SEP}ltx2{_SEP}ltx-2.3-22b-distilled-lora-384-1.1.safetensors",
}

# Hard ceiling per single Prompt Relay forward pass on Spark.
# The canonical example workflow uses 489 frames @ 640×640. Bumping this
# requires a re-validation pass — too high will OOM or produce visible
# degradation past the model's effective receptive field.
MAX_RELAY_FRAMES = 489

# ComfyUI cosmetic — segment colors for the timeline visualization in UI.
# Cycles deterministically so re-renders of the same timeline look the same.
_RELAY_SEGMENT_COLORS = [
    "#4f8edc", "#e07b3a", "#5cb464", "#c5599e",
    "#d4af37", "#7a5cc8", "#3aaab8", "#d96360",
]


def _frames_from_duration(duration_s, fps):
    """LTX expects per-segment frame counts of (n*8 + 1). Compute closest valid
    at or below the requested duration. Minimum 9 frames (~0.4s @ 24fps)."""
    target = int(round(float(duration_s) * float(fps)))
    return max(9, ((target - 1) // 8) * 8 + 1)


def build_ltx_prompt_relay_workflow(
    timeline,                    # list of {"prompt": str, "duration_s": float, "color"?: str}
    *,
    wrapper_prompt,              # global anchor prompt (e.g. screenplay style + setting)
    seed_image_path=None,        # filename relative to ComfyUI's input/ dir; None → T2V w/ blank latent
    fps=DEFAULT_FPS,
    width=640, height=640,       # Prompt Relay is square-friendly; 832×480 also tested
    steps=8, cfg=1.0,            # canonical example uses 8 steps + CFG 1 (sampler add_noise=True)
    seed=None,
    sampler_name="euler_ancestral",
    scheduler_name="linear_quadratic",
    use_lora=False,              # canonical example bypasses the distill-1.1 LoRA; opt-in
    lora_strength=0.5,
    sage_attention=True,
    save_audio=True,             # if False, drop audio from VHS_VideoCombine output
    filename_prefix=None,
    models=None,                 # override any of PROMPT_RELAY_DEFAULTS
):
    """Assemble the LTX 2.3 Prompt Relay workflow as a ComfyUI API-format dict.

    Returns: (wf_dict, seed_used, total_frames)

    `timeline` is a list of dicts with `prompt` (str) and `duration_s` (float).
    Each dict may optionally carry a `color` (hex string for UI) and a
    `frames` int (overrides duration_s — useful when caller wants exact frame
    alignment).

    Total frame count = sum of per-segment frames. Refuses if total > MAX_RELAY_FRAMES.
    """
    if not timeline:
        raise ValueError("Prompt Relay requires at least one segment in timeline")

    models = {**PROMPT_RELAY_DEFAULTS, **(models or {})}

    if seed is None:
        seed = random.randint(0, 2**31 - 1)

    # Compute per-segment frame counts + total
    segments_for_node = []
    seg_lengths = []
    for i, seg in enumerate(timeline):
        if "prompt" not in seg or not seg["prompt"]:
            raise ValueError(f"timeline[{i}] missing 'prompt'")
        if "frames" in seg:
            n_frames = max(9, int(seg["frames"]))
        elif "duration_s" in seg:
            n_frames = _frames_from_duration(seg["duration_s"], fps)
        else:
            raise ValueError(f"timeline[{i}] needs 'duration_s' or 'frames'")
        seg_lengths.append(n_frames)
        segments_for_node.append({
            "prompt": seg["prompt"],
            "length": n_frames,
            "color":  seg.get("color") or _RELAY_SEGMENT_COLORS[i % len(_RELAY_SEGMENT_COLORS)],
        })

    total_frames = sum(seg_lengths)
    if total_frames > MAX_RELAY_FRAMES:
        raise ValueError(
            f"Prompt Relay timeline totals {total_frames} frames; max per pass "
            f"is {MAX_RELAY_FRAMES}. Split into multiple sequences."
        )

    if filename_prefix is None:
        filename_prefix = f"movie_fast/relay_{seed}"

    # Build the structured + legacy-pipe formats that PromptRelayEncodeTimeline
    # accepts. The node honors widget[2] (JSON segments) primarily; widget[3]
    # (pipe-separated) and widget[4] (frame-count CSV) are kept for
    # backward-compat with older versions of the custom node.
    segments_json   = json.dumps({"segments": segments_for_node}, ensure_ascii=False)
    pipe_prompts    = " | ".join(s["prompt"] for s in segments_for_node)
    pipe_frame_csv  = ", ".join(str(n) for n in seg_lengths)

    wf = {
        # ── Model + encoders ───────────────────────────────────────────────
        "100": {"class_type": "UNETLoader",
                "inputs": {
                    "unet_name": models["unet"],
                    "weight_dtype": "default",
                }},
        "103": {"class_type": "DualCLIPLoader",
                "inputs": {
                    "clip_name1": models["clip_a"],
                    "clip_name2": models["clip_b"],
                    "type": models["clip_type"],
                    "device": "default",
                }},
        # VAELoaderKJ (KJ-namespace) loads a standalone .safetensors VAE
        # rather than extracting from a checkpoint. This is what the canonical
        # prompt-relay workflow uses for both video and audio VAEs — they're
        # required because the transformer-only UNet (`*_transformer_only_fp8_scaled`)
        # has neither VAE baked in. Plain VAELoader would fail with the wrong
        # internal shape on the audio side.
        "104": {"class_type": "VAELoaderKJ",
                "inputs": {"vae_name": models["video_vae"],
                           "device": "main_device", "weight_dtype": "bf16"}},
        "105": {"class_type": "VAELoaderKJ",
                "inputs": {"vae_name": models["audio_vae"],
                           "device": "main_device", "weight_dtype": "bf16"}},
    }

    # Optional LoRA (off by default — canonical workflow bypasses it)
    if use_lora:
        wf["101"] = {"class_type": "LoraLoaderModelOnly",
                     "inputs": {
                         "model": ["100", 0],
                         "lora_name": models["lora"],
                         "strength_model": float(lora_strength),
                     }}
        model_after_lora = "101"
    else:
        model_after_lora = "100"

    # Optional Sage Attention patch (canonical workflow has it on).
    # Input names per ComfyUI object_info: model + sage_attention (enum).
    # `allow_compile` is optional (default False); leaving unset.
    if sage_attention:
        wf["102"] = {"class_type": "PathchSageAttentionKJ",
                     "inputs": {
                         "model": [model_after_lora, 0],
                         "sage_attention": "auto",
                     }}
        model_for_relay = "102"
    else:
        model_for_relay = model_after_lora

    # ── Latent prep (video + audio + concat) ───────────────────────────────
    wf["110"] = {"class_type": "EmptyLTXVLatentVideo",
                 "inputs": {
                     "width": int(width), "height": int(height),
                     "length": int(total_frames), "batch_size": 1,
                 }}

    if seed_image_path:
        wf["111"] = {"class_type": "LoadImage",
                     "inputs": {"image": seed_image_path}}
        # LTXVPreprocess input is `img_compression` (INT, default 35)
        wf["112"] = {"class_type": "LTXVPreprocess",
                     "inputs": {"image": ["111", 0], "img_compression": 30}}
        # LTXVImgToVideoInplaceKJ uses a dynamic combo for `num_images` — when
        # set to "1", the node materializes additional inputs that ComfyUI
        # references with a DOT-NAMESPACED prefix: `num_images.strength_1`,
        # `num_images.image_1`, `num_images.index_1`. (Visible in the validator's
        # `extra_info.input_name` field on rejection.) Sending bare `strength_1`
        # etc. fails with "Required input is missing: strength_1" even though
        # the value IS in the payload — the validator looks up the namespaced key.
        wf["113"] = {"class_type": "LTXVImgToVideoInplaceKJ",
                     "inputs": {
                         "vae": ["104", 0],
                         "latent": ["110", 0],
                         "num_images": "1",
                         "num_images.strength_1": 1.0,
                         "num_images.image_1": ["112", 0],
                         "num_images.index_1": 0,
                     }}
        video_latent_for_concat = ["113", 0]
    else:
        # T2V: skip image conditioning, feed empty latent straight into the concat
        video_latent_for_concat = ["110", 0]

    wf["114"] = {"class_type": "LTXVEmptyLatentAudio",
                 "inputs": {
                     "frames_number": int(total_frames),
                     "frame_rate": 25,  # audio frame rate fixed to LTX's 25 Hz codec
                     "batch_size": 1,
                     "audio_vae": ["105", 0],
                 }}
    wf["115"] = {"class_type": "LTXVConcatAVLatent",
                 "inputs": {
                     "video_latent": video_latent_for_concat,
                     "audio_latent": ["114", 0],
                 }}

    # ── Prompt Relay timeline encoding ─────────────────────────────────────
    # Per ComfyUI object_info, the actual input names are:
    #   global_prompt    — wrapper anchor
    #   max_frames       — total timeline length
    #   timeline_data    — JSON state of the timeline editor (auto-managed)
    #   local_prompts    — pipe-separated per-segment prompts (UI-populated)
    #   segment_lengths  — comma-separated frame counts (UI-populated)
    #   epsilon          — smoothing/penalty decay (low = sharp boundaries)
    #   fps (optional)   — display-only; doesn't change generation
    wf["120"] = {"class_type": "PromptRelayEncodeTimeline",
                 "inputs": {
                     "model": [model_for_relay, 0],
                     "clip": ["103", 0],
                     "latent": ["110", 0],
                     "global_prompt": wrapper_prompt,
                     "max_frames": int(total_frames),
                     "timeline_data": segments_json,
                     "local_prompts": pipe_prompts,
                     "segment_lengths": pipe_frame_csv,
                     "epsilon": 0.001,
                     "fps": float(fps),
                     "time_units": "frames",
                 }}

    # ConditioningZeroOut on the positive gives a true-zero negative conditioning
    # (canonical example does this rather than encoding a separate negative prompt
    # — matches the model's training distribution at CFG≈1).
    wf["121"] = {"class_type": "ConditioningZeroOut",
                 "inputs": {"conditioning": ["120", 1]}}
    wf["122"] = {"class_type": "LTXVConditioning",
                 "inputs": {
                     "positive": ["120", 1],
                     "negative": ["121", 0],
                     "frame_rate": float(fps),
                 }}

    # ── Sampler stack ──────────────────────────────────────────────────────
    wf["130"] = {"class_type": "KSamplerSelect",
                 "inputs": {"sampler_name": sampler_name}}
    wf["131"] = {"class_type": "BasicScheduler",
                 "inputs": {
                     "model": ["120", 0],   # use the relay-wrapped model for sigma calc
                     "scheduler": scheduler_name,
                     "steps": int(steps),
                     "denoise": 1.0,
                 }}
    # Note SamplerCustom (NOT SamplerCustomAdvanced) — matches canonical workflow.
    # `add_noise=True` + cfg=1 + low steps is the prompt-relay tuning recipe.
    wf["132"] = {"class_type": "SamplerCustom",
                 "inputs": {
                     "model": ["120", 0],
                     "positive": ["122", 0],
                     "negative": ["122", 1],
                     "sampler": ["130", 0],
                     "sigmas": ["131", 0],
                     "latent_image": ["115", 0],
                     "add_noise": True,
                     "noise_seed": int(seed),
                     "cfg": float(cfg),
                 }}

    # ── Decode + assemble ──────────────────────────────────────────────────
    # LTXVSeparateAVLatent splits the joint AV latent back into video + audio.
    # Per ComfyUI object_info: VAEDecode wants (samples, vae);
    #                         LTXVAudioVAEDecode wants (samples, audio_vae).
    wf["140"] = {"class_type": "LTXVSeparateAVLatent",
                 "inputs": {"av_latent": ["132", 0]}}
    wf["141"] = {"class_type": "VAEDecode",
                 "inputs": {"samples": ["140", 0], "vae": ["104", 0]}}
    if save_audio:
        wf["142"] = {"class_type": "LTXVAudioVAEDecode",
                     "inputs": {"samples": ["140", 1], "audio_vae": ["105", 0]}}

    # VHS_VideoCombine — required inputs per object_info: images, frame_rate,
    # loop_count, filename_prefix, format, pingpong, save_output.
    # Optional: audio (mux), meta_batch, vae.
    # Format must be one of the documented enums; "video/h264-mp4" is the
    # canonical mp4-with-h264 pick.
    combine_inputs = {
        "images": ["141", 0],
        "frame_rate": float(fps),
        "loop_count": 0,
        "filename_prefix": filename_prefix,
        "format": "video/h264-mp4",
        "pingpong": False,
        "save_output": True,
    }
    if save_audio:
        combine_inputs["audio"] = ["142", 0]
    wf["143"] = {"class_type": "VHS_VideoCombine", "inputs": combine_inputs}

    return wf, seed, total_frames


# ============================================================================
# Phase 2 — Screenplay driver
# ============================================================================

# Per-character seed offset — added to scene seed when that character is focal.
# Keeps a character's appearance stable across scenes. Treat the hash as stable
# across sessions as long as the character name is stable; for multi-episode
# series, persist a characters.json with explicit seed values to avoid churn.
def character_seed_offset(char_name, base_seed):
    """Stable offset per character. Same name + same base_seed → same visual."""
    if not char_name:
        return base_seed
    h = 0
    for c in char_name.upper():
        h = (h * 131 + ord(c)) & 0x7FFFFFFF
    return (base_seed + h) & 0x7FFFFFFF


def chunk_duration(total_s, max_s=MAX_CLIP_SECONDS):
    """Split a scene duration into ≤max_s chunks. Returns list of chunk lengths.

    Aims for chunks near max_s with the last chunk being the remainder.
    Minimum chunk 1.0 s — anything shorter gets absorbed into the prior chunk.
    """
    total_s = max(1.0, float(total_s))
    n_full = int(total_s // max_s)
    remainder = total_s - n_full * max_s
    chunks = [max_s] * n_full
    if remainder >= 1.0:
        chunks.append(remainder)
    elif remainder > 0 and chunks:
        # Absorb tiny tail into last chunk (still ≤ max_s)
        chunks[-1] = min(max_s, chunks[-1] + remainder)
    elif not chunks:
        chunks = [total_s]
    return chunks


def tags_from_scene(scene):
    """Derive LoRA-routing tags from a scene dict. Pulls from:
      - explicit `tags` field (list or comma-string)
      - `mood` / `camera` / `style` fields
      - `action` / `description` keywords (last-resort heuristic)
    """
    tags = []
    raw = scene.get("tags", [])
    if isinstance(raw, str):
        raw = [t.strip() for t in raw.split(",") if t.strip()]
    tags.extend(raw)
    for k in ("camera", "style", "mood"):
        v = scene.get(k)
        if v:
            tags.append(f"{k}: {v}" if k != "mood" else v)
    # Heuristic keyword scan on action / description
    text_blob = " ".join(str(scene.get(k, "")) for k in ("action", "description", "prompt")).lower()
    if any(w in text_blob for w in ("zoom out", "pulls back", "wide establishing")):
        tags.append("zoomout")
    if any(w in text_blob for w in ("dolly left", "slides left")):
        tags.append("camera: dolly-left")
    if "close-up" in text_blob or "talking head" in text_blob:
        tags.append("character: talkinghead")
    return tags


def focal_character(scene):
    """Best guess at the scene's focal character — drives the per-character
    seed offset. Picks the first dialogue speaker if any; else the first entry
    in scene['characters'] if present; else None."""
    for d in scene.get("dialogue", []) or []:
        c = d.get("character")
        if c and c.upper() not in ("NARRATOR", "SELF", "VOICE", "OS", "V.O."):
            return c
    chars = scene.get("characters") or []
    if chars and isinstance(chars, list):
        return chars[0]
    return None


def render_clip(image_path, prompt, duration_s, *,
                tags=None, mode=DEFAULT_MODE, character=None, base_seed=None,
                width=DEFAULT_WIDTH, height=DEFAULT_HEIGHT, fps=DEFAULT_FPS,
                steps=DEFAULT_STEPS, cfg=DEFAULT_CFG,
                persistence=None, sampler_name="euler",
                filename_prefix=None, poll_timeout=1800):
    """Render a single LTX 2.3 clip. Returns (output_path, elapsed_s, seed_used).

    Intended to be the building block for `render_scene()` / `render_screenplay()`.
    """
    if base_seed is None:
        base_seed = random.randint(0, 2**31 - 1)
    seed = character_seed_offset(character, base_seed) if character else base_seed

    mode_cfg = MODES[mode]
    picks = list(mode_cfg["always_on_loras"])
    # Mode-specific defaults for CFG, steps, sampler — abstract mode overrides
    if cfg == DEFAULT_CFG and "default_cfg" in mode_cfg:
        cfg = mode_cfg["default_cfg"]
    if steps == DEFAULT_STEPS and "default_steps" in mode_cfg:
        steps = mode_cfg["default_steps"]
    if sampler_name == "euler" and "default_sampler" in mode_cfg:
        sampler_name = mode_cfg["default_sampler"]

    tags_lower = [t.lower().strip() for t in (tags or []) if t]
    extras = []
    for pattern, (path, strength) in SCENE_LORAS.items():
        if any(pattern in t for t in tags_lower):
            extras.append((path, strength))
    picks.extend(extras[:3])

    prefix = filename_prefix or f"movie_fast/clip_{seed}"
    wf, _ = build_ltx_i2v_workflow(
        image_path=image_path, prompt=prompt, filename_prefix=prefix,
        duration_s=duration_s, fps=fps,
        width=width, height=height,
        steps=steps, cfg=cfg, seed=seed,
        loras=picks, mode=mode,
        persistence=persistence, sampler_name=sampler_name,
    )
    t0 = time.time()
    result, pid = submit_and_wait(wf, f"mmfast-{seed}", poll_timeout=poll_timeout)
    elapsed = time.time() - t0
    status = result.get("status", {}).get("status_str")
    if status != "success":
        msgs = result.get("status", {}).get("messages", [])
        raise RuntimeError(f"LTX render failed ({status}): {str(msgs[-3:])[:500]}")

    for v in result.get("outputs", {}).values():
        for key in ("videos", "gifs", "images"):
            for a in v.get(key, []):
                if not isinstance(a, dict) or "filename" not in a:
                    continue
                fn = a["filename"]
                if not fn.lower().endswith((".mp4", ".webm")):
                    continue
                sub = a.get("subfolder", "")
                ftype = a.get("type", "output")
                p_cand = os.path.join(OUTPUT_ROOT, sub, fn)
                if os.path.exists(p_cand):
                    return p_cand, elapsed, seed
                # Filesystem lookup failed (likely OUTPUT_ROOT doesn't
                # match ComfyUI's actual output dir — common when running
                # from inside a container without COMFYUI_ROOT set, or via
                # SSH where ComfyUI's filesystem isn't mounted). Fall back
                # to ComfyUI's /view HTTP endpoint and stage the file
                # locally so the rest of the pipeline (last-frame extract,
                # ffprobe, etc.) sees a real path.
                try:
                    blob = comfy_fetch_view(fn, sub, ftype)
                    cache_dir = os.path.join(OUTPUT_ROOT, "_view_cache", sub)
                    os.makedirs(cache_dir, exist_ok=True)
                    p_cand = os.path.join(cache_dir, fn)
                    with open(p_cand, "wb") as f:
                        f.write(blob)
                    return p_cand, elapsed, seed
                except Exception as exc:
                    print(f"WARN: /view fallback failed for {sub}/{fn}: {exc}")
                    continue
    raise RuntimeError("No output file found in history")


def _extract_last_frame(video_path, out_png_path):
    """Extract the last frame of a video into a PNG. Used for chunk
    continuity: chunk N+1's input becomes chunk N's last frame.
    """
    os.makedirs(os.path.dirname(out_png_path), exist_ok=True)
    # Use -sseof -0.1 to seek near the end, then take the last frame via
    # -vframes 1 (after enough decoding to emit it).
    subprocess.run(
        [FFMPEG, "-y", "-sseof", "-0.3", "-i", video_path,
         "-vf", "scale=in_range=full:out_range=full", "-update", "1",
         "-frames:v", "1", "-q:v", "1", out_png_path],
        check=True, capture_output=True)


def render_scene(scene, scene_idx, project_dir, *,
                  base_seed, mode=DEFAULT_MODE,
                  width=DEFAULT_WIDTH, height=DEFAULT_HEIGHT, fps=DEFAULT_FPS,
                  steps=DEFAULT_STEPS, cfg=DEFAULT_CFG,
                  persistence=None, sampler_name="euler",
                  prompt_override=None, carry_last_frame=True):
    """Render all clips for a scene (auto-chunked to ≤7 s) and return the list.

    A scene dict should carry:
      - source_image / image_path / image : path to the input image (relative to input/)
      - prompt / action / description     : text prompt for the clip(s)
      - duration / duration_hint          : total scene length in seconds (auto-chunked)
      - tags / mood / camera / style      : routing signals for LoRAs
      - characters / dialogue             : focal-character inference for seed offsets
      - persistence                       : override the per-scene persistence (0..1)

    When `carry_last_frame=True` (default), chunk N+1's input image becomes
    chunk N's last frame — each chunk continues from where the previous left off
    instead of restarting from the scene's original source image. This is the
    single biggest lever for scene coherence across long (multi-chunk) scenes.

    Returns a list of dicts: [{clip_path, seed, duration, chunk_idx}, ...]
    """
    orig_image = (scene.get("source_image") or scene.get("image_path")
                  or scene.get("image") or scene.get("staged_image_path"))
    if not orig_image:
        raise RuntimeError(f"Scene {scene_idx} has no image path")

    prompt = (prompt_override or scene.get("prompt")
              or scene.get("action") or scene.get("description") or "")
    duration_total = float(scene.get("duration")
                           or scene.get("duration_hint") or 7.0)
    tags = tags_from_scene(scene)
    character = focal_character(scene)
    scene_persistence = persistence if persistence is not None else scene.get("persistence")

    # Directory for per-chunk last-frame PNGs used as next chunk's input
    frames_dir = os.path.join(COMFYUI_ROOT, "input", "_movie_fast_frames",
                               project_dir.replace("/", os.sep))
    os.makedirs(frames_dir, exist_ok=True)

    # Split into ≤7 s chunks. Add `transition` LoRA to all but the last chunk so
    # clip boundaries blend naturally when stitched.
    chunk_lengths = chunk_duration(duration_total, MAX_CLIP_SECONDS)
    results = []
    current_image = orig_image  # mutates across chunks when carry_last_frame=True
    for chunk_idx, chunk_dur in enumerate(chunk_lengths):
        chunk_tags = list(tags)
        is_boundary = chunk_idx < len(chunk_lengths) - 1
        if is_boundary:
            chunk_tags.append("transition")

        prefix = f"{project_dir}/scene_{scene_idx:03d}_chunk_{chunk_idx:02d}"
        carry_note = f"carry_last={chunk_idx>0 and carry_last_frame}"
        print(f"  [S{scene_idx:03d}-{chunk_idx:02d}] {chunk_dur:.1f}s "
              f"char={character or '-'}  img={os.path.basename(current_image)}  "
              f"tags={chunk_tags}  {carry_note}", flush=True)
        try:
            path, elapsed, seed = render_clip(
                image_path=current_image, prompt=prompt, duration_s=chunk_dur,
                tags=chunk_tags, mode=mode, character=character,
                # Keep the seed STABLE across chunks of the same scene — only
                # scene_idx varies. This preserves the "look" from chunk to chunk;
                # the new input image (last frame of prior chunk) provides motion
                # continuity on top.
                base_seed=base_seed + scene_idx * 1000,
                width=width, height=height, fps=fps,
                steps=steps, cfg=cfg, filename_prefix=prefix,
                persistence=scene_persistence, sampler_name=sampler_name,
            )
            print(f"      -> {path} ({elapsed:.0f}s)")
            results.append({"clip_path": path, "seed": seed,
                            "duration": chunk_dur, "chunk_idx": chunk_idx,
                            "elapsed_s": round(elapsed, 1),
                            "input_image": current_image})

            # Extract last frame for the NEXT chunk's input (if any chunks remain
            # and carry-forward is enabled).
            if carry_last_frame and chunk_idx < len(chunk_lengths) - 1:
                next_frame_rel = (f"_movie_fast_frames/{project_dir.replace('/', os.sep)}/"
                                  f"scene_{scene_idx:03d}_chunk_{chunk_idx:02d}_last.png")
                next_frame_abs = os.path.join(COMFYUI_ROOT, "input", next_frame_rel.replace("/", os.sep))
                try:
                    _extract_last_frame(path, next_frame_abs)
                    current_image = next_frame_rel.replace("\\", "/")
                    print(f"      carry: last frame -> {os.path.basename(next_frame_abs)}")
                except Exception as e:
                    print(f"      carry FAILED ({e}); next chunk falls back to original image")
                    current_image = orig_image
        except Exception as e:
            print(f"      FAILED: {e}")
    return results


def chunk_scenes_into_relay_sequences(scenes, fps, max_frames=MAX_RELAY_FRAMES):
    """Group consecutive screenplay scenes into Prompt Relay sequences.

    Each sequence becomes ONE Prompt Relay forward pass. Within a sequence,
    scenes morph smoothly via the timeline. Between sequences, there's a hard
    cut (visually — and the renderer carries the previous sequence's last
    frame as the seed image for the next sequence's relay).

    Chunking rules:
      1. Frame budget: a sequence's total frame count must stay ≤ max_frames.
         Adding the next scene that would exceed → finalize, start new.
      2. Explicit break: a scene with `relay_break: true` or any of the tags
         {'transition', 'cut', 'scene_change'} forces it to start a new sequence.
      3. Image change: when consecutive scenes have different `source_image`,
         we still keep them in the same sequence (the relay morphs through).
         A hard cut requires explicit signal per rule 2 — otherwise the
         smooth-morph property is what we WANT.

    Returns: list of sequences, each {"scenes": [...], "scene_indices": [...],
             "total_frames": int, "seed_image": str or None}.
    """
    BREAK_TAGS = {"transition", "cut", "scene_change"}
    sequences = []
    current = {"scenes": [], "scene_indices": [], "total_frames": 0, "seed_image": None}

    def _finalize():
        nonlocal current
        if current["scenes"]:
            sequences.append(current)
        current = {"scenes": [], "scene_indices": [], "total_frames": 0, "seed_image": None}

    for i, scene in enumerate(scenes):
        # Compute this scene's LTX-aligned frame count
        duration_s = float(scene.get("duration") or scene.get("duration_hint") or 4.0)
        scene_frames = _frames_from_duration(duration_s, fps)

        # If a single scene exceeds the relay frame budget, it can't fit.
        # Finalize the current sequence and put this scene alone (it'll be
        # truncated to max_frames at render time).
        if scene_frames > max_frames:
            _finalize()
            sequences.append({
                "scenes": [scene], "scene_indices": [i],
                "total_frames": max_frames,
                "seed_image": scene.get("source_image") or scene.get("image_path") or scene.get("image"),
                "_truncated_from": scene_frames,
            })
            current = {"scenes": [], "scene_indices": [], "total_frames": 0, "seed_image": None}
            continue

        explicit_break = (
            scene.get("relay_break") is True
            or any(t in BREAK_TAGS for t in (scene.get("tags") or []))
        )

        # Need-to-break check
        would_overflow = (current["total_frames"] + scene_frames) > max_frames
        if explicit_break or would_overflow:
            _finalize()

        # If this is the first scene of a (possibly new) sequence, seed image
        # comes from this scene
        if not current["scenes"]:
            current["seed_image"] = (
                scene.get("source_image") or scene.get("image_path") or scene.get("image")
            )

        current["scenes"].append(scene)
        current["scene_indices"].append(i)
        current["total_frames"] += scene_frames

    _finalize()
    return sequences


def _scene_to_relay_segment(scene, fps):
    """Convert a screenplay scene into a Prompt Relay segment dict."""
    duration_s = float(scene.get("duration") or scene.get("duration_hint") or 4.0)
    # Prefer description (camera-facing) over action (motion-only); concatenate
    # if both present for richest conditioning.
    parts = []
    for key in ("description", "action", "prompt"):
        v = scene.get(key)
        if v: parts.append(str(v).strip())
    prompt = " — ".join(parts) if parts else "continuation of previous shot"
    # Inject mood / camera / style as natural-language suffixes
    for key in ("camera", "mood", "style"):
        v = scene.get(key)
        if v: prompt = f"{prompt}, {key}: {v}"
    # Append dialogue if present (helps joint-A/V audio generation)
    dialog = scene.get("dialogue") or []
    if dialog:
        lines = []
        for d in dialog:
            speaker = d.get("character", "?")
            line = d.get("line", "")
            if line:
                lines.append(f'{speaker} says "{line}"')
        if lines:
            prompt = f"{prompt}. {' Then '.join(lines)}"
    return {"prompt": prompt, "duration_s": duration_s}


def _build_sequence_wrapper(screenplay, sequence):
    """Compose the global anchor prompt for a Prompt Relay sequence.

    Pulls screenplay-level style/setting + the union of characters appearing
    in this sequence's scenes. Falls back to a generic cinematic anchor.
    """
    bits = []
    if screenplay.get("title"):
        bits.append(f'Film "{screenplay["title"]}"')
    if screenplay.get("style"):
        bits.append(f"style: {screenplay['style']}")
    if screenplay.get("setting"):
        bits.append(f"setting: {screenplay['setting']}")
    chars = []
    for sc in sequence["scenes"]:
        for c in (sc.get("characters") or []):
            if c not in chars:
                chars.append(c)
    if chars:
        bits.append(f"characters: {', '.join(chars)}")
    bits.append("a single continuous cinematic shot, smooth motion, consistent lighting")
    return ". ".join(bits)


def render_screenplay_relay(screenplay_path, output_dir=None, *,
                            base_seed=None,
                            width=640, height=640, fps=DEFAULT_FPS,
                            steps=8, cfg=1.0,
                            sampler_name="euler_ancestral",
                            scheduler_name="linear_quadratic",
                            use_lora=False, lora_strength=0.5,
                            save_audio=True,
                            carry_last_frame=True,
                            max_frames=MAX_RELAY_FRAMES,
                            limit=None):
    """Drive a screenplay through the LTX 2.3 Prompt Relay pipeline.

    For each Prompt Relay-friendly chunk of consecutive scenes ("sequence"),
    builds ONE timeline workflow that morphs smoothly through the scene's
    prompts. Hard cuts between sequences (carrying the previous sequence's
    last frame as the seed image, same continuity strategy as the per-scene
    flow uses across chunks of a single scene).

    Tradeoffs vs render_screenplay():
      + Smoother motion within a sequence (one shared model context)
      + Joint A/V output with model-generated audio (no separate stitch step
        needed for the relay portion)
      - Bounded by VRAM: max ~489 frames per sequence on Spark
      - Single seed image per sequence (best for "same character, varied
        actions" not "now we're somewhere completely different")

    Returns: a manifest dict listing sequences + per-sequence output mp4 paths.
    """
    with open(screenplay_path, encoding="utf-8") as f:
        screenplay = json.load(f)

    scenes = screenplay.get("scenes") or screenplay.get("shots") or []
    if limit is not None:
        scenes = scenes[:limit]

    project_name = (screenplay.get("title")
                    or os.path.splitext(os.path.basename(screenplay_path))[0])
    project_name = "".join(c if c.isalnum() or c in "_-" else "_" for c in project_name)[:60]
    output_dir = output_dir or os.path.join(OUTPUT_ROOT, "movie_fast", project_name)
    os.makedirs(output_dir, exist_ok=True)
    comfy_prefix = f"movie_fast/{project_name}_relay"

    if base_seed is None:
        base_seed = random.randint(0, 2**31 - 1)

    sequences = chunk_scenes_into_relay_sequences(scenes, fps, max_frames=max_frames)

    print(f"=== Movie Maker Fast — Screenplay Run (Prompt Relay) ===")
    print(f"  screenplay:  {screenplay_path}")
    print(f"  project:     {project_name}")
    print(f"  scenes:      {len(scenes)}{' (limited)' if limit else ''}")
    print(f"  → sequences: {len(sequences)} (auto-chunked at {max_frames}-frame budget)")
    for i, seq in enumerate(sequences):
        n_scenes = len(seq['scenes'])
        truncated = '⚠ TRUNCATED' if seq.get('_truncated_from') else ''
        print(f"    seq {i}: scenes [{seq['scene_indices'][0]}..{seq['scene_indices'][-1]}] "
              f"({n_scenes} scene{'s' if n_scenes>1 else ''}, "
              f"{seq['total_frames']} frames ≈ {seq['total_frames']/fps:.1f}s) {truncated}")
    print(f"  dims/fps:    {width}x{height} @ {fps}fps")
    print(f"  sampler:     {sampler_name} / {scheduler_name} / {steps} steps / CFG {cfg}")
    print(f"  audio:       {'KEEP (joint A/V per sequence)' if save_audio else 'DROP (video-only)'}")
    print(f"  base_seed:   {base_seed}")
    print(f"  output:      {output_dir}")
    print()

    t0_all = time.time()
    all_sequences_out = []
    last_frame_image = None  # carry-forward across sequences

    for seq_i, seq in enumerate(sequences):
        seed = (base_seed + seq_i * 1000) & 0x7FFFFFFF
        # Seed image precedence: explicit scene image > previous sequence's last frame
        seed_image = seq["seed_image"] or last_frame_image

        timeline = [_scene_to_relay_segment(sc, fps) for sc in seq["scenes"]]
        wrapper = _build_sequence_wrapper(screenplay, seq)
        seq_prefix = f"{comfy_prefix}_seq{seq_i:03d}_seed{seed}"
        out_path = os.path.join(output_dir, f"sequence_{seq_i:03d}_seed{seed}.mp4")

        print(f"[SEQ {seq_i:03d}/{len(sequences)-1}] {len(seq['scenes'])} scene(s), "
              f"{seq['total_frames']} frames, seed_image={seed_image or '(T2V)'}")
        for j, scene in enumerate(seq["scenes"]):
            desc = (scene.get('description') or scene.get('action') or '?')[:80]
            print(f"  • scene {seq['scene_indices'][j]}: {desc}")

        try:
            wf, seed_used, total_frames = build_ltx_prompt_relay_workflow(
                timeline=timeline,
                wrapper_prompt=wrapper,
                seed_image_path=seed_image,
                fps=fps, width=width, height=height,
                steps=steps, cfg=cfg, seed=seed,
                sampler_name=sampler_name, scheduler_name=scheduler_name,
                use_lora=use_lora, lora_strength=lora_strength,
                sage_attention=True, save_audio=save_audio,
                filename_prefix=seq_prefix,
            )
            t0 = time.time()
            result, pid = submit_and_wait(wf, f"mmfast-relay-{seed_used}",
                                          poll_timeout=2400)
            elapsed = time.time() - t0
            status = result.get("status", {}).get("status_str")
            if status != "success":
                print(f"  SEQ FAILED: {status}")
                continue

            # Locate output mp4 (FS first, /view fallback)
            src = None
            for v in result.get("outputs", {}).values():
                for key in ("videos", "gifs", "images"):
                    for a in v.get(key, []):
                        if not isinstance(a, dict) or "filename" not in a:
                            continue
                        fn = a["filename"]
                        if not fn.lower().endswith((".mp4", ".webm")):
                            continue
                        sub = a.get("subfolder", "")
                        ftype = a.get("type", "output")
                        p_cand = os.path.join(OUTPUT_ROOT, sub, fn)
                        if os.path.exists(p_cand):
                            src = p_cand; break
                        try:
                            blob = comfy_fetch_view(fn, sub, ftype)
                            os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
                            with open(out_path, "wb") as f: f.write(blob)
                            src = out_path; break
                        except Exception as exc:
                            print(f"  WARN: /view fallback failed: {exc}")
                    if src: break
                if src: break

            if not src:
                print(f"  SEQ FAILED: no output file found")
                continue
            if os.path.abspath(src) != out_path:
                shutil.copy2(src, out_path)
            size_mb = os.path.getsize(out_path) / 1024 / 1024
            print(f"  ✓ {total_frames}f @ {fps}fps = {total_frames/fps:.1f}s in {elapsed:.0f}s "
                  f"({size_mb:.2f} MB) → {out_path}")

            # Carry-forward last frame for the next sequence's seed image.
            # Extract locally with ffmpeg, then UPLOAD to ComfyUI via /upload/image.
            # Upload-then-reference is more robust than writing to a guessed
            # COMFYUI_ROOT/input/... path — it works regardless of whether the
            # script runs in-container, on-host, or via SSH from a separate machine.
            if carry_last_frame and seq_i < len(sequences) - 1:
                # tempfile in OS temp dir — local-only, doesn't need ComfyUI's filesystem
                tmp_dir = os.path.join(tempfile.gettempdir(), "movie_fast_carry")
                os.makedirs(tmp_dir, exist_ok=True)
                tmp_png = os.path.join(
                    tmp_dir,
                    f"{project_name}_seq{seq_i:03d}_lastframe.png",
                )
                try:
                    _extract_last_frame(out_path, tmp_png)
                    last_frame_image = comfy_upload_image(
                        tmp_png,
                        target_subfolder="_movie_fast_frames",
                        overwrite=True,
                    )
                    print(f"  carry-forward: uploaded {os.path.basename(tmp_png)} → "
                          f"ComfyUI input as '{last_frame_image}'")
                except Exception as exc:
                    print(f"  WARN: carry-forward failed: {exc}; next seq goes T2V")
                    last_frame_image = None

            all_sequences_out.append({
                "sequence_idx": seq_i,
                "scene_indices": seq["scene_indices"],
                "n_scenes": len(seq["scenes"]),
                "total_frames": total_frames,
                "duration_s": round(total_frames / fps, 2),
                "seed": seed_used,
                "seed_image": seed_image,
                "wrapper": wrapper,
                "output_path": out_path,
                "size_bytes": os.path.getsize(out_path),
                "render_elapsed_s": round(elapsed, 1),
                "joint_av": save_audio,
            })
        except Exception as e:
            print(f"  SEQ FAILED: {e}")

    elapsed_all = time.time() - t0_all
    manifest = {
        "project_name": project_name,
        "mode": "prompt_relay",
        "width": width, "height": height, "fps": fps,
        "steps": steps, "cfg": cfg, "sampler": sampler_name,
        "scheduler": scheduler_name,
        "save_audio": save_audio,
        "max_relay_frames": max_frames,
        "use_lora": use_lora, "lora_strength": lora_strength,
        "base_seed": base_seed,
        "carry_last_frame": carry_last_frame,
        "n_scenes_input": len(scenes),
        "n_sequences_rendered": len(all_sequences_out),
        "total_elapsed_s": round(elapsed_all, 1),
        "sequences": all_sequences_out,
    }
    manifest_path = os.path.join(output_dir, "relay_manifest.json")
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)

    print(f"\n=== Screenplay Relay Complete ===")
    print(f"  sequences: {len(all_sequences_out)} / {len(sequences)}")
    print(f"  total:     {sum(s['total_frames'] for s in all_sequences_out)} frames "
          f"= {sum(s['duration_s'] for s in all_sequences_out):.1f}s of footage")
    print(f"  elapsed:   {elapsed_all:.0f}s ({elapsed_all/60:.1f} min)")
    print(f"  manifest:  {manifest_path}")
    return manifest


def render_screenplay(screenplay_path, output_dir=None, *,
                      mode=DEFAULT_MODE, base_seed=None,
                      width=DEFAULT_WIDTH, height=DEFAULT_HEIGHT, fps=DEFAULT_FPS,
                      steps=DEFAULT_STEPS, cfg=DEFAULT_CFG,
                      persistence=None, sampler_name="euler",
                      carry_last_frame=True,
                      limit=None):
    """Drive a full screenplay through the LTX 2.3 fast pipeline.

    Expects a screenplay JSON compatible with the existing AGENT_CINEMA_AUTOPILOT
    format (produced by produce.py's stage_storyboard).

    Produces per-scene clip MP4s under output/movie_fast/<project>/ and a
    manifest JSON listing all clips in scene/chunk order for the stitcher.
    """
    with open(screenplay_path, encoding="utf-8") as f:
        screenplay = json.load(f)

    scenes = screenplay.get("scenes") or screenplay.get("shots") or []
    project_name = (screenplay.get("title")
                    or os.path.splitext(os.path.basename(screenplay_path))[0])
    # Sanitize project name for file paths
    project_name = "".join(c if c.isalnum() or c in "_-" else "_" for c in project_name)[:60]

    output_dir = output_dir or os.path.join(OUTPUT_ROOT, "movie_fast", project_name)
    os.makedirs(output_dir, exist_ok=True)
    # Relative prefix used by ComfyUI SaveVideo (ComfyUI prepends output/)
    comfy_prefix = f"movie_fast/{project_name}"

    if base_seed is None:
        base_seed = random.randint(0, 2**31 - 1)

    print(f"=== Movie Maker Fast — Screenplay Run ===")
    print(f"  screenplay: {screenplay_path}")
    print(f"  project:    {project_name}")
    print(f"  scenes:     {len(scenes)}{' (limited to first ' + str(limit) + ')' if limit else ''}")
    print(f"  mode:       {mode}")
    print(f"  dims/fps:   {width}x{height} @ {fps}fps")
    print(f"  sampler:    {steps} steps, CFG {cfg}")
    print(f"  base_seed:  {base_seed}")
    print(f"  output:     {output_dir}")
    print()

    t0_all = time.time()
    all_clips = []
    for i, scene in enumerate(scenes):
        if limit is not None and i >= limit:
            break
        print(f"[SCENE {i:03d}] {str(scene.get('description','') or scene.get('action',''))[:70]}")
        try:
            clips = render_scene(
                scene, i, comfy_prefix,
                base_seed=base_seed, mode=mode,
                width=width, height=height, fps=fps,
                steps=steps, cfg=cfg,
                persistence=persistence, sampler_name=sampler_name,
                carry_last_frame=carry_last_frame,
            )
            all_clips.extend({"scene_idx": i, **c} for c in clips)
        except Exception as e:
            print(f"  SCENE FAILED: {e}")

    elapsed_all = time.time() - t0_all
    manifest = {
        "project_name": project_name,
        "mode": mode,
        "width": width, "height": height, "fps": fps,
        "steps": steps, "cfg": cfg,
        "base_seed": base_seed,
        "total_elapsed_s": round(elapsed_all, 1),
        "clips": all_clips,
    }
    manifest_path = os.path.join(output_dir, "clips_manifest.json")
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)

    print(f"\n=== Screenplay Complete ===")
    print(f"  clips: {len(all_clips)}")
    print(f"  elapsed: {elapsed_all:.0f}s ({elapsed_all/60:.1f} min)")
    print(f"  manifest: {manifest_path}")
    return manifest


# ============================================================================
# Phase 3 — Stitcher
# ============================================================================

def run_ffmpeg(cmd, *, check=True, capture=True):
    """Print a short trace + run ffmpeg. Raises on nonzero when check=True."""
    short = " ".join(f'"{c}"' if " " in c else c for c in cmd[:6])
    print(f"    $ {short}{' ...' if len(cmd) > 6 else ''}", flush=True)
    r = subprocess.run(cmd, capture_output=capture, text=True)
    if check and r.returncode != 0:
        print(f"    STDERR tail: {(r.stderr or '')[-1500:]}")
        raise RuntimeError(f"ffmpeg failed: {r.returncode}")
    return r


def probe_duration_s(path):
    r = run_ffmpeg([FFPROBE, "-v", "error", "-show_entries", "format=duration",
                   "-of", "csv=p=0", path])
    return float(r.stdout.strip())


def stitch_clips(manifest_path, *,
                  output_path=None,
                  dialogue_wav=None, music_wav=None, sfx_wav=None,
                  xfade_s=0.8, music_volume=0.30, sfx_volume=0.8,
                  lufs=-16.0):
    """Stitch the clips listed in a `clips_manifest.json` into a final film.

    Signal chain:
      1. Concat all clips with `xfade` (video) — progressive crossfades at clip
         boundaries. Audio from clips is discarded (LTX fast-mode is video-only
         anyway; quality-mode audio is incoherent-per-clip without continuity
         across chunks).
      2. Optional audio track mux with sidechain ducking:
           music  — ducked against dialogue (threshold 0.05, ratio 8:1,
                    attack 20ms, release 300ms). volume = music_volume.
           SFX    — overlayed directly at sfx_volume.
           dialogue — the clean speech bus.
      3. Loudnorm to `lufs` LUFS (I=-16, TP=-1.5, LRA=11 — podcast/broadcast).

    Args:
        manifest_path: path to a `clips_manifest.json` from render_screenplay()
        output_path:   final mp4 path; defaults to <project>_final.mp4 next to manifest
        dialogue_wav:  path to the dialogue master WAV (from Qwen3-TTS
                       via scene_production_tool/produce.py stage_tts or
                       radio_drama.py stage_mix dialogue bus)
        music_wav:     optional music master WAV (from music_tool/music_maker.py)
        sfx_wav:       optional SFX master WAV (from radio_drama.py generate_sfx
                       chain or a timeline-placed SFX bus — preferably already
                       aligned to the video timeline)
        xfade_s:       crossfade duration between consecutive clips, default 0.8 s
        music_volume:  base volume for music track (0-1)
        sfx_volume:    base volume for SFX track
        lufs:          target integrated loudness (EBU R128)
    """
    with open(manifest_path, encoding="utf-8") as f:
        manifest = json.load(f)
    clips = manifest.get("clips") or []
    if not clips:
        raise RuntimeError(f"No clips in manifest: {manifest_path}")

    # Resolve paths + measure durations
    project_name = manifest.get("project_name", "film")
    manifest_dir = os.path.dirname(os.path.abspath(manifest_path))
    output_path = output_path or os.path.join(manifest_dir, f"{project_name}_final.mp4")

    clip_infos = []
    for c in clips:
        p = c["clip_path"]
        d = probe_duration_s(p)
        clip_infos.append({"path": p, "duration": d})

    fps = manifest.get("fps", DEFAULT_FPS)
    print(f"=== Stitch: {len(clip_infos)} clips → {output_path} ===")

    # Concat video with xfade. For N clips we need N-1 xfade calls.
    # Final duration after all xfades: sum(d) - (N-1)*xfade
    if len(clip_infos) == 1:
        # Single clip — just copy + re-encode to canonical format
        cmd = [FFMPEG, "-y", "-i", clip_infos[0]["path"],
               "-c:v", "libx264", "-crf", "18", "-preset", "fast",
               "-pix_fmt", "yuv420p", "-an",
               os.path.splitext(output_path)[0] + "_nosound.mp4"]
        run_ffmpeg(cmd)
        video_nosound = os.path.splitext(output_path)[0] + "_nosound.mp4"
    else:
        # Build xfade chain: clip0 + clip1 via xfade, result + clip2 via xfade, ...
        cmd = [FFMPEG, "-y"]
        for ci in clip_infos:
            cmd += ["-i", ci["path"]]
        # Compute cumulative offsets for xfade (offset = running_length - xfade_s)
        filter_parts = []
        cur_label = "[0:v]"
        cur_dur = clip_infos[0]["duration"]
        for i in range(1, len(clip_infos)):
            offset = max(0, cur_dur - xfade_s)
            out_label = f"[v{i}]" if i < len(clip_infos) - 1 else "[vout]"
            filter_parts.append(
                f"{cur_label}[{i}:v]xfade=transition=fade:duration={xfade_s:.3f}:"
                f"offset={offset:.3f}{out_label}"
            )
            cur_label = out_label
            # Chained length grows by new_clip - xfade
            cur_dur = cur_dur + clip_infos[i]["duration"] - xfade_s
        filter_complex = ";".join(filter_parts)
        video_nosound = os.path.splitext(output_path)[0] + "_nosound.mp4"
        cmd += ["-filter_complex", filter_complex, "-map", "[vout]",
                "-c:v", "libx264", "-crf", "18", "-preset", "fast",
                "-pix_fmt", "yuv420p", "-an",
                video_nosound]
        run_ffmpeg(cmd)

    final_video_dur = probe_duration_s(video_nosound)
    print(f"    video stitched: {final_video_dur:.2f}s  ({video_nosound})")

    # Audio mux. No audio tracks → just rename video_nosound to output_path.
    if not any([dialogue_wav, music_wav, sfx_wav]):
        shutil.move(video_nosound, output_path)
        print(f"\n=== Final (video-only): {output_path}  ({os.path.getsize(output_path)/1024/1024:.1f} MB)")
        return output_path

    # Build audio mix + loudnorm
    inputs = [video_nosound]
    track_labels = []
    filter_chains = []

    def _register(path, vol, as_speech=False):
        idx = len(inputs)
        inputs.append(path)
        tag = f"a{idx}"
        # Pad to video duration so short tracks don't truncate the mix
        filter_chains.append(
            f"[{idx}:a]aresample=48000,aformat=sample_rates=48000:sample_fmts=fltp:"
            f"channel_layouts=stereo,apad=whole_dur={final_video_dur:.3f},"
            f"atrim=0:{final_video_dur:.3f},volume={vol:.3f}[{tag}]"
        )
        track_labels.append((tag, as_speech))

    if dialogue_wav:
        _register(dialogue_wav, 1.0, as_speech=True)
    if sfx_wav:
        _register(sfx_wav, sfx_volume, as_speech=False)
    if music_wav:
        _register(music_wav, music_volume, as_speech=False)

    # If we have both speech and music, sidechain-duck music against speech
    speech_tags = [t for t, s in track_labels if s]
    non_speech_tags = [t for t, s in track_labels if not s]
    if speech_tags and non_speech_tags:
        # Build a mono speech bus as the sidechain key
        speech_bus_in = "".join(f"[{t}]" for t in speech_tags)
        filter_chains.append(
            f"{speech_bus_in}amix=inputs={len(speech_tags)}:duration=longest:normalize=0[speech_raw]"
        )
        filter_chains.append(
            "[speech_raw]aformat=sample_rates=48000:sample_fmts=fltp:channel_layouts=stereo,"
            "alimiter=level_in=1:level_out=0.95:limit=0.98[speech]"
        )
        filter_chains.append("[speech]asplit=2[speech_out][speech_key]")

        # Duck music tracks by the speech key (chain them if multiple)
        music_bus_in = "".join(f"[{t}]" for t in non_speech_tags)
        filter_chains.append(
            f"{music_bus_in}amix=inputs={len(non_speech_tags)}:duration=longest:normalize=0[music_raw]"
        )
        filter_chains.append(
            "[music_raw][speech_key]sidechaincompress=threshold=0.05:ratio=8:"
            "attack=20:release=300:makeup=1[music_ducked]"
        )
        filter_chains.append(
            "[speech_out][music_ducked]amix=inputs=2:duration=longest:normalize=0:"
            "weights=1.0 0.8[mix_raw]"
        )
    else:
        # No ducking needed — flat mix
        all_tags = "".join(f"[{t}]" for t, _ in track_labels)
        filter_chains.append(
            f"{all_tags}amix=inputs={len(track_labels)}:duration=longest:normalize=0[mix_raw]"
        )

    # Loudnorm on the final mix
    filter_chains.append(
        f"[mix_raw]loudnorm=I={lufs}:TP=-1.5:LRA=11[aout]"
    )

    filter_complex = ";".join(filter_chains)
    cmd = [FFMPEG, "-y"]
    for i_path in inputs:
        cmd += ["-i", i_path]
    cmd += ["-filter_complex", filter_complex,
            "-map", "0:v", "-map", "[aout]",
            "-c:v", "copy",  # reuse video from the xfade step
            "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
            "-shortest", output_path]
    run_ffmpeg(cmd)

    # Cleanup intermediate
    if os.path.exists(video_nosound) and video_nosound != output_path:
        os.remove(video_nosound)

    final_dur = probe_duration_s(output_path)
    size_mb = os.path.getsize(output_path) / 1024 / 1024
    print(f"\n=== Final: {output_path}")
    print(f"    duration: {final_dur:.2f}s  ({final_dur/60:.2f} min)")
    print(f"    size:     {size_mb:.1f} MB")
    print(f"    loudness: {lufs} LUFS (EBU R128)")
    return output_path


# ============================================================================
# CLI — single-clip render for Phase 1, screenplay for Phase 2, stitch for Phase 3
# ============================================================================

def main():
    p = argparse.ArgumentParser(
        description="Movie Maker Fast — LTX 2.3 cinematic video generator")
    sub = p.add_subparsers(dest="cmd")

    # Subcommand: clip  — single clip render (Phase 1)
    pc = sub.add_parser("clip", help="Render a single clip from an image + prompt (I2V)")
    pc.add_argument("--image", default=None,
        help="Input image path RELATIVE to ComfyUI's input directory. Required unless --t2v.")
    pc.add_argument("--t2v", action="store_true",
        help="Text-to-video mode — no image needed. Content comes purely from --prompt. "
             "Ideal for procedural / fractal / abstract / geometric generative content.")
    pc.add_argument("--prompt", required=True, help="Scene description for the clip")
    pc.add_argument("--negative", default=DEFAULT_NEGATIVE)
    pc.add_argument("--duration", type=float, default=7.0, help="Clip duration in seconds (≤ 7)")
    pc.add_argument("--fps", type=int, default=DEFAULT_FPS)
    pc.add_argument("--width", type=int, default=DEFAULT_WIDTH)
    pc.add_argument("--height", type=int, default=DEFAULT_HEIGHT)
    pc.add_argument("--steps", type=int, default=DEFAULT_STEPS)
    pc.add_argument("--cfg", type=float, default=DEFAULT_CFG)
    pc.add_argument("--seed", type=int, default=None)
    pc.add_argument("--tags", nargs="*", default=[],
        help="Scene tags to add LoRAs; e.g. --tags 'camera: dolly-left' 'transition'")
    pc.add_argument("--mode", default=DEFAULT_MODE, choices=list(MODES),
        help=f"Render mode (default: {DEFAULT_MODE}). 'fast' = distilled-fp8 (faster), "
             f"'quality' = non-distilled fp8 + distill LoRA (higher fidelity, ~30-50%% slower), "
             f"'abstract' = no physics LoRAs for fractals/artwork.")
    pc.add_argument("--persistence", type=float, default=None,
        help="Image-persistence [0..1]: 0=full motion freedom, 1=hold input frame. "
             "Try 0.7 for steady character shots, 0.3 for dynamic action, unset for default (full motion).")
    pc.add_argument("--sampler", default="euler",
        help="KSampler name (default 'euler'; 'euler_ancestral' for abstract = more variation).")
    pc.add_argument("--style", default=None,
        help="Shortcut for a style tag: animation|claymation|ghibli|galaxy|tribal|illustration|cyberpunk. "
             "Appended to --tags as 'style: <name>'.")
    pc.add_argument("--audio-reference", default=None,
        help="A2V: filename of an audio clip in input/. Currently a no-op — no shipped model "
             "supports joint audio-video conditioning. Reserved for future audio-capable "
             "checkpoints. Audio for the final video should be added at stitch time via "
             "the separate audio stack (Qwen3-TTS / ACE-Step / MMAudio).")
    pc.add_argument("--audio-guidance", type=float, default=0.5,
        help="A2V: strength of audio influence on video (0.0=ignore, 1.0=dominant). Default 0.5.")
    pc.add_argument("--audio-start-pct", type=float, default=0.0,
        help="A2V: diffusion timestep fraction to start applying audio guidance (default 0.0).")
    pc.add_argument("--audio-end-pct", type=float, default=1.0,
        help="A2V: diffusion timestep fraction to stop applying audio guidance (default 1.0).")
    pc.add_argument("--vbvr-strength", type=float, default=None,
        help="Override VBVR physics LoRA strength (default 0.7). Lower (0.3-0.5) if "
             "output is over-saturated or distorted; raise toward 1.0 for stronger physics constraints.")
    pc.add_argument("--ic-lora-strength", type=float, default=None,
        help="Override IC-LoRA union control strength (default 0.7). Lower if "
             "output is over-stylized; raise toward 1.0 for stronger composition control.")
    pc.add_argument("--output", "-o", default=None,
        help="Output mp4 path (default: output/movie_fast/<slug>_<seed>.mp4)")
    # ── Phase 1b: Prompt Relay ────────────────────────────────────────────
    pc.add_argument("--relay", default=None, metavar="TIMELINE.JSON",
        help="Render via LTX 2.3 Prompt Relay (timeline of prompts → ONE continuous "
             "joint A/V pass with smooth morphing between segments). Takes a JSON file "
             "with a 'segments' list (per-segment 'prompt' + 'duration_s' or 'frames'), "
             "an optional 'wrapper' anchor prompt, an optional 'seed_image', plus the "
             "usual fps/width/height. When --relay is set, --image / --t2v / --prompt / "
             "--mode / per-tool LoRA flags are IGNORED — the relay builder uses its own "
             "model body and conditioning path. Total frames must be ≤ MAX_RELAY_FRAMES "
             "(489 by default); split longer films into multiple sequences.")
    pc.add_argument("--relay-wrapper", default=None,
        help="Override wrapper anchor prompt (else taken from timeline.json's 'wrapper' field, "
             "else built from the first segment's prompt).")
    pc.add_argument("--relay-no-audio", dest="relay_save_audio",
        action="store_false", default=True,
        help="Drop the audio track from the relay output (video-only mp4). "
             "Default: keep the model-generated joint A/V audio.")
    pc.add_argument("--relay-use-lora", action="store_true",
        help="Apply the distill-1.1 LoRA on top of the relay UNet. Off by default — "
             "the canonical example workflow has it bypassed.")
    pc.add_argument("--relay-lora-strength", type=float, default=0.5,
        help="Distill-1.1 LoRA strength when --relay-use-lora is set. Default 0.5.")

    # Subcommand: screenplay  — drive a full screenplay JSON
    ps = sub.add_parser("screenplay", help="Render all scenes from a screenplay JSON")
    ps.add_argument("screenplay_path",
        help="Path to screenplay.json (from produce.py, AGENT_CINEMA_AUTOPILOT, or compatible)")
    ps.add_argument("--output-dir", default=None,
        help="Output directory (default: output/movie_fast/<project>)")
    ps.add_argument("--mode", default=DEFAULT_MODE, choices=list(MODES))
    ps.add_argument("--width", type=int, default=DEFAULT_WIDTH)
    ps.add_argument("--height", type=int, default=DEFAULT_HEIGHT)
    ps.add_argument("--fps", type=int, default=DEFAULT_FPS)
    ps.add_argument("--steps", type=int, default=DEFAULT_STEPS)
    ps.add_argument("--cfg", type=float, default=DEFAULT_CFG)
    ps.add_argument("--seed", type=int, default=None)
    ps.add_argument("--limit", type=int, default=None,
        help="Only render the first N scenes (useful for testing)")
    ps.add_argument("--persistence", type=float, default=None,
        help="Global persistence override (0..1). Individual scenes can set their own `persistence` field.")
    ps.add_argument("--sampler", default="euler")
    ps.add_argument("--vbvr-strength", type=float, default=None,
        help="Override VBVR physics LoRA strength (default 0.7). Applied to every scene.")
    ps.add_argument("--ic-lora-strength", type=float, default=None,
        help="Override IC-LoRA union control strength (default 0.7). Applied to every scene.")
    ps.add_argument("--no-carry-last-frame", dest="carry_last_frame",
        action="store_false", default=True,
        help="Disable last-frame carry-forward between chunks of a scene. "
             "Default ON: chunk N+1 starts from chunk N's last frame for visual continuity.")
    # ── Phase 2: Prompt Relay screenplay path ─────────────────────────────
    ps.add_argument("--use-relay", action="store_true",
        help="Render the screenplay via LTX 2.3 Prompt Relay sequences instead of the "
             "per-scene I2V flow. Auto-chunks consecutive scenes into Prompt Relay "
             "sequences (each ≤ MAX_RELAY_FRAMES = %d frames on Spark) so each "
             "sequence becomes ONE forward pass with smooth morphing through its "
             "scenes. Hard cuts between sequences carry-forward the previous "
             "sequence's last frame as seed image. Output is JOINT A/V — model "
             "generates audio simultaneously with video. Per-scene scenes can opt "
             "into starting a new sequence by setting `relay_break: true` or any of "
             "the tags {'transition', 'cut', 'scene_change'}." % MAX_RELAY_FRAMES)
    ps.add_argument("--relay-no-audio", dest="relay_save_audio",
        action="store_false", default=True,
        help="With --use-relay: drop the audio track from each sequence. Default "
             "keeps the model-generated joint A/V audio.")
    ps.add_argument("--relay-use-lora", action="store_true",
        help="With --use-relay: apply distill-1.1 LoRA on top of the relay UNet "
             "(off by default — canonical workflow bypasses it).")
    ps.add_argument("--relay-lora-strength", type=float, default=0.5,
        help="With --use-relay --relay-use-lora: LoRA strength (default 0.5).")
    ps.add_argument("--relay-max-frames", type=int, default=MAX_RELAY_FRAMES,
        help=f"With --use-relay: max frames per single Prompt Relay pass "
             f"(default {MAX_RELAY_FRAMES} — validated ceiling on Spark).")

    # Subcommand: stitch  — concat clips from manifest + optional audio
    pst = sub.add_parser("stitch", help="Concatenate clips from a manifest with optional audio mux")
    pst.add_argument("manifest_path",
        help="Path to clips_manifest.json produced by the screenplay subcommand")
    pst.add_argument("--output", "-o", default=None, help="Final MP4 path")
    pst.add_argument("--dialogue", default=None, help="Path to dialogue master WAV (Qwen3-TTS)")
    pst.add_argument("--music", default=None, help="Path to music bed WAV (music_maker)")
    pst.add_argument("--sfx", default=None, help="Path to SFX master WAV (radio_drama)")
    pst.add_argument("--xfade", type=float, default=0.8, help="Crossfade duration between clips")
    pst.add_argument("--music-volume", type=float, default=0.30)
    pst.add_argument("--sfx-volume", type=float, default=0.8)
    pst.add_argument("--lufs", type=float, default=-16.0)

    args = p.parse_args()

    # Default to 'clip' for back-compat if no subcommand given
    if args.cmd is None:
        print("Usage: python movie_maker_fast.py {clip|screenplay} ...")
        print("       python movie_maker_fast.py clip --image IMG --prompt '...' [options]")
        print("       python movie_maker_fast.py screenplay screenplay.json [options]")
        sys.exit(1)

    # Apply --vbvr-strength / --ic-lora-strength overrides if provided.
    # Mutates MODES in place so all downstream renders pick them up.
    apply_cli_lora_overrides(args)

    if args.cmd == "screenplay":
        if getattr(args, "use_relay", False):
            # Phase 2: Prompt Relay-driven screenplay. Each Prompt Relay
            # sequence does smooth multi-prompt morphing within its frame
            # budget; hard cuts between sequences carry the previous
            # sequence's last frame as seed image. Joint A/V output by
            # default (model generates audio with video).
            #
            # Prompt Relay uses different sampler defaults (8 steps, CFG 1.0,
            # euler_ancestral / linear_quadratic) than the per-scene I2V flow.
            # Honor user-provided overrides if explicitly set; otherwise use
            # the relay-tuned defaults rather than the I2V path's defaults.
            relay_steps = args.steps if args.steps != DEFAULT_STEPS else 8
            relay_cfg   = args.cfg   if args.cfg   != DEFAULT_CFG else 1.0
            relay_sampler = args.sampler if args.sampler != "euler" else "euler_ancestral"
            # Relay also uses square dims by convention; only override the
            # I2V-flow defaults when the user explicitly bumped them.
            relay_w = args.width  if args.width  != DEFAULT_WIDTH  else 640
            relay_h = args.height if args.height != DEFAULT_HEIGHT else 640
            render_screenplay_relay(
                args.screenplay_path, output_dir=args.output_dir,
                base_seed=args.seed,
                width=relay_w, height=relay_h, fps=args.fps,
                steps=relay_steps, cfg=relay_cfg, limit=args.limit,
                sampler_name=relay_sampler,
                use_lora=args.relay_use_lora,
                lora_strength=args.relay_lora_strength,
                save_audio=args.relay_save_audio,
                carry_last_frame=args.carry_last_frame,
                max_frames=args.relay_max_frames,
            )
        else:
            render_screenplay(
                args.screenplay_path, output_dir=args.output_dir,
                mode=args.mode, base_seed=args.seed,
                width=args.width, height=args.height, fps=args.fps,
                steps=args.steps, cfg=args.cfg, limit=args.limit,
                persistence=args.persistence, sampler_name=args.sampler,
                carry_last_frame=args.carry_last_frame,
            )
        return

    if args.cmd == "stitch":
        stitch_clips(
            args.manifest_path, output_path=args.output,
            dialogue_wav=args.dialogue, music_wav=args.music, sfx_wav=args.sfx,
            xfade_s=args.xfade, music_volume=args.music_volume,
            sfx_volume=args.sfx_volume, lufs=args.lufs,
        )
        return

    # Mode-specific always-on LoRAs + tag-driven scene LoRAs
    mode_cfg = MODES[args.mode]
    picks = list(mode_cfg["always_on_loras"])

    # --style shortcut → prepend to tags
    all_tags = list(args.tags or [])
    if args.style:
        all_tags.append(f"style: {args.style}")

    tags_lower = [t.lower().strip() for t in all_tags if t]
    extras = []
    for pattern, (path, strength) in SCENE_LORAS.items():
        if any(pattern in t for t in tags_lower):
            extras.append((path, strength))
    extras = extras[:3]
    picks.extend(extras)
    loras = picks
    # Mode-specific CFG / steps / sampler defaults (only override if user left at default)
    cfg = args.cfg if args.cfg != DEFAULT_CFG else mode_cfg.get("default_cfg", DEFAULT_CFG)
    steps = args.steps if args.steps != DEFAULT_STEPS else mode_cfg.get("default_steps", DEFAULT_STEPS)
    sampler = args.sampler if args.sampler != "euler" else mode_cfg.get("default_sampler", "euler")
    seed = args.seed if args.seed is not None else random.randint(0, 2**31 - 1)

    if args.output:
        out_path = os.path.abspath(args.output)
        prefix = os.path.splitext(os.path.basename(out_path))[0]
        internal_prefix = f"movie_fast/{prefix}"
    else:
        slug = "".join(c if c.isalnum() else "_" for c in args.prompt.lower())[:48].strip("_")
        internal_prefix = f"movie_fast/{slug}_{seed}"
        out_path = os.path.join(OUTPUT_ROOT, "movie_fast", f"{slug}_{seed}.mp4")

    # ── Phase 1b: Prompt Relay path ────────────────────────────────────────
    # When --relay is set, build the multi-segment timeline workflow instead
    # of the standard single-prompt I2V/T2V workflow. The two paths are
    # mutually exclusive — --relay's own timeline supplies all per-segment
    # prompts/durations, so --prompt / --duration / --image / --t2v / --mode
    # / per-tool LoRA flags become irrelevant here.
    if getattr(args, "relay", None):
        if not os.path.isfile(args.relay):
            raise SystemExit(f"--relay file not found: {args.relay}")
        with open(args.relay) as f:
            tl_doc = json.load(f)
        segs = tl_doc.get("segments")
        if not segs:
            raise SystemExit(f"--relay JSON missing 'segments' list: {args.relay}")
        wrapper = (args.relay_wrapper
                   or tl_doc.get("wrapper")
                   or tl_doc.get("wrapper_prompt")
                   or f"A continuous cinematic shot. {segs[0]['prompt']}")
        # Per-timeline overrides fall back to top-level CLI defaults
        relay_fps    = int(tl_doc.get("fps", args.fps))
        relay_width  = int(tl_doc.get("width",  640))   # square by default for prompt-relay
        relay_height = int(tl_doc.get("height", 640))
        relay_steps  = int(tl_doc.get("steps",  8))     # canonical example tuning
        relay_cfg    = float(tl_doc.get("cfg",  1.0))
        relay_seed_image = tl_doc.get("seed_image") or tl_doc.get("image")

        wf, seed_used, total_frames = build_ltx_prompt_relay_workflow(
            timeline=segs,
            wrapper_prompt=wrapper,
            seed_image_path=relay_seed_image,
            fps=relay_fps,
            width=relay_width, height=relay_height,
            steps=relay_steps, cfg=relay_cfg, seed=seed,
            sampler_name=tl_doc.get("sampler", "euler_ancestral"),
            scheduler_name=tl_doc.get("scheduler", "linear_quadratic"),
            use_lora=args.relay_use_lora,
            lora_strength=args.relay_lora_strength,
            sage_attention=True,
            save_audio=args.relay_save_audio,
            filename_prefix=internal_prefix,
        )
        print("=== Movie Maker Fast — Prompt Relay ===")
        print(f"  Wrapper:    {wrapper[:100]}{'...' if len(wrapper) > 100 else ''}")
        print(f"  Segments:   {len(segs)}")
        for i, s in enumerate(segs):
            est_f = s.get("frames") or _frames_from_duration(s.get("duration_s", 4.0), relay_fps)
            print(f"    [{i}] {est_f:>3} frames  {s['prompt'][:80]}")
        print(f"  Seed image: {relay_seed_image or '(T2V — blank latent)'}")
        print(f"  Dims:       {relay_width}×{relay_height} @ {relay_fps} fps")
        print(f"  Total:      {total_frames} frames "
              f"(~{total_frames / relay_fps:.1f}s)  [budget {MAX_RELAY_FRAMES}]")
        print(f"  Sampler:    {tl_doc.get('sampler', 'euler_ancestral')} / "
              f"{tl_doc.get('scheduler', 'linear_quadratic')} / {relay_steps} steps / CFG {relay_cfg}")
        print(f"  Audio:      {'KEEP (joint A/V)' if args.relay_save_audio else 'DROP (video-only)'}")
        print(f"  LoRA:       {'distill-1.1 @ %.1f' % args.relay_lora_strength if args.relay_use_lora else '(bypassed)'}")
        print(f"  Seed:       {seed_used}")
        print(f"  Output:     {out_path}")
        print()
        print("generating...", flush=True)
        # Skip the verbose I2V print block + jump straight to submit
        # (continues at the existing submit_and_wait call below)
        # We use a sentinel branch inside the existing post-build flow.

    # ── Standard single-prompt I2V/T2V path ────────────────────────────────
    elif not args.t2v and not args.image:
        raise SystemExit("`clip` requires --image (or use --t2v for text-to-video mode, or --relay <timeline.json> for prompt-relay)")
    else:
        wf, seed_used = build_ltx_i2v_workflow(
            image_path=args.image or "",  # ignored when t2v=True
            prompt=args.prompt, negative_prompt=args.negative,
            duration_s=args.duration, fps=args.fps,
            width=args.width, height=args.height,
            steps=steps, cfg=cfg, seed=seed,
            loras=loras, mode=args.mode, filename_prefix=internal_prefix,
            persistence=args.persistence, sampler_name=sampler,
            t2v=args.t2v,
            audio_reference=args.audio_reference,
            audio_guidance_scale=args.audio_guidance,
            audio_start_percent=args.audio_start_pct,
            audio_end_percent=args.audio_end_pct,
        )

    # The verbose Single-Clip print block only applies to the I2V/T2V path
    # (it inspects MODES, args.t2v, args.image, wf['41'] — all relay-incompatible).
    # The relay path printed its own banner above, so skip this block when
    # --relay was used.
    if not getattr(args, "relay", None):
        # No mode currently sets joint_av=True; --audio-reference is a no-op (warning
        # is emitted from build_ltx_i2v_workflow). effective_mode == requested mode.
        effective_mode = args.mode
        effective_cfg  = MODES[effective_mode]
        print("=== Movie Maker Fast — Single Clip ===")
        print(f"  Mode:       {effective_mode}  (joint_av={effective_cfg['joint_av']}, "
              f"t2v={args.t2v}, a2v={args.audio_reference is not None})")
        print(f"  Base:       {effective_cfg['checkpoint']}")
        print(f"  Encoder:    {effective_cfg['text_encoder']}")
        print(f"  Video VAE:  {effective_cfg['video_vae']}")
        if args.audio_reference:
            print(f"  A2V ref:    {args.audio_reference}  (guidance={args.audio_guidance:.2f}, "
                  f"window {args.audio_start_pct:.2f}..{args.audio_end_pct:.2f})")
        if args.t2v:
            print(f"  Input:      (none — text-to-video)")
        else:
            print(f"  Image:      {args.image}")
        if args.persistence is not None:
            i2v_str = 1.0 - float(args.persistence) * 0.6
            print(f"  Persistence:{args.persistence:.2f}  (i2v strength={i2v_str:.2f})")
        print(f"  Sampler:    {sampler} / linear_quadratic / {steps} steps / CFG {cfg}")
        print(f"  LoRAs ({len(loras)}):")
        for name, strength in loras:
            print(f"    {name}  @ {strength}")
        print(f"  Prompt:     {args.prompt[:80]}{'...' if len(args.prompt) > 80 else ''}")
        print(f"  Tags:       {args.tags or '(none)'}")
        print(f"  Dims:       {args.width}×{args.height} @ {args.fps} fps")
        print(f"  Duration:   {args.duration} s → {wf['41']['inputs']['length']} frames")
        print(f"  Seed:       {seed_used}")
        print(f"  Output:     {out_path}")
        print()
        print("generating...", flush=True)

    t0 = time.time()
    result, pid = submit_and_wait(wf, f"mmfast-{seed_used}", poll_timeout=1800)
    elapsed = time.time() - t0
    status = result.get("status", {}).get("status_str")
    if status != "success":
        print(f"FAILED: {status}")
        for m in result.get("status", {}).get("messages", [])[-8:]:
            print(f"  {str(m)[:400]}")
        sys.exit(1)

    # Find the rendered mp4. ComfyUI's SaveVideo node emits the file under the
    # `images` key of the node output (historical quirk — the `videos` key is used
    # only by older VHS nodes). Check both keys + any animation entries.
    # If the file isn't reachable via the local filesystem (script running inside
    # a container without COMFYUI_ROOT pointed at the right path, or pure-HTTP
    # remote mode without a shared mount), download via ComfyUI's /view endpoint
    # straight into out_path.
    src = None
    fetched_via_view = False
    for v in result.get("outputs", {}).values():
        for key in ("videos", "gifs", "images"):
            for a in v.get(key, []):
                if not isinstance(a, dict) or "filename" not in a:
                    continue
                fn = a["filename"]
                if not fn.lower().endswith((".mp4", ".webm", ".gif")):
                    continue
                sub = a.get("subfolder", "")
                ftype = a.get("type", "output")
                p_cand = os.path.join(OUTPUT_ROOT, sub, fn)
                if os.path.exists(p_cand):
                    src = p_cand; break
                # /view fallback: stream the bytes directly into out_path
                try:
                    blob = comfy_fetch_view(fn, sub, ftype)
                    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
                    with open(out_path, "wb") as f:
                        f.write(blob)
                    src = out_path; fetched_via_view = True; break
                except Exception as exc:
                    print(f"WARN: /view fallback failed for {sub}/{fn}: {exc}")
                    continue
            if src: break
        if src: break
    if not src:
        print("ERROR: no output video file found in history")
        print(f"outputs: {json.dumps(result.get('outputs',{}), indent=2)[:500]}")
        sys.exit(1)

    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    if not fetched_via_view and os.path.abspath(src) != out_path:
        shutil.copy2(src, out_path)
    size_mb = os.path.getsize(out_path) / 1024 / 1024

    r = subprocess.run([FFPROBE, "-v", "error", "-select_streams", "v:0",
        "-show_entries", "stream=codec_name,width,height,r_frame_rate:format=duration",
        "-of", "default=nw=1", out_path], capture_output=True, text=True)

    print(f"\ngenerated in {elapsed:.0f}s  ({args.duration/elapsed:.2f}× real-time)")
    print(f"clip:  {out_path}  ({size_mb:.2f} MB)")
    print(f"probe: {r.stdout.strip().replace(chr(10), ' | ')}")
    print(f"seed:  {seed_used}")


if __name__ == "__main__":
    main()
