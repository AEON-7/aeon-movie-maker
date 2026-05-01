---
name: movie-maker-fast
description: >
  Fast cinematic video generator built on LTX 2.3 (distilled fp8, video-only) + abliterated Gemma
  text encoder + physics/control/motion LoRA stack. Produces a full screenplay-driven film at
  roughly 10-15x the speed of the WAN MultiTalk pipeline (Movie Maker Slow WAN). Use this skill
  when the user wants a movie / film / cinematic video / animated scene production and speed
  matters more than strict lip-sync accuracy. Companion audio pipelines (Qwen3-TTS Three-Lock
  for dialogue, ACE Step XL base via music_maker for music, MMAudio for SFX) compose alongside
  via the stitcher's audio mux. Distinct from radio-drama-production (audio-only) and
  AGENT_CINEMA_AUTOPILOT (WAN-based slow pipeline).
---

# Movie Maker Fast — LTX 2.3 cinematic video pipeline

> Companion to `radio-drama-production` (audio only), `music-producer` (standalone music), and `tts-voice-designer` (voice casting). This skill is the **video engine**; it imports all three of those for the audio passes.

## 0. Target host + tool

- **Host:** `${SSH_USER}@127.0.0.1` (Workstation — RTX 5090, 64 GB RAM)
- **Tool:** `${COMFYUI_ROOT}\scene_production_tool\movie_maker_fast.py`
- **Companion tools** (invoked by this one for audio):
  - `scene_production_tool/radio_drama.py` — dialogue TTS + SFX priority chain
  - `music_tool/music_maker.py` — music cues via ACE Step XL base + APG chain
- **ComfyUI endpoint:** `http://127.0.0.1:8188`

## 1. Why this skill exists (and when NOT to use it)

The original cinema pipeline (`AGENT_CINEMA_AUTOPILOT` using `render_all_acts.py` + WAN 2.1 MultiTalk) produces **very tight lip-synced dialogue** but takes ~20–30 min per shot. For a 10-minute drama that's 4–6 hours of render.

Movie Maker Fast uses **LTX 2.3 distilled fp8** — a video-only model tuned for speed. A 7-second clip at 832×480 renders in ~75 s warm on the 5090. The full 10-minute drama renders in ~30–40 min. **~10–15× speedup.**

**Use this skill when:**
- Visuals are the primary deliverable; lip-sync is "close enough"
- You want a cinematic film with musical scoring + SFX, dialogue may be VO or off-frame
- Speed matters (previews, iterations, multi-shot drafts before committing)
- The production has many scenes (>15) where MultiTalk's per-shot cost is prohibitive

**Use `AGENT_CINEMA_AUTOPILOT` (slow WAN) instead when:**
- On-screen character dialogue requires tight lip-sync (every word matches mouth)
- Hero shots where motion naturalness on the speaker is paramount
- Short-form work where the 20-min-per-shot cost is acceptable

Both pipelines can coexist — the same `screenplay.json` works for both.

## 2. Three render modes — `--mode fast | quality | abstract`

LTX 2.3 is trained predominantly on real-world video. Each mode tunes the LoRA stack + sampler for a different content class. Pick by **what kind of video you're making**:

| Mode | Content class | Stack | Sampler | CFG | Steps |
|---|---|---|---|---|---|
| **`fast`** (default) | Narrative / character / real-world scenes | Distilled + IC-union + VBVR physics | euler | 3.0 | 20 |
| `quality` | Reference/debugging (joint AV via EROS) | EROS full + distill LoRA + IC-union + VBVR | euler | 3.0 | 20 |
| **`abstract`** | Fractals, geometry, artwork in motion, psychedelic, non-physical | NO always-on LoRAs (physics would hurt) | **euler_ancestral** | **5.0** | **30** |

Why abstract drops the physics + reference LoRAs:
- **VBVR** enforces object permanence, gravity, and collision realism — exactly wrong for a pulsing mandala or fractal unfold.
- **IC-LoRA union control** carries reference-scene semantics that don't apply to non-representational content.
- **euler_ancestral** adds stochastic variation each step, which morphs abstract content more expressively than plain euler.
- **Higher CFG (5 vs 3) + 30 steps** compensate for the distilled model's natural-video bias when asked for unfamiliar geometry.

