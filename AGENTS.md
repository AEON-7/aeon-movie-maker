# AGENTS.md — execution runbook for AI agents

This document is **the single source of truth** for how to use
`aeon-movie-maker`. If you're an AI agent (Claude, a local LLM, or any
code-using assistant), read this top-to-bottom before executing anything.
You should not need to consult any other file.

If you finish reading and don't know what to do, **stop and ask the human**.

---

## 1. What this tool does

`aeon-movie-maker` is a Python CLI that turns text descriptions (or a
JSON "screenplay" file) into video clips. It does this by sending workflow
instructions to **ComfyUI** (a separate program already running somewhere
on the network). ComfyUI uses the **LTX 2.3 video model** to actually
generate the pixels.

**Inputs**: text prompts, optional seed images, optional screenplay JSON
**Outputs**: `.mp4` video files (with embedded audio when using Prompt Relay)
**You don't generate audio for music — that's a separate tool.** You CAN
generate dialogue with lipsync via the Prompt Relay flow.

---

## 2. Glossary — every term defined

Read this section even if you think you know the terms. Many are used
specifically here.

| Term | Definition |
|---|---|
| **ComfyUI** | The model-serving program that actually runs the video model. Reachable via HTTP, default `http://127.0.0.1:8188`. This tool talks to it; you don't run ComfyUI yourself, you just need it up. |
| **LTX 2.3** | The 22-billion-parameter text-to-video model that generates the actual pixels. Two main checkpoints: `distilled-fp8` (fast, lower fidelity) and `dev-fp8` (slower, higher fidelity). |
| **Scene** | One continuous moment in your screenplay. Has a description, duration in seconds, and optional dialogue. The smallest unit a human author writes. |
| **Sequence** (Prompt Relay only) | One forward pass through the model. Contains 1–N scenes that morph smoothly into each other. Limited to 489 frames (~20s @ 24fps) on DGX Spark. |
| **Segment** (Prompt Relay only) | The portion of a sequence corresponding to one scene. The model conditions differently on each segment of the timeline. |
| **Clip** (per-scene flow only) | The MP4 file produced for one scene in the per-scene flow. Each scene = one clip. |
| **T2V (text-to-video)** | Generate video from text only. No starting image. |
| **I2V (image-to-video)** | Generate video starting from a seed image. The first frame is constrained, subsequent frames diffuse outward. |
| **Joint A/V** | The model produces both video AND audio in the same forward pass. **Only the Prompt Relay flow does this.** The per-scene flow produces silent video. |
| **Prompt Relay** | A specific ComfyUI workflow (`PromptRelayEncodeTimeline` node) that takes multiple prompts with different time durations and morphs through them in one continuous shot. The `--use-relay` flag activates this. |
| **Lipsync** | When the model generates speech audio that matches the mouth motion of the character on screen. Triggered by writing `'CHARACTER says "line"'` patterns in the prompt (which the screenplay's `dialogue` field becomes automatically). |
| **Carry-forward** | Between Prompt Relay sequences (hard cuts), the script extracts the LAST FRAME of the previous sequence and uploads it as the SEED IMAGE for the next sequence. Maintains visual continuity across cuts. Done automatically. |
| **Wrapper prompt** | The "global anchor" prompt for a Prompt Relay sequence. Built from the screenplay's `style` + `setting` + character VISUAL DESCRIPTIONS. The strongest cross-sequence identity signal. |
| **Negative prompt** | Tells the model what NOT to generate. Crucial for suppressing model-generated music in the joint A/V output (so you can add your own score later). |
| **Hard cut** | A jarring scene change between two Prompt Relay sequences. Happens automatically when a scene's frame count would overflow the budget, or when you set `relay_break: true` / `tags: ["transition"]` on the scene. |
| **Stitch** | The `stitch` subcommand. Concatenates multiple clips into one final film and optionally muxes in dialogue + music + SFX. |

---

## 3. Decision tree — what does the user want?

Read the user's request. Pick the matching row. **Do not improvise.**

| User asked for | Do this |
|---|---|
| "Make a video clip of X" / "render a 5-second shot of X" | **Recipe A** (single clip) |
| "Make a video from this image of X" | **Recipe A** with `--image` |
| "Make a film / movie / story / multi-scene video" with multiple distinct shots | **Recipe B** (screenplay, per-scene flow) |
| "Make a film with **dialogue** / **characters speaking** / **lipsync**" | **Recipe C** (screenplay, Prompt Relay flow) |
| "Make a long continuous shot that morphs through a story" | **Recipe C** |
| "Make a film with dialogue AND a custom music score" | **Recipe D** (full production) |
| "Add music to my existing film" | **Recipe D step 3** + **Recipe D step 4** only |
| User mentions "abstract / fractal / kaleidoscope / geometric / non-realistic" | Add `--mode abstract` to whichever recipe |
| User wants to test something quickly | Use `--limit 1` (screenplay) or `--duration 3` (clip) — keeps render time low |

If the user's request doesn't fit ANY row → **stop and ask**.

---

## 4. Preconditions — verify BEFORE running anything

Run these checks. If any fail, stop and tell the human exactly what's missing.

### 4a. ComfyUI must be reachable

```bash
curl -sf -m 3 "${COMFYUI_URL:-http://127.0.0.1:8188}/system_stats" >/dev/null && echo "ComfyUI OK" || echo "ComfyUI NOT REACHABLE"
```

If "NOT REACHABLE": tell the human. They need to start ComfyUI before you
can do anything.

### 4b. ffmpeg + ffprobe must be on PATH

```bash
command -v ffmpeg && command -v ffprobe && echo "ffmpeg OK" || echo "ffmpeg MISSING"
```

If MISSING: install with `sudo apt install -y ffmpeg` (Linux/Debian) OR
`brew install ffmpeg` (macOS). Don't try to render without it — the script
will fail at the very end during file-probing.

### 4c. Python deps installed

```bash
python3 -c "import requests" && echo "requests OK" || echo "INSTALL: python3 -m pip install --break-system-packages requests"
```

`requests` is the only dependency. If missing, run the suggested install line.

### 4d. (Optional) Discover ComfyUI models

If you need to know which checkpoints / LoRAs / VAEs are loaded:

```bash
curl -sf "${COMFYUI_URL:-http://127.0.0.1:8188}/object_info" | python3 -c "import sys,json; d=json.load(sys.stdin); print(list(d.keys())[:20])"
```

You don't usually need to do this — the recipes below assume the canonical
`comfyui-aeon-spark` distribution which has every model the recipes need.

---

## 5. Recipes — copy-paste literal commands

Each recipe is one path. Pick from the decision tree, then execute the
recipe top-to-bottom. **Don't merge recipes** unless you're following
Recipe D (which composes B/C and the music tool).

### Recipe A — single clip

For one short video shot.

**Step 1: Decide T2V or I2V**
- If user gave you an image → I2V → use `--image PATH`
- If no image → T2V → use `--t2v`

**Step 2: Run**

```bash
# T2V example
python scripts/movie_maker_fast.py clip \
  --t2v \
  --prompt "A fox walking through morning mist in a pine forest, drone shot from above" \
  --duration 5 \
  --output forest_fox.mp4

# I2V example (image must be in ComfyUI's input/ dir, path is RELATIVE to that)
python scripts/movie_maker_fast.py clip \
  --image my_image.png \
  --prompt "Camera pushes in slowly, the figure turns and smiles" \
  --duration 5 \
  --output portrait_motion.mp4
```

**Step 3: Verify output**

```bash
[ -f OUTPUT.mp4 ] && ffprobe -v error -show_entries format=duration OUTPUT.mp4 && echo OK || echo "FAILED"
```

The duration should be close to (within 0.5s of) what you requested. If
the output is missing or 0 bytes → check the script's stderr for the
error and find it in §7 below.

---

### Recipe B — screenplay, per-scene flow

For multi-scene films where each scene gets its own clip and you'll add
audio later via the `stitch` subcommand.

**Step 1: Have a screenplay JSON ready**

Format (minimum viable):

```json
{
  "title": "my_film",
  "scenes": [
    {
      "description": "A woman opens a door into a bright kitchen, morning light",
      "duration": 5.0,
      "source_image": "kitchen_door.png"
    },
    {
      "description": "She walks to the counter and lifts a teapot",
      "duration": 5.0,
      "source_image": "kitchen_door.png"
    }
  ]
}
```

`source_image` paths are relative to ComfyUI's `input/` directory.

**Step 2: Run**

```bash
python scripts/movie_maker_fast.py screenplay my_film.json \
  --output-dir output/movie_fast/my_film
```

This produces ONE mp4 per scene plus a `clips_manifest.json`.

**Step 3: Verify**

```bash
ls output/movie_fast/my_film/*.mp4 | wc -l   # should equal number of scenes
[ -f output/movie_fast/my_film/clips_manifest.json ] && echo "manifest OK"
```

**Step 4 (optional): Stitch with audio**

If user provides dialogue/music/SFX wav files:

```bash
python scripts/movie_maker_fast.py stitch output/movie_fast/my_film/clips_manifest.json \
  --dialogue dialogue.wav \
  --music music.wav \
  --sfx sfx.wav \
  -o my_film_final.mp4
```

---

### Recipe C — screenplay, Prompt Relay flow (with dialogue + lipsync)

For films where you want characters to SPEAK with audible dialogue and
lipsynced mouth motion. The Prompt Relay flow generates joint A/V — video
and audio in the same forward pass.

**Step 1: Write the screenplay JSON with dialogue**

This is the most important step for quality. Read carefully:

```json
{
  "title": "my_dialogue_film",
  "style": "cinematic, photorealistic faces, golden hour lighting",
  "setting": "a sunlit cafe with wooden tables and brass fixtures",

  "characters": {
    "ANNA": "A woman in her thirties with shoulder-length brown hair, freckles, wearing a navy linen blouse, warm expressive eyes",
    "BEN": "A man in his thirties with short black hair, neatly trimmed beard, wearing a grey wool sweater, calm focused gaze"
  },

  "negative_prompt": "music, background music, soundtrack, score, instruments, drums, melody, instrumental, ambient music, deformed, mutilated, extra limbs, malformed face, blurry, low quality, watermark",

  "scenes": [
    {
      "description": "Anna sits at the cafe table, hands wrapped around a steaming coffee cup, looking out the window",
      "duration": 5.0,
      "characters": ["ANNA"],
      "dialogue": [
        {"character": "ANNA", "line": "I wasn't sure you'd come."}
      ]
    },
    {
      "description": "Ben sits down across from Anna, leans forward, after speaking he reaches for his own cup",
      "duration": 5.0,
      "characters": ["BEN", "ANNA"],
      "dialogue": [
        {"character": "BEN", "line": "Of course I came. I always come."}
      ],
      "tags": ["transition"]
    }
  ]
}
```

**Critical rules** (the difference between good and bad output):

1. **`characters` MUST be a dict mapping NAME → DESCRIPTION**, not a list.
   Names alone don't anchor identity — the visual description is what
   keeps characters consistent across sequences.

2. **`negative_prompt` at the top level should suppress music.**
   Without it, the model adds its own music bed which fights with any
   score you'd compose later. Use the exact list above as a starting
   point.

3. **Each dialogue line should have its own scene** (or its own segment
   within a sequence). DON'T pack 2 exchanges into one scene — the model
   needs ~2-3 seconds of segment time per spoken line for clean audio.

4. **End the LAST scene of each sequence with visual action AFTER the
   dialogue line** ("She lifts her cup and sips" / "He looks toward the
   window"). This gives the model time to land the audio cleanly within
   the segment's frame budget. Without this, dialogue can clip at the
   segment boundary.

5. **Use `tags: ["transition"]`** on scenes that should start a new
   sequence (i.e., a hard cut to a different time/location/character
   entrance). Within a sequence the model morphs smoothly; between
   sequences there's a hard cut.

**Step 2: Run**

```bash
python scripts/movie_maker_fast.py screenplay my_dialogue_film.json \
  --use-relay \
  --output-dir output/movie_fast/my_dialogue_film
```

This produces ONE mp4 per sequence (NOT per scene) plus a
`relay_manifest.json`.

**Step 3: Concatenate the sequences into one film**

Use the `concat-relay` subcommand (smoother than raw ffmpeg concat):

```bash
# Hard cuts (fastest — instant, just remuxes; no quality loss)
python scripts/movie_maker_fast.py concat-relay \
  --input-dir output/movie_fast/my_dialogue_film \
  -o output/movie_fast/my_dialogue_film/MY_DIALOGUE_FILM.mp4

# OR with crossfade dissolves at sequence boundaries (requires re-encode,
# but eliminates jarring jump-cuts. 0.5-1.0 sec is typical; default 0.0)
python scripts/movie_maker_fast.py concat-relay \
  --input-dir output/movie_fast/my_dialogue_film \
  --xfade 0.8 \
  -o output/movie_fast/my_dialogue_film/MY_DIALOGUE_FILM.mp4

# OR also write a yuv444p10le master sibling for color grading / archival
python scripts/movie_maker_fast.py concat-relay \
  --input-dir output/movie_fast/my_dialogue_film \
  --xfade 0.8 --master \
  -o output/movie_fast/my_dialogue_film/MY_DIALOGUE_FILM.mp4
# → produces both MY_DIALOGUE_FILM.mp4 (yuv420p, universal playback)
#   and MY_DIALOGUE_FILM_master.mp4 (yuv444p10le, archival/grading source)
```

**Important: `--master` does NOT mean HDR.** It produces a master copy with
full-color resolution (4:4:4) and 10-bit depth — useful as a source for
further editing or color grading. The underlying LTX 2.3 output is SDR
(BT.709-like) regardless of which output you pick. True HDR requires a
model trained for HDR-aware output (none currently exist).

The final mp4 has dialogue audio embedded.

**Step 4: Verify**

```bash
# Should have audio AND video
ffprobe -v error -show_entries stream=codec_type MY_DIALOGUE_FILM.mp4 -of csv=p=0
# Expect output containing both "video" and "audio"
```

If only `video` shows, something dropped the audio track. Check the
per-sequence mp4s — each should be h264 + aac.

---

### Recipe D — full production (dialogue + custom music)

This is Recipe C plus a custom-composed music score muxed underneath the
dialogue. Use this when the user wants a "real" cinematic film.

**Step 1: Render the dialogue film** — follow Recipe C entirely. The
top-level `negative_prompt` in the screenplay is critical here — it
suppresses the model's bundled music so it doesn't fight with your score.
For multi-sequence films, use `concat-relay --xfade 0.8` (Recipe C step 3)
to smooth the boundaries — hard cuts between sequences are jarring without
crossfade.

**Step 2: Get the film duration** — you need this exact number for the
music render:

```bash
ffprobe -v error -show_entries format=duration -of csv=p=0 MY_DIALOGUE_FILM.mp4
# Example output: 52.270020
```

Round to a whole second — that's your music duration.

**Step 3: Compose the score with `aeon-music-maker`** (sister repo, must
be installed separately):

```bash
# Replace <duration> with the integer seconds from step 2
# Replace the prompt with text matching YOUR film's mood + length
python scripts/music_maker.py \
  --prompt "Cinematic ambient score, gentle piano + cello + warm pads, no drums, no percussion, breathing room between phrases. [intro: solo piano, 8 seconds] [verse: cello joins softly, 12 seconds] [bridge: warm pads enter, 10 seconds] [build: strings rise, 12 seconds] [outro: resolves to solo piano, fades, 10 seconds]" \
  --duration 52 \
  --bpm 60 \
  --variant xl_turbo \
  --master orchestral \
  -o output/music/my_dialogue_film_score.flac
```

The `[section: ... N seconds]` tags are critical — they tell the music
model when to swell, when to breathe, when to resolve. Map the section
durations to your FILM's emotional beats (intro = lost/quiet,
build = revelation, outro = resolution).

**Step 4: Mux dialogue + score together**

```bash
ffmpeg -i MY_DIALOGUE_FILM.mp4 -i output/music/my_dialogue_film_score.flac \
  -filter_complex "[0:a]volume=1.0[a0];[1:a]volume=0.28[a1];[a0][a1]amix=inputs=2:duration=first:dropout_transition=0[a]" \
  -map 0:v -map "[a]" \
  -c:v copy -c:a aac -b:a 192k \
  MY_DIALOGUE_FILM_with_score.mp4
```

`volume=0.28` keeps the music at 28% so the dialogue stays intelligible.
Bump to 0.35 if music feels too thin under speech, drop to 0.20 if
speech intelligibility suffers.

**Step 5: Verify**

```bash
# Confirm video + audio + reasonable size
ls -lh MY_DIALOGUE_FILM_with_score.mp4
ffprobe -v error -show_entries stream=codec_type,codec_name,duration -of compact=p=0 MY_DIALOGUE_FILM_with_score.mp4
```

You should see one h264 video stream + one AAC audio stream, both with
duration matching your input. If no audio stream → the mux dropped it,
re-run step 4 and check the ffmpeg output for warnings.

---

## 6. How long things take (so you can estimate)

Numbers from validated runs on NVIDIA DGX Spark. Other hardware will be
proportional.

| Operation | Time per output second |
|---|---|
| `clip` (Recipe A), fast mode | ~3–5 s wall per s of output video |
| `screenplay` per-scene (Recipe B) | ~5–8 s wall per s of output video |
| `screenplay --use-relay` (Recipe C) | ~6–8 s wall per s of output video, plus ~30s startup |
| `aeon-music-maker` xl_turbo | ~1–2 s wall per s of output music |
| `ffmpeg` mux (any) | <10 s total regardless of length |

For a 60-second film via Recipe D (Prompt Relay + music):
- Render: ~7–9 minutes
- Music: ~1–2 minutes
- Mux: 5 seconds
- **Total: ~10 minutes**

Tell the human the estimate before kicking off long renders. If they
want shorter, suggest `--limit N` to render only the first N scenes for
testing.

---

## 7. Common errors → exact fix

When a recipe fails, find the symptom in the LEFT column. Run the EXACT
command in the RIGHT column.

| Symptom (look in script output / stderr) | Fix |
|---|---|
| `python: command not found` | Use `python3` instead. The script supports it: `python3 scripts/movie_maker_fast.py ...` |
| `ImportError: No module named 'requests'` | `python3 -m pip install --break-system-packages requests` |
| `urllib.error.URLError: [Errno 111] Connection refused` connecting to ComfyUI | ComfyUI isn't running. Tell the human. Don't try to start it yourself unless they ask. |
| `Failed to validate prompt for output ...: Required input is missing: <name>` | A model file or workflow node is missing in ComfyUI. Tell the human, include the missing input name. They need to install the missing model or fix the workflow. |
| `Value not in list: <model_name>.safetensors not in [...]` | A specific model file isn't downloaded in ComfyUI. The user needs to fetch it (usually via `comfyui-aeon-spark`'s `download_models.py` or manually). Tell them the missing filename. |
| `ERROR: no output video file found in history` | The render succeeded but the script couldn't locate the output mp4. Check `ComfyUI/output/movie_fast/` directly with `find`. The file is almost certainly there — copy it manually. (This is a known bug in older script versions.) |
| Script hangs at "generating..." for >10 minutes | First clip after ComfyUI startup loads ~50 GB of weights from disk. Wait. After 15 min with no progress: tell the human, ask if ComfyUI's logs show anything. |
| Output video is black / corrupt / wrong duration | Check the script's banner for the actual model + step count it used. If steps < 8 or model is wrong, add explicit `--mode fast` (or `quality`) to the command. |
| Output dialogue audio is just ambient noise (no speech) | The screenplay scenes lack dialogue. Add `dialogue: [{"character": "X", "line": "..."}]` to scenes. |
| Output has music when you wanted no music | The screenplay's top-level `negative_prompt` doesn't suppress music. Add the music vocabulary from Recipe C step 1 critical rule #2. |
| Output characters look mutilated / extra limbs / wrong faces | (a) Add stronger anatomy negatives to top-level `negative_prompt`. (b) Verify each character has a detailed VISUAL description in the `characters` dict. (c) If still bad, escalate to non-distilled model: this requires editing `movie_maker_fast.py` MODES dict — beyond agent scope, ask the human. |
| Last dialogue line cut off at end of sequence | (1) **Make sure the script is at HEAD** — pre-2026-05-04 versions had an audio-frame-budget bug where audio_frames was set equal to video_frames, but they're at different rates (24fps video vs 25Hz audio codec). Fixed in 5/4 commit; bumps audio frames by ~4% at 24fps so lines land cleanly. (2) Also add visual action AFTER the dialogue in the LAST scene of each sequence (e.g. `"After speaking, she sips her tea slowly"`) — model needs ~300-500ms of "tail" to land each line. |
| Final mp4 plays in some apps but errors with "Unsupported encoding settings" / refuses to open | The xfade or any libx264 re-encode defaulted to **yuv444p / High 4:4:4 Predictive** profile (most consumer players reject this). Re-run with explicit `-pix_fmt yuv420p -profile:v high -level 4.0 -movflags +faststart`. The `concat-relay` subcommand sets these correctly by default for the distribution output. |
| Want to save a master / archival copy alongside the distribution mp4 | Use `concat-relay --master` — also writes a `<basename>_master.mp4` in yuv444p10le (full color + 10-bit depth) suitable for color grading or further compositing. **Note: this is NOT HDR**, just higher-fidelity SDR. The model output is SDR regardless of encoding choice. |
| User asks for "HDR output" | Politely explain: LTX 2.3 is SDR-trained. The model's output is in SDR color space (~BT.709). Encoding to yuv420p10le or yuv444p10le doesn't add HDR data — it just preserves more of the model's existing 8-bit-equivalent dynamic range. True HDR (BT.2020 + PQ/HLG transfer + 10-bit) requires an HDR-trained model, which doesn't exist for video diffusion yet. Offer master/dist split (`concat-relay --master`) as the closest alternative. |
| `OSError: [Errno 28] No space left on device` | Tell the human their disk is full. Don't try to clean up files yourself. |
| `OOM` / `out of memory` from ComfyUI | Tell the human ComfyUI ran out of GPU memory. They may need to restart ComfyUI or close other GPU programs. |

