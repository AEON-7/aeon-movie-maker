#!/usr/bin/env bash
# setup.sh — first-time install for aeon-movie-maker.
set -euo pipefail
[[ -f .env ]] && { set -a; source .env; set +a; }

COMFYUI_URL="${COMFYUI_URL:-http://127.0.0.1:8188}"
COMFYUI_ROOT="${COMFYUI_ROOT:-}"

c_red(){ printf '\033[31m%s\033[0m\n' "$*"; }
c_grn(){ printf '\033[32m%s\033[0m\n' "$*"; }
c_yel(){ printf '\033[33m%s\033[0m\n' "$*"; }
c_blu(){ printf '\033[36m%s\033[0m\n' "$*"; }

c_blu "==> aeon-movie-maker setup"

c_blu "[1/4] ComfyUI at $COMFYUI_URL"
if curl -sf "$COMFYUI_URL/system_stats" >/dev/null 2>&1; then
    c_grn "      ✓ reachable"
else
    c_red "      ✗ ComfyUI not reachable. Start it then re-run."
    exit 1
fi

c_blu "[2/4] Python dependencies"
python -m pip install --quiet --upgrade pip
python -m pip install --quiet -r requirements.txt
c_grn "      ✓ deps installed"

c_blu "[3/4] ffmpeg + ffprobe"
ff="${FFMPEG:-ffmpeg}"; fp="${FFPROBE:-ffprobe}"
if command -v "$ff" >/dev/null && command -v "$fp" >/dev/null; then
    c_grn "      ✓ found"
else
    c_red "      ✗ missing — install via brew/apt or download from ffmpeg.org"
    exit 1
fi

