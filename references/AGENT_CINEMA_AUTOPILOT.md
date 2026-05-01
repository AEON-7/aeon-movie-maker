# Agent Cinema Autopilot — Complete Video Production Guide

Turn any screenplay, story, or novella into a finished cinematic video with
AI-generated visuals, dialogue, music, and professional transitions.

## Two video engines — pick by speed vs lip-sync priority

As of 2026-04-22, the cinema toolkit has **two parallel video engines** sharing
the same screenplay JSON format. Choose per-production:

| | **Movie Maker Fast** (new, LTX 2.3) | **Movie Maker Slow WAN** (legacy, this doc's default) |
|---|---|---|
| Tool | `scene_production_tool/movie_maker_fast.py` | `scene_production_tool/render_all_acts.py` + `multitalk_workflow.py` |
| Skill | [`movie-maker-fast`](../movie-maker-fast.md) | this document |
| Engine | LTX 2.3 22B distilled fp8 + abliterated Gemma + VBVR physics LoRA | Wan 2.1 I2V 480p + MultiTalk (Wav2Vec-driven lip sync) |
| 7s clip render | ~75 s warm | 20–30 min warm |
| 10-min drama | ~30–40 min total | 4–6 hours total |
| Lip-sync | Off-frame / VO quality (visuals-first) | Tight sample-accurate sync |
| Best for | Most productions — previews, iteration, bulk rendering | Hero shots w/ on-screen dialogue closeups |

Both tools consume the same `screenplay.json` format, the same `characters`
Three-Lock voice casting, and produce output that the same stitcher can assemble.
**The fast tool is the new default** unless tight lip-sync is essential.
The rest of this document covers the slow/WAN pipeline in full detail; the fast
pipeline lives in [`movie-maker-fast.md`](../movie-maker-fast.md).

---

## Quick Start

**From a screenplay:**
```bash
ssh ${SSH_USER}@127.0.0.1 'cd "${COMFYUI_ROOT}" && python video_production_tool/autopilot.py "video_production_tool/example_screenplay.json" --style "ethereal mystical cosmic cinematic" --project-name "the_awakening"'
```

**From a story/novella:**
```bash
ssh ${SSH_USER}@127.0.0.1 'cd "${COMFYUI_ROOT}" && python video_production_tool/autopilot.py "path/to/story.txt" --style "dark gothic cinematic" --project-name "my_story" --audio-mode tts'
```

---

## Infrastructure

| Host | IP | Services |
|------|----|----------|
| Windows Desktop | 127.0.0.1 | ComfyUI (8188), TTS (8092), GPU RTX 5090 32GB |
| vLLM | 127.0.0.1:8000 | LLM for screenplay extraction from text |
| SSH | `${SSH_USER}@127.0.0.1` | Your execution interface |

**Verify before starting:**
```bash
# ComfyUI running?
curl -s http://127.0.0.1:8188/system_stats | head -c 100

# LLM available? (needed for text→screenplay extraction)
curl -s http://127.0.0.1:8000/v1/models | head -c 100
```

---

## Two Ways to Provide Input

### Option A: Structured Screenplay JSON

You write (or generate) a JSON file with scenes, dialogue, camera directions. Maximum
control over every shot. See `example_screenplay.json` for the full template.

**Minimal working example:**
```json
{
    "title": "My Film",
    "scenes": [
        {
            "description": "A dark forest at twilight. Mist drifts between ancient trees.",
            "dialogue": [
                {"character": "VOICE", "line": "Something stirs in the shadows.", "direction": "whispered"}
            ],
            "action": "Camera drifts through the trees. Something moves at the edge of visibility.",
            "mood": "eerie, suspenseful"
        }
    ]
}
```

**Full scene fields:**

| Field | Required | Default | Description |
|-------|----------|---------|-------------|
| `description` | **Yes** | — | Visual description of the setting |
| `scene_number` | No | auto | Sequential number |
| `location` | No | "UNSPECIFIED" | Film-style (e.g., "INT. TEMPLE - DAWN") |
| `characters` | No | [] | Character names present in scene |
| `dialogue` | No | [] | Array of {character, line, direction} |
| `action` | No | "" | Camera movement + physical action |
| `mood` | No | "neutral" | Emotional tone keywords |
| `duration_hint` | No | 10 | Estimated seconds |

**Character profiles** (optional, top-level) — use the **Three-Lock voice preservation system** for every speaking character so voices stay identical across scenes, episodes, and sessions. Full theory + 16-emotion override table + ensemble-design axes live in `tts-voice-designer/SKILL.md`; this section covers how to wire it into a cinema-tool screenplay.

### Minimal example (visual-only character, no dialogue)

```json
{
  "characters": {
    "LYRA": {
      "description": "Luminous feminine figure, golden jewelry, white robes"
    }
  }
}
```

### Full speaking-character entry (recommended)

```json
{
  "characters": {
    "LYRA": {
      "description": "Luminous feminine figure, golden jewelry, white robes, mid-20s",
      "voice": "Clear, bright feminine voice with crystalline precision, speaking with confident warmth and subtle emotional resonance, an explorer's curiosity coloring every word",
      "seed": 201,
      "emotion_overrides": {
        "tender":   ", speaking with gentle tenderness and quiet intimacy",
        "resolute": ", voice gaining a steady edge of determination",
        "broken":   ", voice cracking with grief, barely holding together"
      }
    },
    "DEITY": {
      "description": "Veiled androgynous figure, cosmic light behind the veil, ageless",
      "voice": "Deep, resonant masculine voice with cosmic authority, speaking slowly and deliberately with measured gravity that suggests ancient wisdom",
      "seed": 42,
      "emotion_overrides": {
        "commanding": ", projecting with full authority, each word a decree",
        "sorrowful":  ", heavy with sadness, each word weighted with loss"
      }
    },
    "AMIR": {
      "description": "Scholar in his 40s, weathered hands, Middle Eastern features, olive robes",
      "voice": "Warm masculine voice with scholarly authority, measured cadence that weighs each word, hints of Middle Eastern heritage in the careful articulation",
      "seed": 347
    }
  }
}
```

### The Three Locks (summary — full detail in `tts-voice-designer/SKILL.md`)

**Lock 1 — `voice`** (vocal DNA, ~80% of the voice): 1–3 sentences describing pitch/register, texture, accent, pace, and emotional baseline. Follow this formula:

```
[pitch & register] + [texture & quality] + [accent/origin] + [pace & rhythm] + [emotional baseline]
```

Avoid: vague terms ("nice voice"), action descriptions ("speaks about X"), contradictions ("loud whisper"), 5+ sentences. These fail to lock consistently.

**Lock 2 — `seed`** (integer, freezes the remaining randomness): Same `voice` string + same `seed` = bit-for-bit identical voice across sessions separated by weeks. **Never change a character's seed mid-production.** Tip: reserve decades by role — 100s for narrators, 200s for heroes, 300s for antagonists, 400s for supporting — so conflicts are easy to spot.

**Lock 3 — `emotion_overrides`** (additive delivery shifts): For beats where a character's delivery changes without changing their identity. The override string is appended to the base `voice` for that one line; the seed stays the same so timbre is preserved. Pick 3–5 emotions per character that match the script's range; fall through to the built-in global table (tender / broken / commanding / fearful / intimate / furious / joyful / sorrowful / contemplative / tense / cautious / defiant / reflective / angry / anguished) for anything else.

### Wiring emotions to scenes

Each `dialogue` line can reference an emotion the cinema pipeline resolves against the character's `emotion_overrides`:

```json
{
  "scenes": [{
    "description": "AMIR stands at the edge of the archive, torchlight flickering.",
    "dialogue": [
      {"character": "LYRA",  "line": "We shouldn't be here.", "direction": "tender"},
      {"character": "AMIR",  "line": "And yet, here we are.", "direction": "resolute"},
      {"character": "DEITY", "line": "I have been waiting.", "direction": "commanding"}
    ]
  }]
}
```

The `direction` field acts as both an emotion label (composes with the character's `voice` + matching `emotion_overrides[direction]`) and an acting note (e.g. `"whispered, close to mic"` would skip emotion lookup and apply as a per-line instruct override for that one line only).

### Ensemble design — cast for contrast

Listeners distinguish characters by sound alone. Design the cast to spread across five axes; no two characters in the same scene should match on more than 2:

| Axis | Options |
|---|---|
| Pitch register | high / mid / low |
| Pace | quick / deliberate / meandering |
| Texture | smooth / gravelly / breathy / crisp |
| Accent / origin | neutral / regional / foreign |
| Energy | reserved / neutral / animated |

The Digitized Deity cast (LYRA/DEITY/AMIR above) spans three pitch registers, three textures, three accents, and three paces — cleanly separable.

### Session-to-session preservation

Copy the `characters` dict from the shipped film's `screenplay.json` into the next episode's file. Same seeds + same voice strings = identical cast. Treat the characters dict as **read-only after the first scene ships**:

- Adding a new character: assign a seed in an unused decade.
- Extending a character's emotional range: add new keys to `emotion_overrides`, don't edit the base `voice`.
- Need a per-line override for a beat that fits no emotion: put prose in the `direction` field of that single dialogue line (it bypasses the override table).

### Audition before committing

Don't guess on seeds. For each character, submit 3–4 candidate seeds against a representative line with the same `voice` string, listen back, pick the keeper, then freeze. See `tts-voice-designer/SKILL.md` §Testing for a copy-pasteable audition loop that hits the Qwen3-TTS endpoint directly.

### Option B: Plain Text (Story/Novella)

Provide any text file — novella, short story, script outline, or even bullet points.
The LLM automatically extracts a structured screenplay.

```bash
ssh ${SSH_USER}@127.0.0.1 'cd "${COMFYUI_ROOT}" && python video_production_tool/autopilot.py "path/to/my_story.txt" --style "dark fantasy cinematic"'
```

**What the LLM extracts:**
- Identifies key narrative scenes
- Extracts dialogue with speaker attribution
- Creates film-style location lines
- Assigns mood and camera directions
- Estimates scene durations

**After extraction:** Review `screenplay.json` and refine before continuing:
```bash
# Read the extracted screenplay
ssh ${SSH_USER}@127.0.0.1 'python -c "
import json
with open(\"${COMFYUI_ROOT}/output/video/PROJECT/screenplay.json\") as f:
    s = json.load(f)
for sc in s[\"scenes\"]:
    print(f\"Scene {sc[\"scene_number\"]}: {sc[\"location\"]}\")
    print(f\"  {sc[\"description\"][:100]}\")
    for d in sc.get(\"dialogue\",[]):
        print(f\"  {d[\"character\"]}: \\\"{d[\"line\"][:60]}\\\"\")
    print()
"'
```

---

## The 8-Phase Pipeline

### Phase 1: Parse (seconds)
**Input → structured screenplay**

- JSON: validated directly
- Text: LLM extracts scenes, dialogue, directions
- Fallback: paragraph-based splitting if LLM unavailable

### Phase 2: Storyboard (seconds)
**Screenplay → shot-by-shot breakdown**

Each scene becomes 1-5 shots:

| Shot Type | Camera | Duration | When Used |
|-----------|--------|----------|-----------|
| Establishing | Slow push in, wide | 3-6s | Start of each scene |
| Medium | Steady, waist-up | 4-15s | Dialogue delivery |
| Close-up | Face fills frame, shallow DOF | 2-5s | Emotional moments, whispered dialogue |
| Reaction | Medium close-up | 2-4s | Character responses |
| Action | Dynamic tracking | 3-8s | Physical movement |
| Wide | Full environment | 3-6s | Scene endings |

Each shot gets three prompts:
- `image_prompt` — for Flux/SDXL reference image generation
- `video_prompt` — for LTX video generation (includes camera + motion + lip sync cues)
- `audio_cues` — dialogue text, character, direction, ambient description

### Phase 3: Artwork (10-30 minutes)
**Reference images for each shot**

- **Fluxmania III** (default) or SDXL with smart LoRA matching
- Same weighted scoring + family compatibility system as music video tool
- `new_scene=True` shots get unique images; continuation shots share the previous image
- 50 steps for Flux, 30 for SDXL
- All files namespaced: `{project}_shot_NNN.png`

### Phase 4: Audio
**Dialogue + music + sound effects**

**Two modes:**

| Mode | Flag | How it works | Quality |
|------|------|-------------|---------|
| **Native** (default) | `--audio-mode native` | LTX 2.3 generates audio inline with video. Dialogue included in video prompt. | Synthetic but integrated |
| **TTS** | `--audio-mode tts` | Chatterbox/Qwen3-TTS generates per-character dialogue. ACEStep for music. Mixed into master track. | Higher quality, more control |

**TTS mode details:**
- Each dialogue line → individual WAV via ComfyUI TTS nodes
- Silence generated for non-dialogue shots
- All clips concatenated into master audio track
- Master sliced into per-shot WAV files for LTX generation

### Phase 5: Schedule (seconds)
**Frame-perfect timing**

- Duration driven by dialogue length (TTS mode) or `duration_hint` (native mode)
- Overlap buffers (2s) only at scene-change boundaries
- All durations = `num_frames / 24` (exact, no drift)

### Phase 6: Generate (1-3 hours)
**Per-shot LTX 2.3 video via ComfyUI API**

- Each shot submitted individually as an API-format workflow
- Audio slice fed into LTX for audio-reactive generation (lip sync, motion)
- **LoRA stack:** Distilled (0.5) + Reasoning (0.7) + IC-LoRA (0.8) + Abliterated (1.0)
- **Models:** `ltx2310eros_beta` + `Gemma3-12B-NVFP4-Sikaworld-HF` (uncensored)
- Resume support: existing shots are skipped

### Phase 7: Post-Process (5-10 minutes)
**Transitions + trimming**

- RIFE v4.7 morph transitions at scene changes (same variants as music video tool)
- No transitions between shots within the same scene (seamless flow)
- Shots trimmed to content region (overlap buffers removed)

### Phase 8: Stitch (minutes)
**Final assembly**

- All shots + transitions concatenated
- Master audio overlaid
- 6-second fade to black at end
- Output: `{project}_final.mp4`

---

## CLI Reference

```
python video_production_tool/autopilot.py INPUT [options]

Positional:
  INPUT                        Screenplay JSON or plain text file

Core Options:
  --style, -s TEXT             Visual style (e.g., "ethereal mystical cinematic")
  --project-name, -p NAME      Project name (default: from filename)
  --audio-mode {tts,native}    Audio generation mode (default: native)

Image Generation:
  --image-model {flux,sdxl}    Image backend (default: flux)
  --base-model NAME            Flux base: "fluxmania" (default), "flux_dev"
  --sdxl-checkpoint NAME       SDXL checkpoint (e.g., "illustrious", "pony", "nova")

Pipeline Control:
  --resume                     Skip phases with existing output
  --phase N                    Start from phase N (1-8)
  --dry-run                    Print plan without executing

Technical:
  --width INT                  Frame width (default: 1536)
  --height INT                 Frame height (default: 832)
  --fps INT                    Framerate (default: 24)
  --comfyui-url URL            ComfyUI (default: http://localhost:8188)
  --llm-url URL                LLM for text extraction (default: http://127.0.0.1:8000/v1)
```

---

## Style Keywords

The same smart LoRA matching system as the music video tool. Keywords in `--style`
auto-select compatible LoRAs with weighted scoring and anti-tag exclusions.

**Common combos for film:**
- `"cinematic dramatic moody"` — film noir, dark drama
- `"ethereal mystical sacred divine"` — spiritual, transcendent
- `"dark gothic horror eerie"` — dark fantasy, horror
- `"futuristic scifi neon cyberpunk"` — sci-fi
- `"fantasy magical enchanted"` — high fantasy
- `"realistic portrait beauty cinematic"` — realistic drama
- `"psychedelic surreal cosmic trippy"` — experimental
- `"ghibli anime soft illustration"` — anime (use `--image-model sdxl --sdxl-checkpoint illustrious`)

---

## Writing Effective Screenplays

### Scene Descriptions
Be specific about what you see. The AI generates better images and video when
descriptions are concrete:

**Weak:** "A temple."
**Strong:** "A vast temple hall with towering columns of white marble veined with gold.
Dawn light streams through arched windows, catching golden dust motes. The obsidian
floor reflects everything above like a dark mirror."

### Dialogue Directions
The `direction` field guides both TTS voice performance and video generation:
- `"whispered, with cosmic echo"` — quiet, reverberant
- `"shouting, desperate"` — loud, emotional
- `"voiceover, reverent"` — narrator, not on-screen
- `"laughing, joyful"` — happy, animated
- `"eyes closed, serene"` — visual direction for the video

### Camera/Action Descriptions
The `action` field directly drives the video generation prompt:
- `"Camera slowly pushes through the temple hall"` — forward dolly
- `"Slow crane up and away, revealing the full scope"` — pull back
- `"Camera orbits slowly around Lyra"` — orbital shot
- `"Rapid montage of cosmic creation"` — fast cuts
- `"Camera holds steady, close-up on her face"` — static close-up

### Mood Keywords
The `mood` field influences style, lighting, and pacing:
- **Low energy:** mysterious, peaceful, melancholy, contemplative, serene
- **Medium:** dramatic, tense, nostalgic, sacred, ethereal
- **High energy:** climactic, powerful, transcendent, chaotic, euphoric
- **Transitions:** anticipatory (building), resolution (winding down)

---

## Editing the Storyboard

After Phase 2, review and refine `storyboard.json`:

```bash
# View all shots
ssh ${SSH_USER}@127.0.0.1 'python -c "
import json
with open(\"${COMFYUI_ROOT}/output/video/PROJECT/storyboard.json\") as f:
    sb = json.load(f)
for shot in sb[\"shots\"]:
    ns = \"NEW\" if shot[\"new_scene\"] else \"   \"
    print(f\"Shot {shot[\"global_index\"]:3d} {ns} {shot[\"shot_type\"]:12s} {shot[\"duration\"]:5.1f}s  Scene {shot[\"scene_index\"]}\")
    print(f\"  IMG:  {shot[\"image_prompt\"][:90]}\")
    print(f\"  VID:  {shot[\"video_prompt\"][:90]}\")
    if shot[\"dialogue\"]:
        print(f\"  DLG:  {shot[\"character\"]}: \\\"{shot[\"dialogue\"][:60]}\\\"\")
    print()
"'
```

**Editable fields per shot:**

| Field | Safe to Edit | Description |
|-------|-------------|-------------|
| `image_prompt` | YES | Reference image generation prompt |
| `video_prompt` | YES | Video generation prompt (camera, action, lip sync) |
| `dialogue` | YES (careful) | Changes TTS audio in Phase 4 |
| `mood` | YES | Influences transition style |
| `num_frames` | NO | Frame-aligned timing |
| `duration` | NO | Computed from num_frames |
| `global_index` | NO | Shot ordering |
| `new_scene` | NO | Controls transitions and image sharing |

After editing, delete images and re-run from Phase 3:
```bash
ssh ${SSH_USER}@127.0.0.1 'rm -f "${COMFYUI_ROOT}/input/PROJECT/"*.png'
ssh ${SSH_USER}@127.0.0.1 'cd "${COMFYUI_ROOT}" && python video_production_tool/autopilot.py INPUT --project-name "PROJECT" --phase 3'
```

---

## Adapting a Novella

The existing novella at `The_Story_Organized/` contains 12 chapters with 140+ images
that could serve as reference material. To create a video from a novella:

1. Save the novella text as a `.txt` file
2. Run the autopilot — the LLM extracts the screenplay
3. Review and refine the extracted `screenplay.json`
4. Re-run from Phase 2 with your edits

```bash
# Step 1: Run extraction
ssh ${SSH_USER}@127.0.0.1 'cd "${COMFYUI_ROOT}" && python video_production_tool/autopilot.py "path/to/novella.txt" --style "ethereal mystical cinematic" --project-name "novella_film" --phase 1'

# Step 2: Review
ssh ${SSH_USER}@127.0.0.1 'cat "${COMFYUI_ROOT}/output/video/novella_film/screenplay.json" | python -m json.tool | head -50'

# Step 3: Edit screenplay.json (see editing guide above)

# Step 4: Continue from Phase 2
ssh ${SSH_USER}@127.0.0.1 'cd "${COMFYUI_ROOT}" && python video_production_tool/autopilot.py "path/to/novella.txt" --project-name "novella_film" --phase 2'
```

---

## Example: Full Production Run

```bash
# Upload screenplay
scp my_screenplay.json ${SSH_USER}@127.0.0.1:"${COMFYUI_ROOT}/input/"

# Run full pipeline with TTS dialogue
ssh ${SSH_USER}@127.0.0.1 'cd "${COMFYUI_ROOT}" && python video_production_tool/autopilot.py "input/my_screenplay.json" --style "cinematic dramatic moody" --audio-mode tts --project-name "my_film"'

# Monitor progress
ssh ${SSH_USER}@127.0.0.1 'ls "${COMFYUI_ROOT}/output/video/my_film/"*.mp4 2>/dev/null | wc -l'

# Download result
scp ${SSH_USER}@127.0.0.1:"${COMFYUI_ROOT}/output/video/my_film/my_film_final.mp4" ./
```

---

## Output Structure

```
output/video/{project}/
  screenplay.json                     Phase 1: structured screenplay
  storyboard.json                     Phase 2: shot-by-shot breakdown
  schedule.json                       Phase 5: frame-perfect timing
  audio/                              Phase 4:
    {project}_audio_master.wav          Master audio track
    {project}_dialogue_NNN.wav          Per-line TTS clips
    {project}_shot_NNN.wav              Per-shot audio slices
  {project}_shot_NNN_NNNNN_.mp4       Phase 6: generated video shots
  transitions/                        Phase 7: RIFE morph clips
  {project}_final.mp4                 THE FINAL VIDEO

input/{project}/
  {project}_shot_NNN.png              Reference images (Phase 3)
```

---

## Troubleshooting

| Issue | Fix |
|-------|-----|
| Phase 1 extraction garbage | Check LLM at port 8000; refine `screenplay.json` manually |
| Phase 3 images missing | Check `output/{project}/` for suffixed files; re-run `--phase 3` |
| Phase 4 TTS fails | Switch to `--audio-mode native`; or check Chatterbox nodes in ComfyUI |
| Phase 6 shots fail | Check `schedule.json` image paths; `--phase 6 --resume` to retry |
| Dialogue not lip-synced | Use `--audio-mode tts` for better audio; ensure video_prompt mentions "lips moving" |
| Video too short | Check `duration_hint` values in screenplay; increase for longer scenes |
| Audio out of sync | Re-run from `--phase 5` to rebuild timing from audio |
| Want different style | Delete images, re-run from `--phase 3` with new `--style` |