## 2a. Model stack (all on disk, all verified)

### Fast mode (DEFAULT — `--mode fast`)

| Slot | File | Role |
|---|---|---|
| Base | `ltx-2.3-22b-distilled-fp8.safetensors` (27 GB) | Video-only distilled 22B, fp8 |
| Video VAE | `LTX23_video_vae_bf16.safetensors` | |
| Text encoder | `gemma-3-12b-abliterated-text-encoder.safetensors` | Uncensored prompt understanding |
| LoRA (always) | `ltx-2.3-22b-ic-lora-union-control-ref0.5.safetensors` @ 1.0 | Reference-based char/scene control |
| LoRA (always) | `ltx2/Ltx2.3-Licon-VBVR-I2V-96000-R32.safetensors` @ 1.0 | Physics / object permanence |

**No distilled-lora-384 in fast mode** — already baked into the checkpoint. Adding it would over-distill.

### Quality mode (`--mode quality`)

| Slot | File | Role |
|---|---|---|
| Base | `ltx2/ltx-2.3-eros.safetensors` (35 GB) | Abliterated joint audio+video EROS |
| Video VAE | same | |
| Text encoder | same | |
| Audio VAE | `LTXVAudioVAELoader(ltx2/ltx-2.3-eros.safetensors)` | Joint AV path requires this |
| LoRA | `ltx2/ltx-2.3-22b-distilled-lora-384.safetensors` @ 0.5 | Partial distill boost |
| LoRA | `ltx-2.3-22b-ic-lora-union-control-ref0.5.safetensors` @ 1.0 | |
| LoRA | `ltx2/Ltx2.3-Licon-VBVR-I2V-96000-R32.safetensors` @ 1.0 | |

Quality mode includes empty audio latent + LTXVConcatAVLatent + LTXVSeparateAVLatent in the sampler chain. We still drop the audio output (muxed from the separate audio passes). Quality mode is ~30% slower and serves mostly as a debugging reference.

## 3. Per-scene LoRA routing

Tags on a scene (or dialogue direction) route to extra LoRAs on top of the always-on stack. Substring-matched case-insensitively. Cap at 3 extras per clip to avoid model interference.

| Tag | LoRA added | Effect |
|---|---|---|
| `pose` | `ltx2/ltx23__demopose_d3m0p0s3.safetensors` @ 1.0 | Skeleton-driven motion |
| `zoomout` | `ltx2/ltx23_zoomout_z00m047.safetensors` @ 0.9 | Camera pulls back |
| `camera: dolly-left` | `ltx-2-19b-lora-camera-control-dolly-left.safetensors` @ 0.8 | Dolly motion |
| `camera: jib-down` | `ltx2/ltx-2-19b-lora-camera-control-jib-down.safetensors` @ 0.8 | Jib drop |
| `reasoning` | `ltx2/LTX2.3_Reasoning_V1.safetensors` @ 0.7 | Better causality |
| `transition` | `ltx2.3-transition.safetensors` @ 1.0 | Scene-boundary clips (auto-added) |
| `style: claymation` | `ltx2/Claymation.safetensors` @ 0.8 | Stop-motion / clay |
| `style: ghibli` | `StudioGhibli.Redmond...` @ 0.7 | Ghibli watercolor |
| `style: ghibli_offset` | `ghibli_style_offset.safetensors` @ 0.6 | Lighter Ghibli shift |
| `style: galaxy` | `ltx2/LTX23-GalaxyAce.safetensors` @ 0.9 | Cosmic / nebular / starfield |
| `style: tribal` | `Smooth_Tribal.safetensors` @ 0.7 | Ornamental / pattern-rich |
| `style: illustration` | `Illustration concept Variant 3A.safetensors` @ 0.7 | Illustrative / graphic |
| `style: cyberpunk` | `CyberPunkAI.safetensors` @ 0.8 | Neon / tech noir |
| `character: talkinghead` | `ltx-2.3-id-lora-talkvid-3k.safetensors` @ 0.8 | Face consistency on close-ups |

