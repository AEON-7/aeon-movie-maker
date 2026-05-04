# aeon-movie-maker


[![☕ Tips](https://img.shields.io/badge/%E2%98%95_Tips-Support_the_work-ff5e5b?style=flat)](https://github.com/AEON-7/AEON-7#-support-the-work)
> Fast cinematic video generation built around LTX 2.3 22B (distilled fp8). Three subcommands: render a single clip, render a full screenplay (sequential clips with last-frame carry-forward for character/scene continuity), or stitch dialogue + music + SFX into a finished film with sidechain ducking. ~10–15× faster than WAN-based pipelines while delivering comparable cinematic quality.

Part of the **AEON Media Production** family.

> ⚡️ **AI agents using this tool: read [AGENTS.md](AGENTS.md) first.**
> It's a complete copy-pasteable runbook with a glossary, decision tree,
> literal recipes, and a troubleshooting table. You should not need to
> consult any other file.

## What this gives you

- **Three subcommands** — `clip` (single shot), `screenplay` (multi-shot film), `stitch` (audio mux with sidechain ducking)
- **Two screenplay flows** — per-scene I2V (silent video, audio added at stitch time) OR Prompt Relay (`--use-relay`, joint A/V with model-generated dialogue + lipsync)
- **LTX 2.3 22B fp8** — Lightricks' video pipeline. Three sub-modes: `fast` (distilled FP8), `quality` (non-distilled FP8 + 0.5 distill LoRA), `abstract` (drops physics LoRAs for non-realistic content)
- **Last-frame carry-forward** — between sequential clips OR Prompt Relay sequences, the final frame becomes the seed image for the next, preserving character appearance + lighting + composition
- **Per-character seed offsets** — stable hash so the same character appears consistent across an entire screenplay
- **Per-scene LoRA routing** — automatic style-tag → LoRA selection (cinematic, anime, pixar, etc.)
- **T2V / I2V** — text-to-video or image-to-video
- **Joint A/V with dialogue + lipsync** (Prompt Relay flow only) — model generates audio matching mouth motion in the same forward pass
- **Sidechain-ducked mix** at stitch time — music drops ~12 dB under speech, then `loudnorm I=-16:TP=-1.5:LRA=11`

## Glossary

The terms below are used precisely throughout this codebase. If you're
unsure what something means, this is the canonical definition.

| Term | What it means |
|---|---|
| **ComfyUI** | The model-serving program that actually generates the pixels. This tool sends it workflow instructions over HTTP. Default URL `http://127.0.0.1:8188`. |
| **LTX 2.3** | The 22B-parameter video model. Two main checkpoint variants: `distilled-fp8` (fast, lower fidelity) and `dev-fp8` (slower, higher fidelity). |
| **Scene** | One continuous moment a human writes in a screenplay. Has description, duration in seconds, optional dialogue. The smallest authoring unit. |
| **Sequence** (Prompt Relay) | One forward pass through the model. Contains 1–N scenes that morph smoothly into each other. Capped at 489 frames (~20s @ 24fps) per pass on Spark. |
| **Segment** (Prompt Relay) | The portion of a sequence corresponding to one scene. Each segment gets its own prompt + dialogue conditioning. |
| **Clip** (per-scene flow) | The MP4 file produced for one scene. One scene = one clip. |
| **T2V** | Text-to-video. No starting image. |
| **I2V** | Image-to-video. The first frame is constrained by a seed image. |
| **Joint A/V** | Video AND audio produced in the same model forward pass. **Only the Prompt Relay flow does this.** Per-scene flow produces silent video. |
| **Prompt Relay** | The `PromptRelayEncodeTimeline` ComfyUI node — takes multiple prompts with frame-budget weights and morphs through them in one continuous shot. Activated by the `--use-relay` flag. |
| **Lipsync** | Speech audio matched to mouth motion. Triggered by writing `'CHARACTER says "line"'` patterns in the prompt (which the screenplay's `dialogue` array becomes automatically). |
| **Carry-forward** | Between Prompt Relay sequences (hard cuts), the LAST FRAME of the previous sequence becomes the SEED IMAGE for the next. Maintains continuity across cuts. |
| **Wrapper prompt** | The "global anchor" for a Prompt Relay sequence. Built from screenplay-level `style` + `setting` + character VISUAL DESCRIPTIONS (from the `characters` dict). The strongest cross-sequence identity signal. |
| **Negative prompt** | Tells the model what NOT to generate. Critical for suppressing model-generated music in joint A/V output (so you can compose your own score). |
| **Hard cut** | An abrupt scene change between two Prompt Relay sequences. Triggered by `relay_break: true` or `tags: ["transition"]` on a scene, OR automatically when a scene's frame count would overflow the per-sequence budget. |
| **Stitch** | The `stitch` subcommand. Concatenates clips and muxes in dialogue + music + SFX with sidechain ducking. |

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
- `fast` — LTX 2.3 22B distilled FP8, ~3–5 s of wall time per second of output
- `quality` — LTX 2.3 22B non-distilled FP8 + distill LoRA @ 0.5, ~30–50% slower than fast but stronger prompt adherence and more motion variety
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

### `clip --relay <timeline.json>` — Prompt Relay (one continuous shot)

Render ONE LTX 2.3 forward pass that morphs smoothly through a timeline of
prompts — vs the standard `clip` that renders a single static prompt. Powered
by the `PromptRelayEncodeTimeline` custom node from `comfyui-aeon-spark`'s
ComfyUI-PromptRelay pack. Output is **joint A/V** (model generates audio in
the same pass — no separate stitch step needed for the relay portion).

Best for: continuous-shot scenes, dialogue between same characters, montages,
single-scene narrative beats with internal motion.

```bash
python scripts/movie_maker_fast.py clip \
    --prompt "ignored when --relay is set" \
    --relay timeline.json \
    --output forest.mp4
```

`timeline.json` schema:

```json
{
  "wrapper": "A continuous cinematic shot of two friends in a misty forest at dawn",
  "seed_image": "characters/ana_ben_anchor.png",
  "fps": 24, "width": 640, "height": 640,
  "segments": [
    {"prompt": "Ana points at something off-camera, surprised", "duration_s": 5},
    {"prompt": "Ben turns to follow her gaze, then smiles", "duration_s": 5},
    {"prompt": "They both walk forward into a clearing", "duration_s": 6}
  ]
}
```

Constraints:
- **Frame budget per pass**: ≤ 489 frames @ 640×640 on Spark (~20s @ 24fps).
  Longer films need multiple sequences — see `screenplay --use-relay` below.
- **Single seed image** for the whole pass. Character/location changes within
  a sequence morph from that anchor; for hard cuts, use a separate sequence.
- Set `--relay-no-audio` for video-only output, `--relay-use-lora` to apply
  the distill-1.1 LoRA on top.

### `screenplay --use-relay` — Prompt Relay screenplay flow

Auto-chunks a screenplay into Prompt Relay sequences and renders each as ONE
joint A/V pass. Within a sequence: smooth morphing between scenes. Between
sequences: hard cut, with the previous sequence's last frame uploaded to
ComfyUI as the next sequence's seed image.

```bash
python scripts/movie_maker_fast.py screenplay screenplay.json \
    --use-relay \
    --output-dir output/movie_fast/my_film
```

Auto-chunking rules:
1. Frame budget: a sequence's total stays ≤ `--relay-max-frames` (default 489).
   When the next scene would overflow, finalize the sequence + start a new one.
2. Explicit break: a scene with `relay_break: true` or any of the tags
   `{transition, cut, scene_change}` forces a new sequence.

Outputs `relay_manifest.json` listing each sequence with its scene indices,
seed, frame count, and output mp4 path. Joint A/V by default — `--relay-no-audio`
to drop audio per sequence.

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

## Production workflow: dialogue + custom music

The Prompt Relay flow (`screenplay --use-relay`) generates **joint A/V** —
LTX 2.3 produces video AND an audio track (with dialogue + lipsync) in a
single forward pass. The model also tends to add a music bed of its own,
which fights with any score you'd want to compose intentionally. The
validated production pattern is to **suppress music in the relay output**
and **add a custom score from [`aeon-music-maker`](https://github.com/AEON-7/aeon-music-maker)**
muxed underneath the dialogue.

The full step-by-step (with literal copy-pasteable commands, troubleshooting,
output verification) lives in [**AGENTS.md → Recipe D**](AGENTS.md#recipe-d--full-production-dialogue--custom-music).

The 30-second TL;DR:

1. Write your screenplay JSON with a top-level `characters` dict (visual
   descriptions, not just names) and a top-level `negative_prompt` that
   includes `"music, soundtrack, score, instruments, drums, melody, ..."`
   plus standard anatomy negatives.
2. `python scripts/movie_maker_fast.py screenplay <yours>.json --use-relay`
3. Concat the per-sequence MP4s. **Use the `concat-relay` subcommand** —
   it handles xfade dissolves between sequences (much smoother than hard
   cuts), bakes in safe encoder settings (yuv420p / High@L4.0 / faststart),
   and can optionally produce a yuv444p10le master sibling for archival:

   ```bash
   python scripts/movie_maker_fast.py concat-relay \
     --input-dir output/movie_fast/<project> \
     --xfade 0.8 --master \
     -o output/movie_fast/<project>/<PROJECT>.mp4
   ```
4. Compose a score in `aeon-music-maker` matching your film's duration,
   using `[section: ... N seconds]` tags keyed to your emotional beats.
5. Mux: `ffmpeg -filter_complex "[0:a]volume=1.0[a0];[1:a]volume=0.28[a1];[a0][a1]amix..."`

`examples/the_strangers_tea.json` is a complete production-validated
reference: 52s medina short, 6 sequences, dialogue + lipsync + no-music
negative + custom score. End-to-end: ~7 min render + ~1 min music gen +
5 sec mux.

## Companion repos

The natural pipeline:

1. **Audio**: `aeon-radio-drama` produces dialogue + music + SFX masters from a script
2. **Video**: `aeon-movie-maker screenplay` renders the visual clips
3. **Final mux**: `aeon-movie-maker stitch` ties everything together

For non-narrative work (music videos), substitute `aeon-music-maker` for the audio and `aeon-music-video` for the editing.

## Prerequisites

- ComfyUI reachable at `${COMFYUI_URL}`
- Python 3.10+, ffmpeg + ffprobe
- ~80 GB disk for LTX 2.3 22B (fast + quality FP8 checkpoints) + always-on LoRAs + Gemma encoder

`setup.sh` checks all of this and lists download commands for any missing pieces. See `references/AGENT_CINEMA_AUTOPILOT.md` for the full agent runbook.

## Configuration

All config goes through environment variables. Copy `.env.example` to `.env` and fill in your values.

### Where to run this CLI: local vs remote ComfyUI

> ⚠️ **Movie Maker has a constraint the other AEON tools don't have:** the screenplay mode + I2V (image-to-video with seed images and last-frame carry-forward) writes intermediate seed-image PNGs into `${COMFYUI_ROOT}/input/_movie_fast_frames/<scene>/` so the ComfyUI VAE encoder can read them. This means the CLI needs **filesystem-level write access to a path that the ComfyUI server can also read**. Pure-HTTP remote mode (without shared filesystem) does NOT work for I2V or screenplay mode — only for T2V single clips.

#### Mode A — Local (CLI runs on the same machine as ComfyUI) ✓ supports everything

The simplest setup. Both processes share the same filesystem.

```bash
COMFYUI_URL=http://127.0.0.1:8188
COMFYUI_ROOT=/path/to/local/ComfyUI
```

All three subcommands (`clip`, `screenplay`, `stitch`) work without restriction.

#### Mode B — Remote (ComfyUI on a different machine)

Pick the sub-option based on whether you need I2V / screenplay carry-forward:

**B1 — Run the CLI ON the remote machine** (recommended for screenplay work):
```bash
# In .env on the REMOTE box:
COMFYUI_URL=http://127.0.0.1:8188
COMFYUI_ROOT=/path/to/ComfyUI/on/remote
```
Invoke from local terminal:
```bash
ssh ${SSH_USER}@<gpu-host> 'cd /path/to/aeon-movie-maker && python scripts/movie_maker_fast.py screenplay screenplay.json'
scp ${SSH_USER}@<gpu-host>:/path/to/output/movie_fast/<project>/finished_film.mp4 .
```
Everything stays on the remote box; you pull the final cut. ✓ I2V works. ✓ screenplay carry-forward works.

**B2 — Run CLI locally + shared filesystem** (advanced):
Use NFS / SMB / sshfs / Tailscale Files / similar to mount the remote ComfyUI's `input/` directory as a local path. Then point `COMFYUI_ROOT` at the local mount point. The local CLI writes into the shared mount; the remote ComfyUI reads from its native path. ✓ everything works, but adds infrastructure complexity.

**B3 — Run CLI locally + remote HTTP only** (T2V only):
```bash
COMFYUI_URL=http://<gpu-box-ip>:8188
COMFYUI_ROOT=./local-staging   # local dir; only used for output mp4 collection
```
Works for `clip` subcommand with **no `--seed-image`** (T2V mode). Does NOT work for screenplay mode or any I2V. The ComfyUI server can't reach your local files for VAE encoding.

### All environment variables

| Variable | Required? | Default | What it is |
|---|---|---|---|
| `COMFYUI_URL` | required | `http://127.0.0.1:8188` | ComfyUI HTTP endpoint. |
| `COMFYUI_ROOT` | **required for I2V/screenplay** | (none) | Path the CLI uses to stage seed-image frames into `input/_movie_fast_frames/`. **Must be readable by the ComfyUI server** — see "local vs remote" above. |
| `OUTPUT_DIR` | optional | `${COMFYUI_ROOT}/output` | Where rendered MP4s + clips_manifest.json land |
| `FFMPEG` / `FFPROBE` | optional | PATH lookup | Override binary paths if not on PATH |
| `HF_TOKEN` | optional | (none) | HuggingFace token for gated Lightricks/LTX-Video models. Get one at https://huggingface.co/settings/tokens (Read scope). Most users install via ComfyUI Manager and never need this. |
| `CIVITAI_TOKEN` | optional | (none) | Civitai API token for the 7 style LoRAs (cyberpunk / claymation / ghibli / galaxy / tribal / illustration / ghibli_offset). **Only needed if you actually use those `style:` tags.** Get one at https://civitai.com/user/account → API Keys. |

### How to know which model files you need

Run `./setup.sh`. It walks the canonical model paths under `${COMFYUI_ROOT}/models/` and reports what's missing. Easiest installation paths:

1. **ComfyUI Manager** (in-browser UI button) — most LTX 2.3 models are one-click installable
2. **`huggingface-cli download Lightricks/LTX-Video --include '*.safetensors'`** — for batch installs from the official HF repo
3. **Manual download** — visit https://huggingface.co/Lightricks/LTX-Video and grab the specific filenames `setup.sh` lists, place at the canonical paths

For Civitai LoRAs (style tags), search Civitai by filename to find each model's page, then download via the API URL pattern shown in `setup.sh`. License terms are set per-LoRA by the original Civitai uploader.

## Updating an existing install

```bash
cd /path/to/aeon-movie-maker
./sync.sh
```

The script:
1. **Detects local uncommitted changes** and offers to stash + re-apply them
2. **Shows a diff preview** of incoming commits + files-changed list
3. **Asks for confirmation** before pulling
4. **Refreshes Python deps** + re-runs `setup.sh` model check (so any new LTX 2.3 / LoRA additions are flagged)

### Flags

| Flag | What it does |
|---|---|
| `./sync.sh` | Default — interactive, shows diff |
| `./sync.sh --dry-run` (or `-n`) | Show what would change without pulling |
| `./sync.sh --yes` (or `-y`) | Non-interactive |
| `./sync.sh --no-models` | Skip the model file check (faster) |
| `./sync.sh --help` | Print usage |

### What if I customized something?

The sync script auto-stashes any uncommitted local edits before pulling, then re-applies them. `.env`, your `output/` directory, the staging frames at `${COMFYUI_ROOT}/input/_movie_fast_frames/`, and other personal files are gitignored — they're never touched by sync.

If you've added your own custom LoRA mappings to the `SCENE_LORAS` dict in `scripts/movie_maker_fast.py`, those local edits will be auto-stashed and re-applied. If they conflict with upstream changes (rare), sync stops with clear instructions for resolving.

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

---

## ☕ Support the work

If this release has been useful, tips are deeply appreciated — they go directly toward more compute, more models, and more open releases.

<table align="center">
  <tr>
    <td align="center" width="50%">
      <strong>₿ Bitcoin (BTC)</strong><br/>
      <img src="https://raw.githubusercontent.com/AEON-7/AEON-7/main/assets/qr/btc.png" alt="BTC QR" width="200"/><br/>
      <sub><code>bc1q09xmzn00q4z3c5raene0f3pzn9d9pvawfm0py4</code></sub>
    </td>
    <td align="center" width="50%">
      <strong>Ξ Ethereum (ETH)</strong><br/>
      <img src="https://raw.githubusercontent.com/AEON-7/AEON-7/main/assets/qr/eth.png" alt="ETH QR" width="200"/><br/>
      <sub><code>0x1512667F6D61454ad531d2E45C0a5d1fd82D0500</code></sub>
    </td>
  </tr>
  <tr>
    <td align="center" width="50%">
      <strong>◎ Solana (SOL)</strong><br/>
      <img src="https://raw.githubusercontent.com/AEON-7/AEON-7/main/assets/qr/sol.png" alt="SOL QR" width="200"/><br/>
      <sub><code>DgQsjHdAnT5PNLQTNpJdpLS3tYGpVcsHQCkpoiAKsw8t</code></sub>
    </td>
    <td align="center" width="50%">
      <strong>ⓜ Monero (XMR)</strong><br/>
      <img src="https://raw.githubusercontent.com/AEON-7/AEON-7/main/assets/qr/xmr.png" alt="XMR QR" width="200"/><br/>
      <sub><code>836XrSKw4R76vNi3QPJ5Fa9ugcyvE2cWmKSPv3AhpTNNKvqP8v5ba9JRL4Vh7UnFNjDz3E2GXZDVVenu3rkZaNdUFhjAvgd</code></sub>
    </td>
  </tr>
</table>

> **Ethereum L2s (Base, Arbitrum, Optimism, Polygon, etc.) and EVM-compatible tokens** can be sent to the same Ethereum address.
