#!/usr/bin/env python3
"""
normalize_dialogue.py — per-sequence dialogue loudness normalization

LTX 2.3 renders dialogue with huge inter-sequence loudness variation —
up to 23 LU spread across a single film (e.g. one sequence at -10 LUFS,
another at -33 LUFS). Without normalization, the quiet dialogue scenes
feel buried even at consistent music levels.

This tool brings each sequence's audio to a consistent target via simple
per-sequence gain measurement. Video stream is copied untouched; audio is
re-encoded at 48 kHz AAC.

Why simple `volume=NdB` and NOT ffmpeg's `loudnorm` filter:
  loudnorm with `linear=true` internally upsamples to 96 kHz for
  precision, leaving the output stream at 96 kHz. AAC encoded at 96 kHz
  in an MP4 container can produce intermittent decoder dropouts in some
  players (and shortens the apparent audio duration). Plain volumedetect
  measure + volume=NdB filter avoids the resample entirely.

Usage:
  # Normalize all sequences in cleaned/ to ~-23 dB mean
  python tools/normalize_dialogue.py \\
      --input-dir output/movie_fast/MY_FILM/cleaned \\
      --output-dir output/movie_fast/MY_FILM/normalized \\
      --target-mean-db -23 --peak-ceiling-db -1.5

  # Force-mute specific sequences (e.g. ones that had narrator hallucinations)
  python tools/normalize_dialogue.py \\
      --input-dir output/movie_fast/MY_FILM/cleaned \\
      --output-dir output/movie_fast/MY_FILM/normalized \\
      --force-silent 23,24,26

After normalization, re-run `concat-relay --xfade 0 --master` on the
normalized/ dir to produce a NORMALIZED.mp4 with consistent dialogue.
"""

import argparse, re, subprocess, sys
from pathlib import Path


def measure_db(mp4_path):
    """Return (mean_db, max_db) tuple via volumedetect."""
    p = subprocess.run([
        "ffmpeg", "-hide_banner", "-i", str(mp4_path),
        "-af", "volumedetect", "-f", "null", "-"
    ], capture_output=True, text=True)
    mean = re.search(r"mean_volume:\s*(-?[\d.]+)\s*dB", p.stderr)
    peak = re.search(r"max_volume:\s*(-?[\d.]+)\s*dB", p.stderr)
    return (float(mean.group(1)) if mean else None,
            float(peak.group(1)) if peak else None)


def normalize(in_mp4, out_mp4, target_mean_db, peak_ceiling_db, force_silent):
    """If force_silent, output volume=0. Otherwise apply gain to hit
    target_mean_db (clamped so peak doesn't exceed peak_ceiling_db)."""
    if force_silent:
        af = "volume=0"
        msg = "force-muted"
    else:
        mean, peak = measure_db(in_mp4)
        if mean is None or peak is None:
            af = "volume=0"
            msg = "couldn't measure (silent?), keeping silent"
        elif mean < -50:
            # Effectively silent input — don't amplify noise floor
            af = "volume=0"
            msg = f"input below -50 dB ({mean:.1f}), keeping silent"
        else:
            desired = target_mean_db - mean
            max_safe = peak_ceiling_db - peak
            applied = min(desired, max_safe)
            af = f"volume={applied:+.2f}dB"
            msg = (f"was mean={mean:+.1f} peak={peak:+.1f} → "
                   f"gain {applied:+.1f} dB → "
                   f"mean ~{mean+applied:+.1f} peak ~{peak+applied:+.1f}")

    subprocess.run([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(in_mp4),
        "-c:v", "copy",
        "-af", af,
        "-c:a", "aac", "-b:a", "192k", "-ar", "48000",  # FORCE 48 kHz
        "-movflags", "+faststart",
        str(out_mp4),
    ], check=True)
    return msg


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                  formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--input-dir", required=True,
                    help="Directory of source sequence_*.mp4 files (e.g. cleaned/)")
    ap.add_argument("--output-dir", required=True,
                    help="Output directory for normalized sequences")
    ap.add_argument("--target-mean-db", type=float, default=-23.0,
                    help="Target mean RMS in dBFS (default: -23)")
    ap.add_argument("--peak-ceiling-db", type=float, default=-1.5,
                    help="Peak ceiling in dBTP (default: -1.5)")
    ap.add_argument("--force-silent", default="",
                    help="Comma-separated sequence indices to force-mute (e.g. '23,24,26')")
    args = ap.parse_args()

    silent_set = set(int(x) for x in args.force_silent.split(",") if x.strip())
    in_dir = Path(args.input_dir)
    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    seqs = sorted(in_dir.glob("sequence_*.mp4"))
    if not seqs:
        print(f"No sequence_*.mp4 found in {in_dir}", file=sys.stderr)
        sys.exit(1)

    print(f"Found {len(seqs)} sequences. "
          f"Target mean: {args.target_mean_db} dB, peak ceiling: {args.peak_ceiling_db} dB")
    if silent_set:
        print(f"Force-silent: {sorted(silent_set)}")
    print()

    for i, mp4 in enumerate(seqs):
        out_mp4 = out_dir / mp4.name
        force = i in silent_set
        marker = "🔇" if force else "🔊"
        msg = normalize(mp4, out_mp4, args.target_mean_db,
                        args.peak_ceiling_db, force)
        print(f"  {marker} SEQ {i:02d} {mp4.name:55s}  {msg}")

    print(f"\n✓ Normalized outputs in: {out_dir}")
    print(f"  Next step: re-run concat-relay --xfade 0 --master on this dir")


if __name__ == "__main__":
    main()