> **LoRA sourcing**: Camera and motion LoRAs above are HuggingFace-hosted (free, requires `HF_TOKEN` for some). The **style LoRAs** (`style: claymation` / `ghibli` / `ghibli_offset` / `galaxy` / `tribal` / `illustration` / `cyberpunk`) are **Civitai-hosted** and require a `CIVITAI_TOKEN` (set in `.env`). See `setup.sh` for the download URL pattern. All LoRAs are optional — plain prompts without these tags work without any of them.

### Style shortcut

Instead of typing the full tag, use `--style <name>`:

```bash
python movie_maker_fast.py clip --image abstract.png \
  --prompt "kaleidoscopic mandala, pulsing concentric circles, iridescent color shifts" \
  --mode abstract --style galaxy --duration 5
```

That appends `style: galaxy` to the tag list, which picks up the galaxy LoRA.

`transition` is automatically added to the last chunk of any multi-chunk scene so boundaries blend. You don't usually need to set it manually.

## 4. Image persistence & character consistency (the anti-drift toolkit)

LTX 2.3 can "wander" — the input image transforms into something unrelated over a 7 s clip, and chunks of the same scene can look like four unrelated shots spliced together. Three mechanisms, in decreasing order of impact, prevent this:

### 4.1 Last-frame carry-forward (ON by default)

For scenes auto-chunked into multiple clips, **chunk N+1 uses chunk N's last frame as its input image** instead of restarting from the original source. The `transition` LoRA (auto-added on boundary chunks) + matching seed across chunks carry the visual forward.

- `render_scene()` extracts the last frame via `ffmpeg -sseof -0.3` → `-frames:v 1` and stashes it at `input/_movie_fast_frames/<project>/scene_NNN_chunk_NN_last.png`.
- Disable with `--no-carry-last-frame` if you *want* hard-cuts between chunks (rarely useful).

This is the **single biggest lever for scene coherence** — multi-chunk scenes go from "4 unrelated shots" to a continuous arc.

### 4.2 Persistence knob (`--persistence 0..1`)

`LTXVImgToVideoInplace` has a `strength` parameter where HIGHER = more freedom to transform the input (paradoxical naming). The `--persistence` flag exposes an intuitive 0..1 scale:

| `--persistence` | i2v strength | Effect |
|---|---|---|
| unset (default) | 1.00 | Full motion freedom — LTX reinterprets the input aggressively |
| 0.3 | 0.82 | Dynamic action allowed but anchored |
| 0.5 | 0.70 | Balanced — good for most cinematic shots |
| 0.7 | 0.58 | "Hold the frame" — subtle motion only |
| 1.0 | 0.40 | Near-static; barely moves from input |

Per-scene override: add `"persistence": 0.7` to the scene dict in the screenplay.

### 4.3 Character seed stability

- `character_seed_offset("AYA", base_seed)` → stable hash-derived offset. Same name + same base_seed = same face every time.
- `focal_character(scene)` picks the first non-NARRATOR dialogue speaker (else first entry in `scene["characters"]`). The seed offset uses that name.
- All chunks of a scene share the same scene seed (`base_seed + scene_idx * 1000`), so characters don't shift appearance within a scene.

For a multi-episode series: copy the `characters` dict + `base_seed` from one episode's manifest to the next. Faces stay stable bit-for-bit.

### 4.4 What's *not yet* wired (but documented)

**IC-LoRA reference images per character** — the `LTXAddVideoICLoRAGuide` + `LTXICLoRALoaderModelOnly` node path (proven in the KJ pose-switches workflow) can take a per-character reference PNG and strongly anchor that character's appearance across every clip they're in. Always-on `ic-lora-union-control-ref0.5` is already loaded; wiring the guide image is a ~80-line addition that would supersede the seed-offset approach for strict multi-episode consistency. See Phase 2b in the tool's internal TODOs.