If your symptom is NOT in this table → **stop and ask the human**. Include:
- The exact command you ran
- The last 30 lines of script output
- Whether the script exited cleanly or hung

---

## 8. When to stop and ask the human

Stop and ask BEFORE running anything if:

1. **The decision tree (§3) doesn't match what the user asked.** Don't
   guess which recipe to use.
2. **A precondition (§4) failed.** Don't try to install ComfyUI or
   reconfigure the system.
3. **The user provided incomplete inputs** (e.g., asked for I2V but no
   image; asked for dialogue but no character names; asked for "make a
   film" without saying about what).
4. **A render would take > 30 minutes wall time** based on §6 estimates.
   Confirm before kicking it off.
5. **You'd need to write more than 10 dialogue lines or 15 scenes** to
   fulfill the request. Confirm the scope first.

Stop and ask AFTER something fails if:

6. **The error symptom isn't in §7.**
7. **Two consecutive recipe attempts failed** with different errors.
8. **You'd need to escalate model config** (non-distilled checkpoint,
   higher steps, etc.) to fix quality. That's a human-judgment call.

---

## 9. Output convention — how to report back

When reporting completion to the human (or a parent agent):

```
DONE — <recipe letter>
- output: <absolute path to final mp4>
- duration: <seconds>
- size: <MB>
- streams: <video codec> + <audio codec or "no audio">
- render time: <seconds wall>
```

When reporting failure:

```
FAILED at step <N> of recipe <letter>
- last command: <what you ran>
- error: <exact error message, last line>
- script output (last 20 lines):
  ...
- request: <what you'd need from the human to proceed>
```

Don't hide failures by silently retrying. If recipe step 2 errored,
report it; don't move on to step 3 hoping things resolve.
