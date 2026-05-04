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
- **Long dialogue lines (>12 words) need duration ≥ 7s OR a scene split.**
  LTX 2.3's audio head needs ~0.5s per spoken word + 1.5s buffer. Lines
  that exceed the scene's frame budget get truncated mid-word with no fix
  in post — the audio simply isn't generated. Either bump the scene's
  `duration` to give the model enough frames, or split the line across two
  consecutive scenes within the same sequence (smooth morph keeps the
  visual continuous). See `the_prince_of_two_threads.json` scene 30 for an
  example of where this bit us — Ahura Mazda's 19-word line at
  `duration: 5.0` got truncated to "...Make of." (should have been "Make
  him follow you in.").
- **Use `--xfade 0` (hard cuts) at concat-relay time for dialogue-heavy
  films.** Crossfade `> 0` acrossfades audio between sequences and clips
  dialogue tails/heads when a sequence ends or starts on a spoken line.

## Files

| file | what it is | length | render time on Spark (canonical settings) |
|---|---|---|---|
| `the_strangers_tea.json` | Romantic-mystery short — Western traveler gets lost in a Middle Eastern medina, is found by a local woman, tea-ceremony reveal of intergenerational family connection. **Act 1 / setup.** 12 scenes / 6 sequences / 52s. | 52 s | ~7 min |
| `the_strangers_tea_part_2.json` | **Act 2-3 continuation** of the medina story — palace under threat from Leila's brother Hassan, Daniel and Leila search for grandfather's hidden inheritance, climactic confrontation in the courtyard, family reconciliation. 32 scenes / 16 sequences / 138s. Demonstrates 3-character dialogue + multi-act structure + the tack-on pattern (concatenate after part 1 → 3:10 full film). | 138 s | ~21 min |
| `cosmic_guardians.json` | Mythological action — Vishnu and Shiva manifest to defend the cosmos, exchange brief dialogue. Single-act compact format. 6 scenes / 3 sequences / 22s. | 22 s | ~3 min |
| `the_prince_of_two_threads.json` | **Flagship 4-act epic.** Ancient Persia / Zoroastrian cosmology — Prince Darius is touched by Ahriman (becomes half-obsidian / half-flesh with time-bending powers), partners with Ahura Mazda, seals the dark in the crystal tree of life, civilization advances to intergalactic exploration carrying the tree's healing fruit. Frame story: child at the tree closes the circle. Demonstrates 5-character cast, multi-act structure, transformation arc, frame story, 53 scenes / 23 sequences / 234 s (3:54). | 234 s | ~50 min @ CFG 1.5 |

## How to render

```bash
# Render at canonical settings (CFG 1.5 is current sweet spot for distilled-fp8)
python scripts/movie_maker_fast.py screenplay examples/the_strangers_tea.json \
    --use-relay \
    --width 832 --height 480 \
    --cfg 1.5 \
    --output-dir output/movie_fast/the_strangers_tea

# Concat with HARD CUTS (preserves dialogue at sequence boundaries) +
# write both yuv420p distribution and yuv444p10le master siblings:
python scripts/movie_maker_fast.py concat-relay \
    --input-dir output/movie_fast/the_strangers_tea \
    --xfade 0 --master \
    -o output/movie_fast/the_strangers_tea/THE_STRANGERS_TEA.mp4
```

Add a custom score generated via the sister
[`aeon-music-maker`](https://github.com/AEON-7/aeon-music-maker) tool, then
mux it underneath the dialogue track — see the
**Production workflow: dialogue + custom music** section in the top-level
[README](../README.md).