## 5. 7-second clip enforcement + auto-chunking

LTX 2.3 coherence degrades past ~8 s. Scenes longer than 7 s auto-split into ≤7 s chunks:

```
3.0 s  →  [3.0]                   (no split)
7.5 s  →  [7.0]                   (0.5s tail absorbed into the 7s chunk)
14.0 s →  [7.0, 7.0]              (even split)
20.0 s →  [7.0, 7.0, 6.0]         (last chunk is remainder)
23.5 s →  [7.0, 7.0, 7.0, 2.5]
```

All non-last chunks auto-get the `transition` LoRA so the xfade stitcher has smooth boundaries to work with.

## 6. Screenplay schema

Compatible with `AGENT_CINEMA_AUTOPILOT` / `produce.py` output. Minimum viable scene:

```json
{
  "title": "my_film",
  "scenes": [
    {
      "description": "A woman stands at the archive's edge, cool-lit, shallow DOF.",
      "action": "Slow push-in. She turns toward an unseen presence.",
      "source_image": "styled_film_act1/shot_003.png",
      "duration": 10.0,
      "mood": "reverent",
      "camera": "dolly-in",
      "tags": ["transition"],
      "characters": ["LYRA"],
      "dialogue": [{"character": "LYRA", "line": "Someone is here.", "direction": "tender"}]
    }
  ]
}
```

Fields used by Movie Maker Fast:

| Field | Required | Purpose |
|---|---|---|
| `source_image` / `image_path` / `image` | ✓ | Input image (relative to `input/`) |
| `prompt` / `action` / `description` | ✓ (one of) | Text prompt for LTX |
| `duration` / `duration_hint` | ✓ | Scene length in seconds; auto-chunks |
| `tags` | optional | Explicit LoRA routing tags |
| `mood` / `camera` / `style` | optional | Implicit tags (auto-prefixed `mood:` / `camera:` / `style:`) |
| `characters` | optional | First entry is focal-character fallback |
| `dialogue` | optional | First non-NARRATOR speaker drives focal character |

## 7. CLI

```bash
# Single-clip (Phase 1)
python movie_maker_fast.py clip --image styled_film_act1/shot_003.png \
  --prompt "Cinematic slow push-in..." --duration 7 --mode fast --seed 42

# Persistent character shot (holds the frame, subtle motion only)
python movie_maker_fast.py clip --image character.png \
  --prompt "She tilts her head slightly, soft breath" \
  --duration 6 --persistence 0.7 --seed 200

# Abstract content (mandala, fractal, geometric)
python movie_maker_fast.py clip --image mandala_seed.png \
  --prompt "kaleidoscopic mandala pattern, pulsing concentric circles, iridescent color shifts" \
  --duration 5 --mode abstract --style galaxy

# Full screenplay (Phase 2) — last-frame carry-forward ON by default
python movie_maker_fast.py screenplay screenplay.json --seed 42 --persistence 0.5

# Stitch clips into final film (Phase 3)
python movie_maker_fast.py stitch output/movie_fast/<project>/clips_manifest.json \
  --dialogue dialogue_master.wav --music music_bed.wav --sfx sfx_master.wav \
  --output <project>_final.mp4
```

## 8. Full production recipe

From a screenplay to a finished film:

