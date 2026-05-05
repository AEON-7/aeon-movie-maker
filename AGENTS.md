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

### 4e. (Required for Recipe D) `aeon-music-maker` sister repo

Music score generation in Recipe D **depends on the sister repo
`aeon-music-maker`** (https://github.com/AEON-7/aeon-music-maker). It wraps
ACE Step 1.5 XL with the correct ComfyUI workflow nodes (DualCLIPLoader +
ModelSamplingAuraFlow + TextEncodeAceStepAudio1.5 — the v1.5 variants;
using the wrong node names produces noise, see "Common errors") plus a
dynamics-preserving mastering chain (HPF → EQ → tape sat → LUFS → true peak).

```bash
# If not already present:
git clone https://github.com/AEON-7/aeon-music-maker.git /path/to/aeon-music-maker
cd /path/to/aeon-music-maker
./setup.sh                 # checks ComfyUI, fetches missing ACE-Step models
```

Verify it can call your ComfyUI:
```bash
COMFYUI_URL=http://localhost:8188 python3 /path/to/aeon-music-maker/scripts/music_maker.py --help
```

**Don't roll your own ACE-Step ComfyUI workflow.** It uses `ModelSamplingAuraFlow`
(NOT `ModelSamplingSD3`), `EmptyAceStep1.5LatentAudio` (not the non-`1.5`
variant), `TextEncodeAceStepAudio1.5`, and `DualCLIPLoader` with both
`qwen_0.6b_ace15.safetensors` AND `qwen_4b_ace15.safetensors`. Distilled
`xl_turbo` requires CFG 1.0 + 10 steps (not 5/50). Get any of these wrong
and the output is garbled noise. `aeon-music-maker` handles all of this.

ACE-Step 1.5 caps at **~240 seconds per generation**. Films longer than
that need cue-based composition (multiple short pieces concatenated with
crossfade) — see Recipe D Step 3.

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

4. **Match scene `duration` GENEROUSLY to dialogue length.**
   The empirically-validated formula from `the_prince_of_two_threads`
   production: **`duration ≥ word_count + 2 seconds`**, minimum 5s.
   That's roughly **2× the spoken time** (LTX needs visual setup
   before the line, the line itself, plus breath/reaction beats after).
   Earlier guidance based on `0.5 × words + 1.5s` was too conservative —
   it led to mid-word truncation on the long Ahura Mazda speeches.

   | dialogue | words | `duration` | actual outcome |
   |---|---|---|---|
   | "What is this?" | 3 | 5 s | clean |
   | "How many died this morning?" | 5 | 6 s | clean |
   | "Then I will go to the fire tonight. Alone." | 9 | 8 s | clean |
   | "Three hundred more in the eastern provinces, my lord. The wells run black." | 13 | 11 s | clean |
   | "His own struggle has powered the bloom. The first fruit. For the first who suffered." | 15 | 12 s | clean |
   | "Two threads woven on one loom. The Lie has touched you, but you have not yet broken." | 18 | 16 s | clean |
   | "Walk with me, prince. We will seal him forever in the tree that was made before the abyss." | 19 | 17 s | clean |
   | "He fears the tree. The crystal is older than the abyss. Lead him there. Make him follow you in." | 19 | 16 s | clean (was truncated to "Make of." at duration 5 s) |

   The chunker's per-sequence frame budget is **489 frames @ 24fps =
   20.4 s max**, so single-scene durations up to ~18 s work fine.
   Beyond that, split the line across two consecutive scenes within
   the same sequence (no `transition` tag between them — the relay
   morphs smoothly):
   ```json
   {"description": "...", "duration": 8.0,
    "dialogue": [{"character": "X", "line": "First half of a very long line."}]},
   {"description": "...continuing action...", "duration": 12.0,
    "dialogue": [{"character": "X", "line": "Second half of the very long line."}]}
   ```
   Failing this, LTX **truncates the dialogue mid-word** at the
   segment boundary — and there's no fix in post (the audio simply
   isn't there).

