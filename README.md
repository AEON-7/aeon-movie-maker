# aeon-movie-maker

> Fast cinematic video generation built around LTX 2.3 22B (distilled fp8). Three subcommands: render a single clip, render a full screenplay (sequential clips with last-frame carry-forward for character/scene continuity), or stitch dialogue + music + SFX into a finished film with sidechain ducking. ~10–15× faster than WAN-based pipelines while delivering comparable cinematic quality.

Part of the **AEON Media Production** family.

## What this gives you

- **Three modes** — `clip` (single shot), `screenplay` (multi-shot film), `stitch` (audio mux with sidechain ducking)
- **LTX 2.3 22B fp8** — Lightricks' fast/quality joint-AV pipeline. Three sub-modes: `fast` (distilled), `quality` (EROS, joint-AV), `abstract` (drops physics LoRAs for non-realistic content)
- **Last-frame carry-forward** — between sequential clips, the final frame of clip N becomes the seed image for clip N+1, preserving character appearance + lighting + composition
- **Persistence knob** — `--persistence 0–1` controls how strictly the seed image constrains the next clip (0 = free, 1 = locked)
- **Per-character seed offsets** — stable hash so the same character appears consistent across an entire screenplay
- **Per-scene LoRA routing** — automatic style-tag → LoRA selection (cinematic, anime, pixar, etc.)
- **T2V / I2V / A2V** — text-to-video, image-to-video, or **audio-to-video** (LTX 2.3 EROS with `LTXVReferenceAudio` — true joint AV)
- **Sidechain-ducked mix** at stitch time — music drops ~12 dB under speech, then `loudnorm I=-16:TP=-1.5:LRA=11`

## Quick start

```bash
git clone https://github.com/AEON-7/aeon-movie-maker.git
cd aeon-movie-maker
cp .env.example .env       # edit COMFYUI_URL + COMFYUI_ROOT
./setup.sh                 # check ComfyUI, install deps, list missing models

# Single clip — fast mode (distilled fp8)
python scripts/movie_maker_fast.py clip \
    --prompt "drone shot over a misty pine forest at dawn, cinematic, slow motion" \
    --duration 5 --width 832 --height 480 \
    --output forest_drone.mp4

# Full screenplay
python scripts/movie_maker_fast.py screenplay screenplay.json

# Stitch audio with the rendered video clips
python scripts/movie_maker_fast.py stitch clips_manifest.json \
    --dialogue dialogue_master.wav \
    --music music_bed.flac \
    --sfx sfx_master.wav \
    -o finished_film.mp4
```

## Modes

### `clip` — single shot

Render one video clip from a text prompt, an optional seed image, or an audio reference.

```bash
python scripts/movie_maker_fast.py clip \
    --prompt "neon-lit Tokyo street, rainy night, reflection, cinematic" \
    --duration 5 \
    --mode fast \
    --seed-image character_portrait.jpg \
    --persistence 0.6 \
    --output shot.mp4
```

Modes:
- `fast` — LTX 2.3 22B distilled fp8, ~3–5 s of wall time per second of output
- `quality` — LTX 2.3 EROS joint-AV, slower but supports `--audio-reference` for true A2V
- `abstract` — drops physics LoRAs (VBVR), better for fractals / motion graphics / non-realistic content

### `screenplay` — multi-shot film

Render a sequence of clips from a structured JSON. Each clip's last frame becomes the next clip's seed image (with persistence weighting), giving you coherent character + scene continuity across an entire film.

```json
{
  "title": "my_film",
  "fps": 24,
  "characters": {
    "ALICE":  {"description": "young woman, dark hair, blue eyes", "voice_seed": 100},
    "BOB":    {"description": "older man, gray beard, leather jacket", "voice_seed": 200}
  },
  "scenes": [
    {
      "id": "01_intro",
      "duration": 5,
      "prompt": "Alice stands in a doorway, looking out at the street",
      "characters": ["ALICE"],
      "style_tags": ["cinematic", "soft_lighting"]
    },
    {
      "id": "02_dialogue",
      "duration": 6,
      "prompt": "close-up on Alice as she speaks, single tear",
      "dialogue": [{"character": "ALICE", "text": "I never said I'd stay forever."}]
    }
  ]
}
```

The screenplay command automatically:
- Routes per-scene LoRAs based on `style_tags`
- Carries the last frame of scene N as seed for scene N+1
- Applies the per-character seed offset for visual identity
- Writes a `clips_manifest.json` mapping scene IDs to clip files (used by `stitch`)

### `stitch` — final mux with audio

Take the rendered clips + a dialogue master + music bed + SFX layer and produce a finished film. The mix uses the same sidechain-ducked filter chain as `aeon-radio-drama`:

```
dialogue → speech bus → alimiter
                          │
                          ├── output to mix
                          └── sidechain key

music + SFX → amix → sidechaincompress (driven by speech, threshold 0.05, ratio 8)
                  → amix with speech (weights 1.0 0.8)
                  → loudnorm I=-16:TP=-1.5:LRA=11
```

```bash
python scripts/movie_maker_fast.py stitch clips_manifest.json \
    --dialogue dialogue_master.wav \
    --music    music_bed.flac \
    --sfx      sfx_master.wav \
    --music-volume 0.30 \
    --sfx-volume   0.80 \
    --xfade        0.8 \
    -o finished_film.mp4
```

## Companion repos

The natural pipeline:

1. **Audio**: `aeon-radio-drama` produces dialogue + music + SFX masters from a script
2. **Video**: `aeon-movie-maker screenplay` renders the visual clips
3. **Final mux**: `aeon-movie-maker stitch` ties everything together

For non-narrative work (music videos), substitute `aeon-music-maker` for the audio and `aeon-music-video` for the editing.

## Prerequisites

- ComfyUI reachable at `${COMFYUI_URL}`
- Python 3.10+, ffmpeg + ffprobe
- ~50 GB disk for LTX 2.3 22B + EROS + LoRAs + Gemma encoder

`setup.sh` checks all of this and lists download commands for any missing pieces. See `references/AGENT_CINEMA_AUTOPILOT.md` for the full agent runbook.

## Project structure

```
aeon-movie-maker/
├── README.md
├── AGENTS.md
├── SKILL.md           full skill: prompt engineering, mode selection, persistence tuning
├── ATTRIBUTION.md
├── LICENSE
├── .env.example
├── .gitignore
├── setup.sh
├── sync.sh
├── requirements.txt
├── scripts/
│   └── movie_maker_fast.py  the three subcommands (clip / screenplay / stitch)
└── references/
    ├── MOVIE_MAKER_GUIDE.md       deep technical guide (~85 KB)
    └── AGENT_CINEMA_AUTOPILOT.md  agent-mode end-to-end runbook
```

## License

MIT.

## See also

- [`aeon-radio-drama`](https://github.com/AEON-7/aeon-radio-drama) — full audio pass for the film
- [`aeon-music-maker`](https://github.com/AEON-7/aeon-music-maker) — music score
- [`aeon-music-video`](https://github.com/AEON-7/aeon-music-video) — audio-reactive editing
- [`comfyui-aeon-spark`](https://github.com/AEON-7/comfyui-aeon-spark) — base ComfyUI Docker stack