```bash
# Step 1 — render video clips (15-40 min for a 10-min drama)
ssh ${SSH_USER}@127.0.0.1 'cd ${COMFYUI_ROOT} && python scene_production_tool\movie_maker_fast.py screenplay output\video\my_film\screenplay.json'

# Step 2 (parallel with Step 1) — produce the three audio tracks:

# 2a — Dialogue master (Qwen3-TTS Three-Lock per character)
ssh ${SSH_USER}@127.0.0.1 'cd ${COMFYUI_ROOT} && python scene_production_tool\radio_drama.py my_film --stage tts'
# This produces output/radio/my_film/audio/dialogue/line_NNN.wav
# — concatenate them in screenplay order to make dialogue_master.wav

# 2b — Music cues (ACE Step XL base via APG chain + dynamics-preserving mastering)
#     --master auto will pick "orchestral" from keywords ("cinematic", "film score")
#     → −18 LUFS target + zero saturation + full LRA preservation for emotional arcs
ssh ${SSH_USER}@127.0.0.1 'cd ${COMFYUI_ROOT} && python music_tool\music_maker.py \
  --prompt "cinematic orchestral film score, sweeping strings, sustained brass, timpani, quiet intro builds to full climax then breathes into soft outro, loud-quiet-loud dynamics, breathing room between phrases, close-mic'd" \
  --duration 180 --bpm 70 --key "A minor" --variant xl_base --master auto \
  -o output/music/my_film_bed.flac'

# 2c — SFX (MMAudio primary, SAO/ACE fallback)
# Use radio_drama.py --stage sfx with a script containing sfx_cue events
# OR invoke generate_sfx() directly for specific events

# Step 3 — Stitch video + audio into final film
ssh ${SSH_USER}@127.0.0.1 'cd ${COMFYUI_ROOT} && python scene_production_tool\movie_maker_fast.py stitch \
  output/movie_fast/my_film/clips_manifest.json \
  --dialogue output/radio/my_film/dialogue_master.wav \
  --music output/music/my_film_bed.flac \
  --sfx output/radio/my_film/sfx_master.wav \
  -o output/movie_fast/my_film/my_film_final.mp4'

# Step 4 — Pull
scp ${SSH_USER}@127.0.0.1:${COMFYUI_ROOT}/output/movie_fast/my_film/my_film_final.mp4 .
```

## 9. Audio mux details (stitcher internals)

The stitcher's filter chain uses the same sidechain-duck pattern proven in `stitch_act.py` and `radio_drama.py`:

```
All tracks → aresample to 48kHz stereo fltp → pad to video duration → volume

dialogue → speech bus → alimiter (protect against transients)
                    │
                    ├── asplit → one copy goes to final mix
                    │
                    └── other copy becomes sidechain key

music + SFX → amix → sidechaincompress (driven by speech key)
                      threshold=0.05 ratio=8 attack=20ms release=300ms

speech + ducked music/SFX → amix weights=1.0 0.8 → loudnorm I=-16:TP=-1.5:LRA=11
```

Output: **−16 LUFS integrated, −1.5 dBTP true peak, 48 kHz stereo AAC 192 kbps** (EBU R128 / podcast standard).

## 10. Render-speed reference

Measured on RTX 5090 (Blackwell), ComfyUI 0.19.3, LTX 2.3 22B distilled fp8, 832×480 @ 24 fps:

| Clip | Model status | Steps | Time | Real-time ratio |
|---|---|---|---|---|
| 3 s | cold (first load) | 20 | 81 s | 0.04× |
| 5 s | warm (EROS loaded) | 24 | 90 s | 0.06× |
| 5 s | fast-mode cold | 20 | 69 s | 0.07× |
| 7 s | fast-mode warm | 20 | **~75 s** | **~0.09×** |

For a 25-clip drama: **~32 min total render (fast mode)** vs ~5 hours for MultiTalk. **~10× speedup.**

Dimension sensitivity: 832×480 is the sweet spot. At 1280×720 expect ~1.8× longer per clip; at 512×288 ~0.6×. Stay ≤960 max-dim for interactive iteration.

## 11. Failure modes + recovery

