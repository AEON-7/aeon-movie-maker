# Attribution

`aeon-movie-maker` orchestrates the LTX 2.3 video pipeline. Full credit to:

## Models

### LTX 2.3 22B (distilled fp8) + EROS
- **Authors:** Lightricks
- **HuggingFace:** https://huggingface.co/Lightricks/LTX-Video
- **Repository:** https://github.com/Lightricks/LTX-Video
- The distilled fp8 variant (`ltxv-2b-0.9.7-distilled-fp8_e4m3fn`) provides ~3-5x wall-time per output second on a 5090.
- The EROS variant supports joint AV (audio-driven generation via `LTXVReferenceAudio`).

### VBVR physics LoRA
- The Verifier-Based Video Refinement (VBVR) physics LoRA improves motion realism in the LTX fast pipeline. Sourced from the ltxv community on HuggingFace.

### Gemma abliterated encoder (text encoder)
- Quantized GGUF (Q6_K) of an abliterated `gemma-3-12b-it` variant, used as the LTX text encoder.
- HuggingFace: search for `gemma-3-12b-it-abliterated`.

### IC-LoRA Union (optional)
- Composition control via reference frames. Used for character continuity when seed-offset alone isn't enough.

### Style LoRAs (Civitai-hosted, optional)

The following LoRAs are referenced by `style:` tags in screenplay JSON. They are hosted on [Civitai](https://civitai.com) and require a Civitai API token (`CIVITAI_TOKEN` in `.env`) for download. All are optional — plain prompts without `style:` tags don't need any of them.

| Style tag | LoRA filename | Source | Description |
|---|---|---|---|
| `style: cyberpunk` | `CyberPunkAI.safetensors` | Civitai community LoRA | Neon / tech noir aesthetic |
| `style: tribal` | `Smooth_Tribal.safetensors` | Civitai community LoRA | Ornamental / pattern-rich |
| `style: claymation` | `Claymation.safetensors` | Civitai community LoRA, LTX-targeted | Stop-motion / clay |
| `style: ghibli` | `StudioGhibli.Redmond-StdGBRRedmAF-StudioGhibli.safetensors` | Civitai community LoRA | Ghibli watercolor |
| `style: ghibli_offset` | `ghibli_style_offset.safetensors` | Civitai community LoRA | Lighter Ghibli shift |
| `style: galaxy` | `LTX23-GalaxyAce.safetensors` | Civitai community LoRA, LTX 2.3-targeted | Cosmic / nebula / starfield |
| `style: illustration` | `Illustration concept Variant 3A.safetensors` | Civitai community LoRA | Illustrative / graphic |

Search Civitai by filename to find each model's page; the API download URL pattern is `https://civitai.com/api/download/models/<version_id>` with `Authorization: Bearer $CIVITAI_TOKEN`. License terms are set per-LoRA by the original Civitai uploader — check each model's page before redistribution. **This repo does not bundle or redistribute these LoRA weights** — users must download them themselves under the original LoRA license terms.

## ComfyUI custom nodes

Most LTX 2.3 nodes are in mainline ComfyUI. The full set:
- `LTXAVTextEncoderLoader`, `LTXAVDualCLIPEncode`, `LTXVImgToVideoInplace`, `LTXVBaseSampler`, `LTXVEmptyLatentAudio`, `LTXVSeparateAVLatent`, `LTXVReferenceAudio`, `LTXVImageEncoderForA2V`
- Standard: `UNETLoader`, `VAELoader`, `LoraLoader`, `KSamplerSelect`, `BasicScheduler`, `RandomNoise`, `SamplerCustomAdvanced`, `SaveVideo`

## Audio mix chain

The `stitch` subcommand uses [FFmpeg](https://www.ffmpeg.org/) for sidechain ducking + final loudnorm. Filter chain documented in the `aeon-radio-drama` repo's `references/mixing-guide.md`.

## Pipeline-specific design notes

- **Last-frame carry-forward**: between sequential clips in a screenplay, the final frame of clip N is exported as a JPG and re-injected as the seed image for clip N+1, preserving character + lighting + composition continuity.
- **Persistence knob**: scales the i2v denoise strength inversely (0 = full transformation, 1 = locked to seed). Original to this project.
- **Per-character seed offsets**: stable hash from character name → small integer added to the base seed. Same character = same hash = same offset = same visual identity across an entire screenplay.
- **Per-scene LoRA routing**: maps `style_tags` in screenplay JSON to LoRA file selection at workflow-build time.

## License notes

This repo is MIT-licensed. Models retain their own licenses — refer to:
- LTX-Video: https://huggingface.co/Lightricks/LTX-Video for license terms (research / commercial conditions vary)
- Gemma: Google's Gemma license terms apply
