# aeon-movie-maker


[![☕ Tips](https://img.shields.io/badge/%E2%98%95_Tips-Support_the_work-ff5e5b?style=flat)](https://github.com/AEON-7/AEON-7#-support-the-work)
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
4. **Refreshes Python deps** + re-runs `setup.sh` model check (so any new LTX 2.3 / EROS / LoRA additions are flagged)

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