5. **Enrich descriptions with explicit pre/post-dialogue action cues**
   when bumping duration past 6-7s. Without action beats, the longer
   scene reads as a static character holding still while the dialogue
   plays, which feels lifeless. The pattern that works:

   ```json
   {
     "description": "Medium two-shot. Ahura Mazda kneels gracefully to Darius's eye level, his radiant figure haloed by the column of golden light. The flame on the altar burns steady and bright. Before speaking, he raises a hand of light and gestures at Darius's transformed shoulder. After speaking with gentle authority, he places a hand of light on Darius's transformed shoulder — the obsidian skin softens to a faint amber glow under the touch, then the darkness slowly reclaims it as Darius bows his head",
     "duration": 16.0,
     "dialogue": [{"character": "AHURA_MAZDA", "line": "Two threads woven on one loom. The Lie has touched you, but you have not yet broken."}]
   }
   ```
   Three structural beats inside the description:
   - **Setup** (visual context before the line): "kneels gracefully...the flame burns steady..."
   - **Pre-dialogue trigger** ("Before speaking, he raises a hand of light..."): primes the speaker
   - **Post-dialogue reaction** ("After speaking with gentle authority, he places a hand..."): fills the buffer
   This anchors the model's motion through the longer duration so the
   character moves naturally during pauses.