| Symptom | Cause | Fix |
|---|---|---|
| HTTP 400 on submit with `value_not_in_list` | Path uses `/` instead of `\` on Windows; OR a model file is missing at the expected path | First, check filenames + paths against `setup.sh`. The 'ltx2/' subfolder under `models/checkpoints/` and `models/loras/` is **not optional** — keep it. Second, use `\\` in any custom lora_name / ckpt_name string. |
| **Output looks over-saturated, distorted, or "off"** | Almost always one of: (1) wrong checkpoint installed at wrong path, (2) text encoder mismatch (.gguf vs .safetensors), (3) LoRA strengths stacking too high. | See § 11a "Saturation & distortion troubleshooting" below. |
| HTTP 400 with `scheduler: 'beta57' not in [...]` | ComfyUI version doesn't have that scheduler | Use `linear_quadratic` or `beta` (tool default is `linear_quadratic`) |
| Output file not found after success | SaveVideo writes under `outputs[id]['images']` not `['videos']` | Tool checks all 3 keys — should not recur |
| Faces drift between clips | No character consistency | Pass same `--seed` + ensure `characters` dict is consistent; focal char inferred from first dialogue speaker |
| Audio clips don't align with video | Dialogue master built separately; positions drift | Use radio_drama.py's scheduler to build the dialogue track at fixed offsets matching scene timings |
| OOM on a 7 s clip | Fast mode requires ~20 GB VRAM with models warm | Reduce resolution to 768×432 or restart ComfyUI to clear cached models |
| First clip is 80+ s but subsequent ones are fast | Cold load of 27 GB checkpoint + 12 GB encoder | Normal — render one throwaway 3-s clip first to warm the cache |

## 11a. Saturation & distortion troubleshooting

If output is over-saturated, washed out, or shows obvious diffusion artifacts (scrambled faces, smeary motion, wrong colors), work through these in order — each one is a real bug or misconfig that's bitten users:

### Step 1 — Verify the right checkpoint is loaded

Open ComfyUI's `models/checkpoints/` directory. The fast-mode checkpoint must be at this **exact** path:

```
models/checkpoints/ltx-2.3-22b-distilled-fp8.safetensors
```

Common mistake: users see "ltxv-distilled" on a HuggingFace page and download `ltxv-2b-0.9.7-distilled-fp8_e4m3fn.safetensors` (an older 2024 LTXV release, ~6 GB). That model loads fine in ComfyUI but **produces saturated, distorted output** because the script feeds it an LTX 2.3-shaped latent it can't decode correctly. The fix is to download the right file from `huggingface.co/Lightricks/LTX-Video` — should be ~22 GB.

For quality mode + A2V, EROS lives at:

```
models/checkpoints/ltx2/ltx-2.3-eros.safetensors
```

(The `ltx2/` subfolder is **not optional**.)

### Step 2 — Verify the text encoder

The script loads:

```
models/text_encoders/gemma-3-12b-abliterated-text-encoder.safetensors
```

If you only have the `.gguf` quantization (`google_gemma-3-12b-it-abliterated-v2-Q6_K.gguf`), the LTX text-encoder loader will fail or use a fallback path that produces incoherent embeddings → garbage video. Get the `.safetensors` variant from the same Lightricks repo.

### Step 3 — Tune LoRA strengths

Defaults in v0.2+:

| LoRA | Default | Lower if… | Raise toward 1.0 if… |
|---|---|---|---|
| VBVR physics (`Ltx2.3-Licon-VBVR-...`) | **0.7** | Output looks plasticky / over-physical / saturated | Motion looks fake or unphysical |
| IC-LoRA Union (`ic-lora-union-control-ref0.5`) | **0.7** | Output looks too "neutral" / flat | Composition drifts wildly between frames |
| Distill assist (quality mode only) | 0.5 | (rarely needs change) | (rarely needs change) |

Override at the CLI:

```bash
python movie_maker_fast.py clip --prompt "..." \
    --vbvr-strength 0.5 \
    --ic-lora-strength 0.5 \
    -o out.mp4
