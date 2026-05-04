# Reference screenplays

Production-validated screenplay JSONs for the Prompt Relay flow
(`screenplay --use-relay`). Both demonstrate the patterns that survived end-
to-end render testing on DGX Spark:

- Top-level **`characters`** dict mapping name → full visual description (the
  thing that actually anchors identity across sequences — names alone aren't
  enough, the relay needs visual specificity).
- Top-level **`negative_prompt`** field listing music + anatomy negatives so
  the joint-A/V audio output is dialogue + ambient ONLY (no model-generated
  music to fight with the score you'll add in post via aeon-music-maker).
- **Dialogue lines** in scene `dialogue` arrays — these get forwarded into
  the relay prompt as `'CHARACTER says "line"'` patterns, which is what
  triggers LTX 2.3's lipsync + voice generation.
- **Visual action AFTER dialogue** in the LAST scene of each sequence —
  prevents the dialogue from getting cut off at the segment boundary (an
  early bug we hit on the cosmic_guardians v1 render).
- **`tags: ["transition"]`** on scenes that should start a new Prompt Relay
  sequence (i.e. force a hard cut). Within a sequence: smooth morphing.

## Files

| file | what it is | length | render time on Spark (canonical settings) |
|---|---|---|---|
| `the_strangers_tea.json` | Romantic-mystery short — Western traveler gets lost in a Middle Eastern medina, is found by a local woman, tea-ceremony reveal of intergenerational family connection. **Act 1 / setup.** 12 scenes / 6 sequences / 52s. | 52 s | ~7 min |
| `the_strangers_tea_part_2.json` | **Act 2-3 continuation** of the medina story — palace under threat from Leila's brother Hassan, Daniel and Leila search for grandfather's hidden inheritance, climactic confrontation in the courtyard, family reconciliation. 32 scenes / 16 sequences / 138s. Demonstrates 3-character dialogue + multi-act structure + the tack-on pattern (concatenate after part 1 → 3:10 full film). | 138 s | ~21 min |
| `cosmic_guardians.json` | Mythological action — Vishnu and Shiva manifest to defend the cosmos, exchange brief dialogue. Single-act compact format. 6 scenes / 3 sequences / 22s. | 22 s | ~3 min |

## How to render

```bash
# Render
python scripts/movie_maker_fast.py screenplay examples/the_strangers_tea.json \
    --use-relay \
    --output-dir output/movie_fast/the_strangers_tea

# Then concatenate the per-sequence MP4s (they're already joint A/V)
cd output/movie_fast/the_strangers_tea
ls sequence_*.mp4 | sed -E "s/^/file '/;s/$/'/" > concat.txt
ffmpeg -f concat -safe 0 -i concat.txt -c copy THE_STRANGERS_TEA.mp4
```

Add a custom score generated via the sister
[`aeon-music-maker`](https://github.com/AEON-7/aeon-music-maker) tool, then
mux it underneath the dialogue track — see the
**Production workflow: dialogue + custom music** section in the top-level
[README](../README.md).
