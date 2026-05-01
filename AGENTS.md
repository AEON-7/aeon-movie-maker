# AGENTS.md — aeon-movie-maker

Instructions for AI agents that operate this tool.

## When to invoke

- User asks for a "film", "movie", "cinematic video", "short film", "music video with cinematic clips"
- User wants character consistency across multiple shots
- User wants the speed of LTX 2.3 (vs. the older WAN-based pipelines that take 10×+ longer)

For pure audio-reactive editing of already-generated clips, use `aeon-music-video` instead. For the audio pass of a narrative film, use `aeon-radio-drama` and feed its output into this repo's `stitch` command.

## Setup contract

`./setup.sh` once. Idempotent. Verifies:
- ComfyUI reachable at `${COMFYUI_URL}`
- Python deps (`requirements.txt`)
- ffmpeg + ffprobe
- LTX 2.3 22B model files in `${COMFYUI_ROOT}/models/diffusion_models/`
- Gemma abliterated encoder in `${COMFYUI_ROOT}/models/text_encoders/`
- VBVR physics LoRA + IC-LoRA in `${COMFYUI_ROOT}/models/loras/`

The setup script lists download commands (huggingface-cli + curl) for anything missing.

## Invocation contract

Always call the CLI — never reconstruct ComfyUI workflows by hand.

### Single clip

```bash
python scripts/movie_maker_fast.py clip \
    --prompt "<descriptor cloud>" \
    --duration <seconds, 3–8 typical> \
    --mode <fast|quality|abstract> \
    --output <path>.mp4
```

Add `--seed-image <jpg>` for I2V continuity, `--audio-reference <wav>` for A2V (forces `quality` mode), `--persistence 0.0–1.0` to control how strictly the seed image constrains the output.

### Screenplay (multi-shot film)

```bash
python scripts/movie_maker_fast.py screenplay <screenplay>.json
```

Schema in `SKILL.md` § Screenplay format. Outputs:
- `output/movie_fast/<project>/<scene_id>.mp4` per scene
- `output/movie_fast/<project>/clips_manifest.json` for the stitcher

### Stitch (final mux)

```bash
python scripts/movie_maker_fast.py stitch \
    <clips_manifest>.json \
    --dialogue <wav> --music <wav> --sfx <wav> \
    -o <finished_film>.mp4
```

Sidechain ducks music/SFX 12 dB under dialogue, then loudnorm I=-16:TP=-1.5:LRA=11 (broadcast standard).

## Mode selection

| Mode | When to use | Speed | Notes |
|---|---|---|---|
| `fast` | Default, realistic content with motion | ~3–5 s wall per s output | LTX 2.3 22B distilled fp8 + VBVR physics LoRA |
| `quality` | Audio-driven (A2V), max fidelity, joint AV | ~10–15 s wall per s output | LTX 2.3 EROS — also forced when `--audio-reference` is set |
| `abstract` | Fractals, motion graphics, non-realistic | Same as fast | Drops VBVR physics LoRA — better for non-realistic content |

## Prompt engineering

Cinematic prompts work best as comma-separated descriptor clouds:

```
genre: drone shot / low angle / over-the-shoulder / close-up
subject: <what's in frame>
action: <what's happening>
mood: cinematic, moody, golden hour, neon-lit, ...
quality: depth of field, film grain, anamorphic, IMAX, ...
```

For continuity across shots, the screenplay's `characters` dict provides per-character seed offsets. **Don't repeat character descriptions in every scene's prompt** — the screenplay command merges them automatically based on which characters appear in which scene.

For abstract/fractal content (DMT visuals, audio-reactive art), use `--mode abstract` and emphasize geometric / mathematical / synthesis vocabulary in the prompt. See the `aeon-music-video` skill for audio-reactive editing of these.

## Companion repos

| Need | Use |
|---|---|
| Audio for the film (dialogue + music + SFX) | `aeon-radio-drama` (full pipeline) |
| Music score only | `aeon-music-maker` |
| Audio-reactive music video editing | `aeon-music-video` |
| Base ComfyUI stack with all models pre-staged | `comfyui-aeon-spark` |

## Failure modes

| Symptom | Fix |
|---|---|
| `Submit failed: 400` with node validation error | Custom node missing or Gemma encoder not on disk → `./sync.sh` |
| First clip is slow (~80 s) but subsequent ones fast | Normal — cold load of 27 GB checkpoint + 12 GB encoder. Render one throwaway 3 s clip to warm the cache. |
| OOM on a 7 s clip | Fast mode needs ~20 GB VRAM with models warm. Reduce to 768×432 or restart ComfyUI. |
| Faces drift between clips | No character consistency configured. Pass same `--seed` and ensure `characters` dict is consistent across scenes. |
| Audio out of sync in stitched film | Dialogue master built independently of clips manifest. Use `radio_drama.py` to build the dialogue master at fixed offsets matching scene timings. |
| HTTP 400 with `value_not_in_list` | Path uses `/` instead of `\` on Windows-hosted ComfyUI. Tool handles this via `_SEP` — check no manual edits to model name strings. |

## What's NOT yet wired

(Documented in `SKILL.md` § "What's NOT yet wired" so future agents don't re-invent.)

- IC-LoRA reference images per character (would supplement seed-offset character consistency)
- DWPose-driven motion control
- Optional super-resolution + frame interpolation post-pass for 1536×832 + 60 fps output
- Timeline-aware audio placement (currently treats audio as full-length masters; could place SFX at specific scene timestamps via `adelay`)
- Auto dialogue-master assembly from per-line TTS WAVs
