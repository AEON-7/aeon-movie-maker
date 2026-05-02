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

Models (all on disk, all verified working via LTX-2 I2V - With VBVR_EROS.json):

  Base:        models/checkpoints/ltx2/ltx-2.3-eros.safetensors
  Video VAE:   models/vae/LTX23_video_vae_bf16.safetensors
  Text enc:    models/text_encoders/gemma-3-12b-abliterated-text-encoder.safetensors
  Distill LoRA:models/loras/ltx2/ltx-2.3-22b-distilled-lora-384.safetensors
  Union LoRA:  models/loras/ltx-2.3-22b-ic-lora-union-control-ref0.5.safetensors
  VBVR LoRA:   models/loras/ltx2/Ltx2.3-Licon-VBVR-I2V-96000-R32.safetensors
"""
import argparse, json, os, random, shutil, subprocess, sys, time
import urllib.request, urllib.error

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

# ComfyUI on Windows expects backslash path separators inside the filename field
# for nested model subdirectories (forward-slash paths fail validation with
# `value_not_in_list`). All nested paths here use `\` for Windows — plain basenames
# stay as-is. If porting to Linux, replace `\\` with `/`.
_SEP = os.sep

# Two render modes — picks checkpoint + audio-pipeline strategy per call:
#
#   "fast"    — ltx-2.3-22b-distilled-fp8.safetensors (27 GB, video-only).
#               Skips the AV latent pipeline (no audio VAE, empty audio latent,
#               concat/separate). ~2× faster than quality mode. Best for
#               productions where dialogue/music/SFX come from the separate
#               audio stack (Qwen3-TTS + ACE Step + MMAudio). DEFAULT.
#
#   "quality" — ltx2/ltx-2.3-eros.safetensors (35 GB, joint audio+video).
#               Uses the full LTXVImgToVideoInplace + LTXVConcatAVLatent pipeline
#               from the proven VBVR_EROS workflow. Slower but generates audio
#               latents in-band. Useful for reference / debugging.
#
# Either mode accepts the same per-scene LoRA routing.
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
        "text_encoder": "gemma-3-12b-abliterated-text-encoder.safetensors",
        "joint_av":     False,
        "always_on_loras": [
            ("ltx-2.3-22b-ic-lora-union-control-ref0.5.safetensors", 0.7),
            (f"ltx2{_SEP}Ltx2.3-Licon-VBVR-I2V-96000-R32.safetensors", 0.7),
        ],
    },
    "quality": {
        # EROS joint-AV pipeline — slow, mostly for debugging vs the fast path.
        # Distill LoRA at 0.5 is intentional partial distillation of the EROS base.
        "checkpoint":   f"ltx2{_SEP}ltx-2.3-eros.safetensors",
        "video_vae":    "LTX23_video_vae_bf16.safetensors",
        "text_encoder": "gemma-3-12b-abliterated-text-encoder.safetensors",
        "joint_av":     True,
        "always_on_loras": [
            # ComfyUI lists the -1.1 variant under ltxv/ prefix
            (f"ltxv{_SEP}ltx2{_SEP}ltx-2.3-22b-distilled-lora-384-1.1.safetensors", 0.5),
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
        "text_encoder": "gemma-3-12b-abliterated-text-encoder.safetensors",
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
    "reasoning":                      (f"ltx2{_SEP}LTX2.3_Reasoning_V1.safetensors",             0.7),
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
    # When audio_reference is set, LoadAudio + LTXVReferenceAudio are wired into
    # the workflow. The audio literally conditions video generation — motion,
    # pacing, and energy reflect the reference audio's content. Requires joint-AV
    # mode (forces `quality` mode since only EROS was trained on A-V pairs).
    audio_reference=None,
    audio_guidance_scale=0.5,
    audio_start_percent=0.0,
    audio_end_percent=1.0,
):
    """Assemble the LTX 2.3 I2V workflow as a ComfyUI API-format dict.

    Mirrors the stage-2-alone pattern from LTX-2 I2V - With VBVR_EROS.json's
    "Samplers" subgraph. LTX 2.3 EROS is a joint audio-video model, so we
    include an empty audio latent + LTXVConcatAVLatent / Separate pair around
    the sampler; after decode we take just the video stream (audio gets muxed
    later from Qwen3-TTS).

    Signal flow (node IDs as strings — ComfyUI API format):
       [10] CheckpointLoader  → MODEL0, CLIP0, VAE0 (ignored — we load all three fresh)
       [11] VAELoader(video)  → VAE
       [12] LTXAVTextEncoderLoader(gemma-abliterated, eros) → CLIP
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
    # A2V requires joint-AV: only EROS (quality mode) carries audio conditioning.
    # Auto-force quality if the caller wanted A2V but a non-joint mode.
    if audio_reference is not None and not MODES[mode]["joint_av"]:
        print(f"  [A2V auto-forcing mode=quality — current '{mode}' is not joint_av]")
        mode = "quality"
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
                p_cand = os.path.join(OUTPUT_ROOT, a.get("subfolder", ""), fn)
                if os.path.exists(p_cand):
                    return p_cand, elapsed, seed
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
        help="Scene tags to add LoRAs; e.g. --tags 'camera: dolly-left' 'reasoning'")
    pc.add_argument("--mode", default=DEFAULT_MODE, choices=list(MODES),
        help=f"Render mode (default: {DEFAULT_MODE}). 'fast' = distilled-fp8 video-only, "
             f"'quality' = eros joint AV, 'abstract' = no-physics for fractals/artwork.")
    pc.add_argument("--persistence", type=float, default=None,
        help="Image-persistence [0..1]: 0=full motion freedom, 1=hold input frame. "
             "Try 0.7 for steady character shots, 0.3 for dynamic action, unset for default (full motion).")
    pc.add_argument("--sampler", default="euler",
        help="KSampler name (default 'euler'; 'euler_ancestral' for abstract = more variation).")
    pc.add_argument("--style", default=None,
        help="Shortcut for a style tag: animation|claymation|ghibli|galaxy|tribal|illustration|cyberpunk. "
             "Appended to --tags as 'style: <name>'.")
    pc.add_argument("--audio-reference", default=None,
        help="A2V: filename of an audio clip in input/ — literally conditions video generation "
             "on the music. Auto-forces --mode quality (EROS joint-AV required). "
             "Pair with prompts like 'procedural mathematical fractal psychedelic' for trippy results.")
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

    if not args.t2v and not args.image:
        raise SystemExit("`clip` requires --image (or use --t2v for text-to-video mode)")

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

    # Reflect effective mode after auto-force (e.g. A2V forces quality)
    effective_mode = "quality" if (args.audio_reference and not mode_cfg["joint_av"]) else args.mode
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
    src = None
    container_path = None
    for v in result.get("outputs", {}).values():
        for key in ("videos", "gifs", "images"):
            for a in v.get(key, []):
                if not isinstance(a, dict) or "filename" not in a:
                    continue
                fn = a["filename"]
                if not fn.lower().endswith((".mp4", ".webm", ".gif")):
                    continue
                subfolder = a.get("subfolder", "")
                p_local = os.path.join(OUTPUT_ROOT, subfolder, fn)
                if os.path.exists(p_local):
                    src = p_local; break
                # File not found locally — assume it's inside a Docker container at the
                # container-side OUTPUT_ROOT path. Record the relative path for docker cp.
                container_rel = os.path.join(subfolder, fn)
                container_path = os.path.join("/workspace/ComfyUI/output", container_rel)
                src = p_local; break
            if src: break
        if src: break
    if not src:
        print("ERROR: no output video file found in history")
        print(f"outputs: {json.dumps(result.get('outputs',{}), indent=2)[:500]}")
        sys.exit(1)

    # If the source is inside Docker (container_path set but local file missing), copy it out
    if container_path and not os.path.exists(os.path.join(OUTPUT_ROOT, container_path.replace("/workspace/ComfyUI/output/", ""))):
        # Try docker cp to bring the file from the container
        cont_name = os.environ.get("COMFYUI_CONTAINER", "comfyui-spark")
        cp_src = f"{cont_name}:{container_path}"
        os.makedirs(os.path.dirname(src), exist_ok=True)
        cp_result = subprocess.run(
            ["docker", "cp", cp_src, src],
            capture_output=True, text=True
        )
        if cp_result.returncode != 0:
            # Last resort: try finding via docker exec find
            find_result = subprocess.run(
                ["docker", "exec", cont_name, "find", "/workspace/ComfyUI/output",
                 "-name", fn, "-type", "f"],
                capture_output=True, text=True
            )
            found_paths = [p.strip() for p in find_result.stdout.strip().split("\n") if p.strip()]
            if found_path := found_paths[0] if found_paths else None:
                subprocess.run(["docker", "cp", f"{cont_name}:{found_path}", src], check=True)

    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    if os.path.abspath(src) != out_path:
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