6. **End the LAST scene of each sequence with visual action AFTER the
   dialogue line** ("She lifts her cup and sips" / "He looks toward the
   window"). This gives the model time to land the audio cleanly within
   the segment's frame budget. Without this, dialogue can clip at the
   segment boundary.

7. **Use `tags: ["transition"]`** on scenes that should start a new
   sequence (i.e., a hard cut to a different time/location/character
   entrance). Within a sequence the model morphs smoothly; between
   sequences there's a hard cut.

8. **Scene-level narrator interjections in dialogue-less scenes are
   a known phenomenon.** LTX's joint A/V audio head sometimes
   generates ambient narrator-style speech in dialogue-less sequences,
   drawing the words from the scene description itself. Two failure
   modes seen in production:
   - **Atmospheric narration that adds context** — usually good,
     leave as-is. Example from `the_prince_of_two_threads`: "From the
     roots of the crystal tree in time, and of dying, amaze."
   - **Nonsense gibberish** — sometimes the model produces non-English
     or word-salad. Example: "The foot of Crystal Threizoud of Time
     of Papyrus Hamdings." These should be muted post-hoc.

   Both cases are detected via per-sequence ASR transcription. See
   the **Step 3.5 (audio cleanup)** section below for the full workflow
   + drop-in scrubber tool.

9. **The screenplay's `title` field will NOT be voiced.** As of v0.5,
   `_build_sequence_wrapper` deliberately omits the title from the
   positive prompt — earlier versions had a bug where LTX read the
   `Film "<title>"` text aloud as a narrator title-card interjection
   ("The Prince of Two Threads") at silent sequence boundaries. The
   fix lives in the wrapper, not the screenplay format. Just write a
   normal title.

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
# RECOMMENDED for dialogue-heavy films — preserves every word at sequence
# boundaries. xfade > 0 will acrossfade audio between sequences, which
# clips dialogue tails / heads if a sequence ends or starts on a spoken line.
python scripts/movie_maker_fast.py concat-relay \
  --input-dir output/movie_fast/my_dialogue_film \
  --xfade 0 \
  -o output/movie_fast/my_dialogue_film/MY_DIALOGUE_FILM.mp4

# OR with crossfade dissolves at sequence boundaries (use ONLY for films
# with no dialogue at sequence edges — e.g., music videos, abstract pieces.
# 0.5-1.0s is typical. The crossfade will eat audio on both sides.)
python scripts/movie_maker_fast.py concat-relay \
  --input-dir output/movie_fast/my_dialogue_film \
  --xfade 0.8 \
  -o output/movie_fast/my_dialogue_film/MY_DIALOGUE_FILM.mp4

# Add --master to also write a yuv444p10le sibling for color grading / archival
python scripts/movie_maker_fast.py concat-relay \
  --input-dir output/movie_fast/my_dialogue_film \
  --xfade 0 --master \
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

**Step 3.5: Audio cleanup (optional but recommended)**

LTX 2.3's joint A/V audio head occasionally generates unwanted speech in
dialogue-less sequences (atmospheric scene-description-as-narration that
ranges from "actually nice" to "complete word-salad gibberish"). The
clean-room workflow:

1. **ASR-transcribe each per-sequence MP4** with a Whisper-compatible
   server (we use `qwen3-asr-server` on port 8001):
   ```bash
   for mp4 in output/movie_fast/MY_FILM/sequence_*.mp4; do
       ffmpeg -hide_banner -loglevel error -y -i "$mp4" \
           -vn -ac 1 -ar 16000 -sample_fmt s16 /tmp/probe.wav
       text=$(curl -s http://localhost:8001/v1/audio/transcriptions \
           -F "file=@/tmp/probe.wav" -F "model=qwen3-asr" -F "response_format=text" \
           | python3 -c "import sys,json;print(json.load(sys.stdin).get('text','').strip())")
       echo "$(basename $mp4): $text"
   done
   ```

2. **Compare transcripts to your scripted dialogue.** For each sequence,
   the ASR output should match the screenplay's `dialogue` lines for that
   sequence. Anything else is a hallucination — could be:
   - **Long dialogue truncated mid-word** ("...Make of." instead of
     "Make him follow you in") → fix by bumping the scene `duration`
     and re-rendering that sequence (see rule 4 above).
   - **Atmospheric narrator interjection** (e.g. "From the roots of the
     crystal tree...") → usually keep as-is, adds context to silent
     visual passages.
   - **Word-salad gibberish** (e.g. "The foot of Crystal Threizoud of
     Time of Papyrus Hamdings.") → mute that whole sequence's audio.

3. **Mute unwanted sequences** with a clean ffmpeg pass (video stream
   copied untouched, audio re-encoded with `volume=0`):
   ```bash
   in=output/movie_fast/MY_FILM/sequence_023_seedXXXX.mp4
   tmp=${in%.mp4}_muted.mp4
   ffmpeg -hide_banner -loglevel error -y -i "$in" \
       -c:v copy -af "volume=0" -c:a aac -b:a 192k \
       -movflags +faststart "$tmp"
   mv "$tmp" "$in"
   ```
   For surgical mute of just a time-range (e.g. first 2s of a sequence
   that has "Title Phrase X" leakage at the start), use the `enable`
   expression on the `volume` filter:
   ```bash
   ffmpeg -i "$in" -c:v copy \
       -af "volume=enable='between(t,0,2.0)':volume=0" \
       -c:a aac -b:a 192k -movflags +faststart "$tmp"
   ```

4. **Re-run `concat-relay`** after cleanup so the muted sequences are
   incorporated into the final film. Always work on the per-sequence
   MP4s; never edit the concatenated film directly (no way to
   re-render parts of a baked file).

5. **ASR-verify the muted sequences are silent** — qwen3-asr will return
   short hallucination tokens like `"Hoy."` or `"No."` on truly silent
   input (the model fills empty audio with random short artifacts).
   Combine with an `astats` RMS check: `RMS_level=-inf` confirms true
   silence.

This workflow is what eliminated all leakage from `the_prince_of_two_threads`
v2 production. The wrapper-level title-omission patch (rule 9) prevents
the most common leak; per-sequence ASR + selective mute handles the
remainder.

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

Recipe C plus a custom-composed cinematic score muxed underneath the
dialogue, plus per-sequence dialogue normalization for consistent vocal
levels across the film. Use this when the user wants a "real" film.

**Prerequisite:** `aeon-music-maker` installed and reachable (see 4e).

#### Step 1: Render the dialogue film
Follow Recipe C entirely. Critical for music compatibility:
- The top-level `negative_prompt` suppresses LTX's bundled music
- Use `concat-relay --xfade 0` (Recipe C Step 3) for hard cuts — preserves
  every dialogue word at sequence boundaries

#### Step 2: Identify pivotal beats and design the cue map

This is the make-or-break creative step. **Don't generate one giant
~5-min track** — that's the temptation but it gives you a generic
soundscape that doesn't follow the film's emotional arc. Instead:

1. **Get the per-sequence runtime** — the chunker's output (printed by
   movie_maker_fast.py during render) lists each sequence's duration:
   ```
   seq 0: scenes [0..1] (2 scenes, 202 frames ≈ 8.4s) 
   seq 1: scenes [2..4] (3 scenes, 363 frames ≈ 15.1s) 
   ...
   ```
   Compute cumulative times to map sequences onto the film timeline.

2. **Find pivot points.** A pivot is a moment where the music's
   character SHOULD change. Look for:
   - **Visual hard cuts** (any scene with `tags: ["transition"]` is a
     potential cue boundary — it's where the screenwriter wanted a beat
     change)
   - **Character entrances** — the divine/villain shows up
   - **Tonal flips** — dread → revelation, hope → defeat, struggle → renewal
   - **Silence before climax** — natural place to drop into a quieter cue
     so the loud cue lands harder
   - **Time-stop / supernatural moments** — these almost always need
     their own brief musical idea

3. **Build the cue map.** Group consecutive sequences that share a mood
   into one cue, **bounded by pivots**. Aim for **5-10 cues** per film:
   - Too few (≤3): generic, wallpaper-y
   - Too many (≥12): jittery, no theme can develop

   For each cue, note:
   | field | example |
   |---|---|
   | timeline | 90-145s (covers SEQ 7-10) |
   | duration | 55s |
   | beat | "Divine arrival + covenant formation" |
   | dynamics | "starts ethereal, swells with FRASHOKERETI theme intro" |
   | bpm | 64 |
   | key | D minor → F major brief sunrise |
   | seed | 729185 (one per cue, sequential for tonal continuity) |

4. **Identify the through-line theme.** Pick ONE recurring melodic
   identity (we called ours "FRASHOKERETI THEME" after the
   Zoroastrian renovation concept). The theme:
   - Hints in the early cues (incomplete, in the bass)
   - Emerges fully at the first big revelation cue
   - Gets transformed in middle cues (doubt, conflict)
   - Resolves triumphant in the final cue
   This through-line is what binds 10 separate generations into ONE score.

#### Step 3: Generate one cue at a time

For each cue, write a focused prompt with `[section: ...]` tags and call
`aeon-music-maker`. Use these conventions for cohesion across cues:

- **Same instrument palette** in every prompt (e.g., for our Persian
  score: ney, santoor, oud, qanun, kamancheh, daf, tombak, setar +
  bowed bass) — even if a particular cue only foregrounds 2-3 of them
- **Same tonic anchor** (we used D throughout, with modulations per cue
  as the arc demanded)
- **Sequential seeds** (e.g., 729183, 729184, 729185, ...) — this gives
  the model a similar starting point per cue, which keeps the sonic
  character broadly continuous
- **Same `--master` preset** (e.g., `orchestral` for cinematic) —
  ensures consistent loudness target across all cues
- **Same `--variant`** (we use `xl_turbo` for iteration speed; `xl_base`
  for max fidelity if you have the model and patience)
- **Each cue duration = zone_duration + 2s** — the extra 2s is the
  trailing tail that crossfades into the next cue. Last cue gets no
  extra (it's the final fade-out).

```bash
# Example: cue 3 (Divine Majesty + Covenant), 55s zone + 2s tail = 57s
COMFYUI_URL=http://localhost:8188 python3 /path/to/aeon-music-maker/scripts/music_maker.py \
    --prompt "$(cat cue3_prompt.txt)" \
    --duration 57 \
    --bpm 64 \
    --key "D minor" \
    --variant xl_turbo \
    --master orchestral \
    --seed 729185 \
    -o output/music/cue3.flac
```

The `--prompt` text should describe the FULL cue arc with section tags:
```
[intro — column of golden light descends, santoor shimmers in cascading
harmonics, qanun ornaments rise and fall like wind, distant warm oud
arpeggios, key of D minor, 64 bpm]

[verse — Ahura Mazda speaks gently, full ney lead in aeolian mode rises
with dignified melody, warm oud arpeggios underneath in D minor, qanun
glissandos add divine sparkle]

[chorus — THE FRASHOKERETI THEME emerges — a hopeful determined melody
in the ney soaring over the orchestra, distant ritual daf heartbeat
enters at 64 bpm, the covenant is being formed, key lifting briefly to
F major like a sunrise]

[outro — the FRASHOKERETI theme settles, ney holds a sustained note of
promise, daf heartbeat steady, anticipating the journey ahead]
```

**Watch out**: ComfyUI's `SaveAudioMP3` node auto-increments file suffixes.
A regenerated `cue7` saved with prefix `cue7_v2` becomes
`cue7_v2_00001_.mp3`, not `cue7_00002_.mp3`. **Concat scripts using a
hard-coded `cue7_00001_.mp3` will pick up the OLD file.** Either delete the
old file before regenerating, or rename the new file to the canonical name
afterward (the workflow we use):

```bash
# After regenerating cue7 with a different prefix:
rm /path/to/output/audio/music_maker/cue7_00001_.mp3
mv /path/to/output/audio/music_maker/cue7_v2_00001_.mp3 \
   /path/to/output/audio/music_maker/cue7_00001_.mp3
```

#### Step 4: Concatenate cues with crossfades

Chain `acrossfade` for smooth transitions, pad/trim to film duration:

```bash
ffmpeg -y \
    -i cue1.mp3 -i cue2.mp3 -i cue3.mp3 \
    -i cue4.mp3 -i cue5.mp3 -i cue6.mp3 \
    -i cue7.mp3 -i cue8.mp3 -i cue9.mp3 \
    -filter_complex "
        [0:a][1:a]acrossfade=d=2:c1=tri:c2=tri[m1];
        [m1][2:a]acrossfade=d=2:c1=tri:c2=tri[m2];
        [m2][3:a]acrossfade=d=2:c1=tri:c2=tri[m3];
        [m3][4:a]acrossfade=d=2:c1=tri:c2=tri[m4];
        [m4][5:a]acrossfade=d=2:c1=tri:c2=tri[m5];
        [m5][6:a]acrossfade=d=2:c1=tri:c2=tri[m6];
        [m6][7:a]acrossfade=d=2:c1=tri:c2=tri[m7];
        [m7][8:a]acrossfade=d=2:c1=tri:c2=tri[merged];
        [merged]apad=pad_dur=1,atrim=end=$FILM_DURATION,afade=t=out:start_time=$((FILM_DURATION-2)).5:duration=2.5[final]
    " \
    -map "[final]" \
    -c:a flac -ar 48000 \
    PRINCE_SCORE.flac
```

Math reminder: `final = sum(cue_durations) - (N-1) * crossfade_duration`.
With 9 cues × ~30-50s each + 8 × 2s acrossfades, easy to land within
1-2s of the film duration; `apad` + `atrim` + `afade` clean up the tail.

**Always force `-ar 48000` on the FLAC output.** Mismatched sample rates
between score and dialogue track cause container-level audio bugs (see
Common Errors).

#### Step 5: Per-sequence dialogue normalization (recommended)

LTX 2.3 renders dialogue with **huge inter-sequence loudness variation**
— up to **23 LU spread** in our production runs (one sequence at -10
LUFS, another at -33 LUFS). If you mux in the score on top of that
variation, the quiet dialogue scenes will feel buried even though the
music isn't actually loud.

**Don't fix this with sidechain ducking on the score.** That degrades
the music. Fix the SOURCE: bring each sequence's dialogue up to a
consistent level via simple per-sequence gain.

```python
# For each cleaned/sequence_*.mp4:
#   1. Measure mean RMS via volumedetect
#   2. Compute gain = target_db - mean_db
#   3. Clamp gain so peak doesn't exceed -1.5 dBTP
#   4. Apply via "volume=NdB", FORCE 48 kHz output
# See tools/normalize_dialogue.py for a drop-in implementation
ffmpeg -i sequence_NNN.mp4 -c:v copy \
    -af "volume=+5.4dB" \
    -c:a aac -b:a 192k -ar 48000 \
    -movflags +faststart \
    normalized/sequence_NNN.mp4
```

Target: `-23 dB mean / -1.5 dBTP peak`. Skip sequences whose input mean
is below `-50 dB` (effectively silent — don't amplify noise floor).

⚠️ **DO NOT use `loudnorm` with `linear=true`** for this. It internally
upsamples to 96 kHz and the resulting AAC audio causes container-level
playback bugs (audio shorter than video, dropouts). Plain `volume=NdB`
with `volumedetect` measurement is the safe path.

After normalizing, re-run `concat-relay --xfade 0 --master` on the
normalized sequences to produce a NORMALIZED.mp4 with consistent
dialogue throughout.

#### Step 6: Mux normalized dialogue + score

```bash
ffmpeg -y -i NORMALIZED.mp4 -i PRINCE_SCORE.flac \
    -filter_complex "
        [0:a]volume=1.0[d];
        [1:a]volume=0.25[s];
        [d][s]amix=inputs=2:duration=first:dropout_transition=2:normalize=0[mixed]
    " \
    -map 0:v -map "[mixed]" \
    -c:v copy -c:a aac -b:a 192k -ar 48000 \
    -movflags +faststart \
    FINAL.mp4
```

Mix levels:
- **Dialogue at 1.0** (full level, preserved as-rendered after Step 5)
- **Score at 0.25** (= -12 dBFS) — sits cleanly underneath
- **`normalize=0`** prevents amix from auto-attenuating either track
- **`-ar 48000`** explicit on the encode

If music feels too thin under speech: bump score to 0.30. If speech is
fighting through: drop score to 0.20. **Don't go below 0.18** or the
score becomes barely audible. **Don't add `sidechaincompress`** — it
sucks the life out of the score.

#### Step 7: Verify

```bash
# Sample rate must be 48000, durations should match the video duration ±0.05s
ffprobe -v error -select_streams a:0 -show_entries stream=sample_rate,duration -of default=nk=1 FINAL.mp4
ffprobe -v error -select_streams v:0 -show_entries stream=duration -of default=nk=1:nw=1 FINAL.mp4

# Loudness sanity
ffmpeg -hide_banner -i FINAL.mp4 -af volumedetect -f null - 2>&1 | grep -E "mean_volume|max_volume"
# Expect mean ~ -22 to -25 dB (orchestral target with dialogue on top), max ~ -0.5 dB
```

If audio sample_rate ≠ 48000 → loudnorm contamination, re-do Step 5
with `volume=NdB` only. If audio duration ≠ video duration → some
sequence in concat had timing weirdness; check the per-sequence
NORMALIZED.mp4 durations.

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
| **Music generation** sounds chaotic / distorted / noise-like | You set the wrong CFG/steps for the variant. **`xl_turbo` requires CFG 1.0 + 10 steps** (it's distilled). Higher values produce noise. Check with `python3 .../music_maker.py --help` and rerun without overriding `--cfg` / `--steps`. |
| **Music generation** errors with `size mismatch for model.embed_tokens.weight` | You're using `CLIPLoader` with `qwen_*_ace15.safetensors`. ACE-Step needs `DualCLIPLoader` loading BOTH the 0.6B and 4B Qwen text encoders together with type=`ace`. Use `aeon-music-maker` — don't roll your own workflow. |
| **Music generation** asks for >240s in one call | ACE-Step 1.5 caps at ~240s per generation. Split your score into multiple cues (Recipe D Step 2/3) and concatenate with `acrossfade=d=2`. |
| **Score regeneration** seems to not actually use the new audio | ComfyUI's `SaveAudioMP3` auto-increments suffixes. A second run with the same prefix saves as `_00002_.mp3`; with a different prefix saves as `<new>_00001_.mp3`. The OLD file is still at `<original>_00001_.mp3` and your concat is using it. Either delete the old file before regenerating, or rename the new file to the canonical name afterward. |
| **Final mux** has audio dropouts / audio shorter than video | Sample-rate mismatch. Most common cause: `loudnorm` with `linear=true` upsampled audio to 96 kHz internally, leaving the AAC encode at 96 kHz. Force `-ar 48000` on every audio encode in the chain. For dialogue normalization, use simple `volumedetect` measure + `volume=NdB` filter instead of loudnorm linear-mode. |
| **Some dialogue lines feel too quiet** vs others in same film | LTX renders dialogue with up to 23 LU inter-sequence variation. Don't lower the score / don't sidechain-duck — fix the SOURCE: per-sequence dialogue normalization (Recipe D Step 5). Target -23 dB mean, peak ceiling -1.5 dBTP, simple `volume=NdB` per sequence. |
| **Score sounds generic / doesn't match the film's emotional arc** | You generated one big track instead of cue-based. Redo as 5-10 cues mapped to story pivot points (Recipe D Step 2). Each cue gets its own focused prompt; cohesion comes from shared instrument palette + sequential seeds + recurring melodic theme. |
| **Score has a "wash"** that drowns dialogue regardless of mix level | (a) Verify the screenplay's top-level `negative_prompt` is suppressing music — LTX's bundled music in the dialogue track will compound with your composed score. (b) Verify you used `--master orchestral` (or appropriate preset) — without mastering, score loudness is unpredictable. (c) Drop score volume from 0.25 to 0.20 in the amix. |

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