```

If you got distorted output and you've verified the right checkpoint is loaded, **start by lowering both to 0.5**. That reproduces the most balanced LTX 2.3 community config.

### Step 4 — Check CFG and steps

| Mode | Default CFG | Default steps | When to adjust |
|---|---|---|---|
| `fast` | 3.0 | 20 | If output is too "loose" (drifts from prompt), raise CFG to 4.0. If saturated/burnt, lower to 2.5. |
| `quality` | 3.0 | 30 | Same. EROS is sensitive — keep CFG ≤ 4.0. |
| `abstract` | 5.0 | 30 | Higher CFG works here because abstract content benefits from prompt adherence. |

CFG > 6 with any LTX 2.3 variant produces saturated, noisy, posterized output — that's the model's signature failure mode.

### Step 5 — Check the VAE

The video VAE must be `LTX23_video_vae_bf16.safetensors` at `models/vae/`. If a wrong VAE loads (e.g., a non-LTX VAE leftover from another project), colors shift dramatically — that's a known cause of "off" output.

### Step 6 — Disable style LoRAs to isolate

Style LoRAs (`style: cyberpunk`, `style: claymation`, etc.) layer on top of always-on LoRAs. Stacking 3+ can cause distortion. Render once with no `--style` and no style tags in screenplay JSON to confirm the base pipeline is clean. Then add styles one at a time.

### Step 7 — Last resort: warm the model cache

The first clip after ComfyUI restart loads ~50 GB of weights from disk. If your disk is slow or other processes are competing for memory, the first clip's diffusion can produce unstable output. Render one throwaway 3-second clip to warm the cache, then retry your real shot.

## 11b. Cinematic scoring — making the music serve the film

Films live and die by their score's emotional arc. A flat, always-loud score kills every scene. The `music_maker.py` tool's `--master auto` will pick `orchestral` preset when you write a proper cinematic prompt — that preset targets −18 LUFS with **zero saturation and no compression**, preserving full LRA 15-25+ (classical territory). Here's how to use it well.

### Always prompt for dynamics, not density

The temptation is to describe the climax ("massive orchestral crescendo") and call it done. ACE will render a wall of sound at constant energy — useless under a scene that needs to breathe. Write the **full arc**, with explicit [section] tags:

```
[intro: solo cello in D minor, sparse, 8 bars] 
[verse: add second cello and viola, still quiet, 16 bars] 
[build: add full string section, rising tension, timpani rolls begin, 8 bars] 
[climax: full orchestra, heroic horns, choir swell, 8 bars] 
[outro: resolve to solo cello, fade to silence, 8 bars]
```

Combine with dynamics vocabulary from the music-producer skill:
- `loud-quiet-loud dynamics`, `breathing room between phrases`
- `sparse intro`, `sudden silence before climax`, `decrescendo to solo`
- `call and response between strings and brass`
- `rubato`, `tempo breathing`, `pauses`, `accelerando into drop`

**Avoid** these dynamics-killing tags for cinematic work:
- ❌ `wall of sound`, `dense mix`, `maximal`, `thick layered`
- ❌ `constant energy`, `always moving`, `never stops`
- ❌ `radio-ready`, `pop-style compression`
- ❌ `banger`, `drop`, `festival` (these push toward EDM preset and lose dynamics)

### Genre keyword → mastering preset mapping

`auto` detects the preset from your prompt. For cinema you almost always want `orchestral`:

| Include these words | Auto-picks | Target LUFS | Notes |
|---|---|---|---|
| orchestr, symphon, film score, cinematic | **orchestral** | −18 | Full transparency, zero sat, preserves 20+ LRA |
| jazz, bebop, bossa, swing, Rhodes | jazz | −15 | Whisper of warmth, near-transparent |
| lofi, ambient, meditat, chillwave | chill | −16 | Gentle, minimal processing |
| edm, dubstep, trance, house | edm | −12 | Loud, colored — **wrong for most cinema** |

If you write "epic orchestral trailer with dubstep drop", the EDM keyword wins and mastering goes loud. Either split into two cues or force `--master orchestral` to override.

### Score-per-act pattern (for multi-scene films)

For a 3-act film, generate one cue per act, not one monolithic score:

```bash
# Act 1 — introduction, sparse, mysterious
python music_maker.py \
  --prompt "[intro: solo piano, sparse, contemplative] [verse: add cello, quiet strings, 16 bars] cinematic ambient score, minimal, restrained, breathing room, nocturnal, mysterious unfolding" \
  --duration 120 --bpm 60 --key "D minor" --variant xl_base --master orchestral \
  -o output/music/act1_bed.flac

