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
- **GENEROUS dialogue durations.** Empirical formula validated in the
  `the_prince_of_two_threads` v2 production: **`duration ≥ word_count + 2 s`,
  minimum 5 s.** That's roughly 2× the spoken time — LTX needs visual
  setup before the line, the line itself, plus breath/reaction beats
  after. Earlier guidance (`0.5 × words + 1.5`) was too conservative
  and led to truncation on long lines. Examples that work:
  - 13-word line → 11 s scene
  - 18-word line → 16 s scene
  - 19-word line → 17 s scene (single scene, fits within 489-frame budget)

  If the line exceeds ~18 s × 24 fps = ~430 frames, split it across two
  consecutive scenes within the same sequence (no `transition` tag
  between them — the relay morphs smoothly).

  **Failing this, LTX truncates the dialogue mid-word and there's no fix
  in post** (the audio simply isn't generated).
- **Enrich descriptions with explicit pre/post-dialogue action cues**
  when scene `duration` exceeds ~7 s. Without action beats the longer
  scene reads as a static character holding still. The pattern:
  `<setup> ... Before speaking, <trigger action>. After speaking with
  <emotional register>, <reaction action>.`
- **Use `--xfade 0` (hard cuts) at concat-relay time for dialogue-heavy
  films.** Crossfade `> 0` acrossfades audio between sequences and clips
  dialogue tails/heads when a sequence ends or starts on a spoken line.
- **CFG 1.5 is the sweet spot for the relay path** on distilled-fp8.
  CFG 1.0 disables negative prompt; CFG ≥ 2.0 fries visuals. The script
  defaults to 1.5 if you don't pass `--cfg` explicitly.
- **Audio post-production cleanup** — see AGENTS.md "Step 3.5" for the
  ASR-verify workflow + mute pattern. Most LTX renders need at least a
  spot-check pass on dialogue-less sequences (some get nice ambient
  narration, some get word-salad gibberish that needs muting).

## Files

| file | what it is | length | render time on Spark (canonical settings) |
|---|---|---|---|
| `the_strangers_tea.json` | Romantic-mystery short — Western traveler gets lost in a Middle Eastern medina, is found by a local woman, tea-ceremony reveal of intergenerational family connection. **Act 1 / setup.** 12 scenes / 6 sequences / 52s. | 52 s | ~7 min |
| `the_strangers_tea_part_2.json` | **Act 2-3 continuation** of the medina story — palace under threat from Leila's brother Hassan, Daniel and Leila search for grandfather's hidden inheritance, climactic confrontation in the courtyard, family reconciliation. 32 scenes / 16 sequences / 138s. Demonstrates 3-character dialogue + multi-act structure + the tack-on pattern (concatenate after part 1 → 3:10 full film). | 138 s | ~21 min |
| `cosmic_guardians.json` | Mythological action — Vishnu and Shiva manifest to defend the cosmos, exchange brief dialogue. Single-act compact format. 6 scenes / 3 sequences / 22s. | 22 s | ~3 min |
| `the_prince_of_two_threads.json` | **Flagship 4-act epic.** Ancient Persia / Zoroastrian cosmology — Prince Darius is touched by Ahriman (becomes half-obsidian / half-flesh with time-bending powers), partners with Ahura Mazda, seals the dark in the crystal tree of life, civilization advances to intergalactic exploration carrying the tree's healing fruit. Frame story: child at the tree closes the circle. Demonstrates 5-character cast, multi-act structure, transformation arc, frame story, generous-duration dialogue scenes (16-17 s for the long Ahura Mazda speeches with explicit pre/post-dialogue action cues — every word lands clean, zero truncation). 53 scenes / 27 sequences / 330 s (5:30). | 330 s | ~95 min @ CFG 1.5 |

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

## Audio production (the part that actually sells the film)

Generating the video is half the job. The other half is the audio mix —
this is where amateur AI films feel artificial and good ones feel real.
Production-validated patterns from `the_prince_of_two_threads` v4:

- **Custom score via `aeon-music-maker`** (REQUIRED dep, see AGENTS.md
  §4e). Don't roll your own ACE-Step ComfyUI workflow — the wrong node
  selection (SD3 instead of AuraFlow, 50 steps + CFG 5 instead of 10/1
  on the distilled `xl_turbo`) produces noise. The sister repo handles
  it correctly.
- **ACE-Step caps at ~240 s per generation.** Films longer than ~4 min
  need to be **scored in cues** — multiple short pieces, each matched to
  a story pivot, concatenated with `acrossfade=d=2`. Aim for 5-10 cues
  per film. See AGENTS.md Recipe D Step 2 for the full cue-design
  methodology.
- **Identify pivots from the chunker output + the `transition` tags.**
  Each `transition`-tagged scene is a candidate cue boundary because it's
  where the screenwriter wanted a hard tonal change. Group consecutive
  same-mood sequences into one cue, change cues at character entrances,
  tonal flips (dread → revelation, struggle → renewal), and time-stop /
  supernatural moments.
- **Cohesion across cues comes from**: shared instrument palette,
  shared tonic key (with modulations), sequential seeds (729183, 729184,
  …), and a recurring melodic theme that hints early, emerges fully at
  the first revelation, gets transformed mid-film, and resolves
  triumphant in the final cue. We called ours `FRASHOKERETI THEME`.
- **Always use `--master orchestral`** for cinematic scores — preserves
  dynamics, hits a consistent LUFS target across cues.
- **Per-sequence dialogue normalization** is mandatory for multi-scene
  films. LTX 2.3 renders dialogue with up to 23 LU inter-sequence
  variation (some lines feel like a whisper next to others). Use
  `tools/normalize_dialogue.py` (target -23 dB mean, peak ceiling
  -1.5 dBTP, 48 kHz forced).
- **Don't sidechain-duck the score under dialogue.** It strips the
  music's life. Fix the dialogue source loudness instead, then mix at
  fixed levels (`dialogue=1.0, score=0.25, normalize=0`).
- **DO NOT use `loudnorm linear=true`** for dialogue normalization —
  it upsamples to 96 kHz internally, which causes container-level
  audio dropouts when the AAC encoder retains that rate. Use simple
  `volumedetect` measurement + `volume=NdB` filter (what
  `tools/normalize_dialogue.py` does).
- **Force `-ar 48000`** on every audio re-encode in the chain.

See `AGENTS.md` Recipe D for the complete step-by-step.
