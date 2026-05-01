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

      LTX 2.3 22B + EROS (video generation, both modes):
        models/diffusion_models/ltxv-2b-0.9.7-distilled-fp8_e4m3fn.safetensors  (~22 GB, REQUIRED for fast mode)
        models/diffusion_models/ltxv-eros-9.7b.safetensors                       (~30 GB, REQUIRED for quality + A2V)

      Text encoder (abliterated Gemma):
        models/text_encoders/google_gemma-3-12b-it-abliterated-v2-Q6_K.gguf      (~9.5 GB, REQUIRED)

      LoRAs:
        models/loras/ltxv-physics-vbvr.safetensors                               (REQUIRED for fast mode physics)
        models/loras/ltxv-ic-lora-union.safetensors                              (optional, for IC-LoRA composition)

      Audio VAE (only needed for A2V quality mode):
        models/vae/ltxv-audio-vae.safetensors                                    (~250 MB, REQUIRED for --audio-reference)

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
        "diffusion_models/ltxv-2b-0.9.7-distilled-fp8_e4m3fn.safetensors"
        "text_encoders/google_gemma-3-12b-it-abliterated-v2-Q6_K.gguf"
        "loras/ltxv-physics-vbvr.safetensors"
    )
    missing=()
    for m in "${REQUIRED[@]}"; do
        [[ -f "$COMFYUI_ROOT/models/$m" ]] || missing+=("$m")
    done
    if [[ ${#missing[@]} -eq 0 ]]; then
        c_grn "      ✓ required models present"
    else
        c_yel "      ${#missing[@]} required model(s) missing:"
        for m in "${missing[@]}"; do echo "        - $m"; done
        c_yel "      Use ComfyUI Manager or huggingface-cli to fetch."
    fi
fi

echo ""
c_grn "==> Setup complete."
c_blu "    Smoke test:"
echo '      python scripts/movie_maker_fast.py clip \'
echo '          --prompt "drone shot, misty pine forest, dawn, cinematic" \'
echo '          --duration 4 --output forest.mp4'