# Act 2 — rising action, tension building
python music_maker.py \
  --prompt "[build: strings enter, tempo pulses rise] [tension: dissonant brass stabs, timpani crescendo] cinematic score, loud-quiet-loud, call and response, foreboding, unstable" \
  --duration 150 --bpm 85 --key "D minor" --variant xl_base --master orchestral \
  -o output/music/act2_bed.flac

# Act 3 — climax + resolution
python music_maker.py \
  --prompt "[climax: full orchestra, heroic horns, choir] [resolution: decrescendo to solo strings, triumphant] sweeping cinematic finale, loud-quiet-loud, cathartic release, hopeful resolution" \
  --duration 180 --bpm 100 --key "E♭ major" --variant xl_base --master orchestral \
  -o output/music/act3_bed.flac
```

Then the stitcher takes one concatenated music file at mix time — or you mix per-scene with different weights. Cues in the same key + compatible tempi crossfade naturally.

### Overriding the target for louder cues

Default orchestral target is −18 LUFS (quieter than dialogue by design). If your film has no dialogue over a given cue (a montage, a silent opening), you can push it louder without losing dynamics:

```bash
python music_maker.py --prompt "..." --master orchestral --target-lufs -14 -o loud_cue.flac
```

The chain still preserves LRA; only the final gain-match lands you 4 dB louder.

### Validation

After generation, `music_maker.py` prints before/after LRA. For cinematic scoring, expect:

| Metric | Raw ACE (orchestral prompt) | After --master orchestral |
|---|---|---|
| LUFS | −10 to −13 | −18.0 ±0.2 |
| LRA | 15–25 LU | 15–25 LU (within −1) |
| TP | sometimes > 0 (clipping) | −3 to −6 dBTP (safe) |
| Crest | 6–8 | 6–9 (often +) |

If LRA lands below 10 on a score, your prompt lost the fight. Rewrite with stronger section tags + explicit `loud-quiet-loud dynamics`.

## 12. Integration with existing pipelines

All tools share conventions:

- **Screenplay JSON**: same shape as `AGENT_CINEMA_AUTOPILOT.md` / `produce.py` output. Both slow-WAN and fast-LTX pipelines consume it identically — you can generate the same film both ways for A/B.
- **Character dict**: the same Three-Lock fields (`voice`, `seed`, `emotion_overrides`) are honored by `produce.py`'s `stage_tts()` for voice continuity; this tool only reads `characters[N]` + `dialogue[N].character` for visual seed offset. So **one manifest, two kinds of consistency.**
- **Audio passes**: `radio_drama.py` produces the dialogue master; `music_maker.py` produces music; `radio_drama.py generate_sfx()` produces SFX. Stitcher muxes all three.

## 13. What's NOT yet wired (TODO list)

Listed explicitly so future agents don't re-invent:

1. **IC-LoRA reference images per character** — `LTXICLoRALoaderModelOnly` + `LTXAddVideoICLoRAGuide` nodes exist and are proven in the KJ pose-switches workflow. Wiring them into `build_ltx_i2v_workflow()` on demand (when a character has `reference_image`) would make character appearance even more stable than seed offsets alone.
2. **DWPose-driven motion** — `sdpose_wholebody_fp16` + `LTXAddVideoICLoRAGuide` can take pose sequences as motion input. Not wired.
3. **Super-resolution pass** — the VBVR_EROS workflow ends with `RTXVideoSuperResolution` (1.5x ULTRA) + `RIFE VFI` frame interpolation. Adding an optional `--upscale` flag that runs these as a post-processing pass would bring output up to 1536×832 + smooth 60 fps.
4. **Audio timeline placement** — stitcher currently treats dialogue/music/SFX as full-length masters. A timeline-aware version that places SFX at specific scene-timestamps via `adelay` would mirror `radio_drama.py`'s mix stage.
5. **Automatic dialogue master assembly** — per-line TTS WAVs need to be concatenated + timed to match scene durations. Currently manual; could be auto-derived from the `clips_manifest.json` + the dialogue_map produced by `radio_drama.py stage_tts`.

None of these block usage; the core fast-render + screenplay + stitcher loop is complete.