c_blu "[4/4] Model file check"
cat <<'EOF'

      ╔══════════════════════════════════════════════════════════════════╗
      ║ EXACT FILENAMES + PATHS BELOW — must match what the script loads ║
      ║ (filenames are case-sensitive on Linux; the 'ltx2/' subfolder is ║
      ║ NOT optional — keep the directory structure as written)          ║
      ╚══════════════════════════════════════════════════════════════════╝

      RECOMMENDED installer: use comfyui-aeon-spark which downloads all canonical files
      automatically (https://github.com/AEON-7/comfyui-aeon-spark — see its download_models.py).
      The paths below are what comfyui-aeon-spark produces; manual installs must match exactly.

      LTX 2.3 22B base models (canonical sources: Comfy-Org/ltx-2 + Lightricks/LTX-2.3 + Lightricks/LTX-2.3-fp8):
        models/checkpoints/ltx-2.3-22b-distilled-fp8.safetensors                 (~22 GB, REQUIRED for 'fast' + 'abstract' modes)
        models/checkpoints/ltx-2.3-22b-dev-fp8.safetensors                       (~29 GB, REQUIRED for 'quality' mode — non-distilled FP8)

      Video VAE:
        models/vae/LTX23_video_vae_bf16.safetensors                              (REQUIRED — Kijai/LTX2.3_comfy)

      Text encoder (Comfy-Org split-files layout):
        models/text_encoders/gemma_3_12B_it.safetensors                          (~24 GB, REQUIRED — base Gemma-3 12B IT)

      Abliteration LoRA (apply on top of Gemma encoder for uncensored prompting):
        models/loras/gemma-3-12b-it-abliterated_heretic_lora_rank64_bf16.safetensors
                                                                                 (REQUIRED if you need uncensored output. NOT auto-loaded by
                                                                                  movie_maker_fast.py because always_on_loras only routes to the
                                                                                  diffusion model — wire it into a custom workflow's CLIP loader
                                                                                  if you want abliteration applied automatically.)

      Always-on LoRAs (auto-loaded by movie_maker_fast.py — diffusion-model side):
        models/loras/ltx-2.3-22b-ic-lora-union-control-ref0.5.safetensors        (REQUIRED — composition control, applied to both fast + quality modes)
        models/loras/ltx2/Ltx2.3-Licon-VBVR-I2V-96000-R32.safetensors            (REQUIRED — VBVR physics, applied to fast + quality modes)
        models/loras/ltx-2.3-22b-distilled-lora-384.safetensors                  (REQUIRED for quality mode — distill assist on the non-distilled
                                                                                  dev-fp8 base; note: NO ltx2/ prefix — file lives at the root of loras/)

      Optional camera/style/control LoRAs (loaded only when screenplay tags request them):
        models/loras/ltx-2-19b-lora-camera-control-dolly-left.safetensors        ('camera: dolly-left')
        models/loras/ltx2/ltx-2-19b-lora-camera-control-jib-down.safetensors     ('camera: jib-down')
        models/loras/ltx2/ltx23_zoomout_z00m047.safetensors                      ('zoomout' / inferred from prompt)
        models/loras/ltx2/ltx23__demopose_d3m0p0s3.safetensors                   ('pose: demo')
        models/loras/ltx2.3-transition.safetensors                               ('transition' — auto-added at scene boundaries)
        models/loras/ltx-2.3-id-lora-talkvid-3k.safetensors                      ('character: talkinghead')

      Style LoRAs (CIVITAI-HOSTED — needs CIVITAI_TOKEN, not HF_TOKEN):
        models/loras/CyberPunkAI.safetensors                                     (cyberpunk style preset)
        models/loras/Smooth_Tribal.safetensors                                   (tribal/ornamental style preset)
        models/loras/ltx2/Claymation.safetensors                                 (stop-motion / clay style preset)
        models/loras/ltx2/LTX23-GalaxyAce.safetensors                            (cosmic / nebula style preset)
        models/loras/StudioGhibli.Redmond-StdGBRRedmAF-StudioGhibli.safetensors  (Ghibli watercolor style)
        models/loras/ghibli_style_offset.safetensors                             (lighter Ghibli shift)
        models/loras/Illustration concept Variant 3A.safetensors                 (illustrative / graphic style)

      To download Civitai LoRAs:
        1. Sign in to https://civitai.com and create an API key at /user/account
        2. Set CIVITAI_TOKEN in your .env file
        3. Search for each LoRA name on civitai.com, find the model version page
        4. Download URL pattern:
             curl -L --create-dirs \
               -H "Authorization: Bearer $CIVITAI_TOKEN" \
               -o "$COMFYUI_ROOT/models/loras/<name>.safetensors" \
               "https://civitai.com/api/download/models/<version_id>"
        5. The 'ltx2/' subfolder is convention used by movie_maker_fast.py — keep it.

      Style LoRAs are OPTIONAL — only needed if your screenplay uses 'style: cyberpunk',
      'style: tribal', 'style: claymation', 'style: ghibli', 'style: ghibli_offset',
      'style: galaxy', or 'style: illustration' tags. Plain prompts work without any
      of them.

EOF
if [[ -z "$COMFYUI_ROOT" ]]; then
    c_yel "      COMFYUI_ROOT not set — can't check local presence. Verify on your ComfyUI host."
else
    REQUIRED=(
        "checkpoints/ltx-2.3-22b-distilled-fp8.safetensors"
        "vae/LTX23_video_vae_bf16.safetensors"
        "text_encoders/gemma_3_12B_it.safetensors"
        "loras/gemma-3-12b-it-abliterated_heretic_lora_rank64_bf16.safetensors"
        "loras/ltx-2.3-22b-ic-lora-union-control-ref0.5.safetensors"
        "loras/ltx2/Ltx2.3-Licon-VBVR-I2V-96000-R32.safetensors"
    )
    OPTIONAL=(
        # 'quality' mode — non-distilled FP8 base + matching distill LoRA
        "checkpoints/ltx-2.3-22b-dev-fp8.safetensors"
        "loras/ltx-2.3-22b-distilled-lora-384.safetensors"
    )
    missing=()
    for m in "${REQUIRED[@]}"; do
        [[ -f "$COMFYUI_ROOT/models/$m" ]] || missing+=("$m")
    done
    if [[ ${#missing[@]} -eq 0 ]]; then
        c_grn "      ✓ all required models present"
    else
        c_yel "      ${#missing[@]} required model(s) missing:"
        for m in "${missing[@]}"; do echo "        - $m"; done
        c_yel "      Recommended: install via comfyui-aeon-spark (handles all 28+ files with"
        c_yel "      resumable HF downloads, retries, and gated-repo token handling):"
        c_yel "        git clone https://github.com/AEON-7/comfyui-aeon-spark"
        c_yel "        cd comfyui-aeon-spark && python download_models.py --workspace \$COMFYUI_ROOT/.."
        c_yel "      Or manually: download from the canonical HF repos listed above and place"
        c_yel "      at the exact paths shown in the model checklist."
    fi
    # Optional models — quality mode + A2V
    opt_missing=()
    for m in "${OPTIONAL[@]}"; do
        [[ -f "$COMFYUI_ROOT/models/$m" ]] || opt_missing+=("$m")
    done
    if [[ ${#opt_missing[@]} -gt 0 ]]; then
        c_yel "      Optional (quality mode) — ${#opt_missing[@]} not present:"
        for m in "${opt_missing[@]}"; do echo "        - $m"; done
        c_yel "      Skip these unless you'll run '--mode quality'."
    fi
fi

echo ""
c_grn "==> Setup complete."
c_blu "    Smoke test:"
echo '      python scripts/movie_maker_fast.py clip \'
echo '          --prompt "drone shot, misty pine forest, dawn, cinematic" \'
echo '          --duration 4 --output forest.mp4'
