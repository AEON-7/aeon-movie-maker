#!/usr/bin/env python3
"""
scrub_narration.py — clean unwanted narration from Prompt Relay sequences

LTX 2.3's joint A/V audio head occasionally generates speech in dialogue-less
sequences (it draws words from the scene description). The output ranges from
"nice atmospheric narration" to "complete word-salad gibberish". This tool
identifies leakage via ASR and surgically mutes time-spans on the per-sequence
MP4s, leaving scripted dialogue intact.

Two modes:

  --mode title-phrases    Mute any time-span where ASR detects literal title
                          fragments ("the prince of two threads" + mishearings).
                          Used as legacy cleanup for renders done before the
                          wrapper-level title-omission patch (commit dca22ed+).
                          Newer renders should not need this — only run it if
                          you're working with old per-sequence MP4s.

  --mode list             Print the ASR transcript of each sequence and exit.
                          Use this to identify which sequences need muting,
                          then run with --mode mute --target SEQ_INDICES.

  --mode mute             Full-mute the audio of specified sequences. Use for
                          dialogue-less sequences that picked up unwanted
                          narrator gibberish. Pass --target as comma-separated
                          list of sequence indices: --target 23,24,26

Examples:
  # 1. List all transcripts to identify problem sequences
  python tools/scrub_narration.py --mode list \\
      --input-dir output/movie_fast/MY_FILM

  # 2. Mute the bad ones surgically
  python tools/scrub_narration.py --mode mute --target 23,24,26 \\
      --input-dir output/movie_fast/MY_FILM

  # 3. Legacy: scrub title-phrase leakage from old renders
  python tools/scrub_narration.py --mode title-phrases \\
      --input-dir output/movie_fast/MY_FILM \\
      --asr-url http://localhost:8001/v1/audio/transcriptions

After scrubbing, re-run `concat-relay` to pick up the cleaned per-sequence
audio in the final film.

Requirements:
  - ffmpeg + ffprobe on PATH
  - Python `requests` package
  - For ASR-based modes (list, title-phrases): a Whisper-compatible ASR
    server reachable via OpenAI-style /v1/audio/transcriptions endpoint.
    We use qwen3-asr-server (https://github.com/AEON-7/qwen3-asr-server).
"""

import argparse
import json
import shutil
import subprocess
import tempfile
from pathlib import Path

# Strict title-fragment matchers used in --mode title-phrases.
# Add your own film's title fragments here if working with a custom render.
TITLE_PHRASES = [
    "the prince of two threads",
    "prince of two threads",
    "the prints of two threads",      # ASR mishearing
    "prince of tweedside",            # ASR mishearing
]


def asr(wav_path, asr_url):
    """OpenAI-compatible /v1/audio/transcriptions POST. Returns plain text."""
    import requests
    with open(wav_path, "rb") as f:
        files = {"file": (Path(wav_path).name, f, "audio/wav")}
        data = {"model": "qwen3-asr", "response_format": "text"}
        try:
            r = requests.post(asr_url, files=files, data=data, timeout=60)
            r.raise_for_status()
            return r.json().get("text", "").strip()
        except Exception as e:
            return f"ASR_ERROR: {e}"


def extract_window(in_mp4, t_start, t_end, out_wav):
    duration = t_end - t_start
    subprocess.run([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-ss", f"{t_start:.3f}", "-t", f"{duration:.3f}",
        "-i", str(in_mp4),
        "-vn", "-ac", "1", "-ar", "16000", "-sample_fmt", "s16",
        str(out_wav),
    ], check=True)


def probe_duration(mp4):
    out = subprocess.run([
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=nw=1:nk=1", str(mp4),
    ], capture_output=True, text=True, check=True)
    return float(out.stdout.strip())


def has_title_phrase(text):
    text_low = text.lower()
    return any(p in text_low for p in TITLE_PHRASES)


def find_title_spans(in_mp4, total_duration, asr_url, work_dir,
                     window_s=1.5, stride_s=0.5):
    """Sub-window ASR. Return list of (start, end) tuples where title
    phrases are detected."""
    spans = []
    t = 0.0
    n = 0
    while t + window_s <= total_duration + 0.01:
        wav = work_dir / f"win_{n:03d}.wav"
        win_end = min(t + window_s, total_duration)
        extract_window(in_mp4, t, win_end, wav)
        text = asr(wav, asr_url)
        if has_title_phrase(text):
            spans.append((t, win_end))
        t += stride_s
        n += 1
    return spans


def coalesce(spans):
    if not spans: return []
    flat = sorted(spans)
    merged = [flat[0]]
    for s, e in flat[1:]:
        if s <= merged[-1][1] + 0.05:
            merged[-1] = (merged[-1][0], max(merged[-1][1], e))
        else:
            merged.append((s, e))
    return merged


def apply_mutes(in_mp4, out_mp4, mute_ranges, full_mute=False):
    if full_mute:
        af = "volume=0"
    elif not mute_ranges:
        shutil.copy2(in_mp4, out_mp4)
        return
    else:
        terms = "+".join(f"between(t,{s:.3f},{e:.3f})" for s, e in mute_ranges)
        af = f"volume=enable='{terms}':volume=0"
    subprocess.run([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-i", str(in_mp4),
        "-c:v", "copy",
        "-af", af,
        "-c:a", "aac", "-b:a", "192k",
        "-movflags", "+faststart",
        str(out_mp4),
    ], check=True)


def cmd_list(args):
    seq_files = sorted(Path(args.input_dir).glob("sequence_*.mp4"))
    print(f"Found {len(seq_files)} sequences in {args.input_dir}")
    print("="*80)
    with tempfile.TemporaryDirectory() as td:
        wav = Path(td) / "probe.wav"
        for i, mp4 in enumerate(seq_files):
            dur = probe_duration(mp4)
            extract_window(mp4, 0, dur, wav)
            text = asr(wav, args.asr_url)
            print(f"SEQ {i:02d} ({dur:5.1f}s) {mp4.name}")
            print(f"        ASR: {text!r}")
            print()


def cmd_mute(args):
    targets = set(int(x) for x in args.target.split(",") if x.strip())
    seq_files = sorted(Path(args.input_dir).glob("sequence_*.mp4"))
    print(f"Full-muting {len(targets)} sequence(s) in-place")
    for i, mp4 in enumerate(seq_files):
        if i not in targets:
            continue
        tmp = mp4.parent / (mp4.stem + "_muted_tmp.mp4")
        print(f"  SEQ {i:02d}: {mp4.name}")
        apply_mutes(mp4, tmp, [], full_mute=True)
        tmp.replace(mp4)
    print("Done. Re-run concat-relay to incorporate the cleaned audio.")


def cmd_title_phrases(args):
    input_dir = Path(args.input_dir)
    out_dir = Path(args.out_dir) if args.out_dir else (input_dir / "cleaned")
    out_dir.mkdir(parents=True, exist_ok=True)
    seq_files = sorted(p for p in input_dir.glob("sequence_*.mp4")
                       if p.parent.name != "cleaned")

    print(f"Found {len(seq_files)} sequences. Output → {out_dir}")
    summary = []
    with tempfile.TemporaryDirectory() as td:
        work = Path(td)
        for i, mp4 in enumerate(seq_files):
            dur = probe_duration(mp4)
            print(f"\n=== SEQ {i:02d}: {mp4.name} ({dur:.2f}s) ===")
            full_wav = work / "full.wav"
            extract_window(mp4, 0, dur, full_wav)
            full_text = asr(full_wav, args.asr_url)
            print(f"  full ASR: {full_text!r}")
            if not has_title_phrase(full_text):
                print(f"  → no title phrase, passthrough")
                shutil.copy2(mp4, out_dir / mp4.name)
                summary.append((mp4.name, "passthrough", []))
                continue
            print(f"  → title phrase detected, sub-windowing")
            raw = find_title_spans(mp4, dur, args.asr_url, work)
            for s, e in raw:
                print(f"    [{s:.2f}-{e:.2f}s] mute")
            mute_ranges = coalesce(raw)
            apply_mutes(mp4, out_dir / mp4.name, mute_ranges)
            summary.append((mp4.name, "muted", mute_ranges))

    print("\n=== SUMMARY ===")
    for name, status, ranges in summary:
        marker = "✂" if status == "muted" else "✓"
        rs = ", ".join(f"{s:.2f}-{e:.2f}s" for s, e in ranges) if ranges else ""
        print(f"  {marker} {name:55s} {status:11s} {rs}")
    print(f"\nCleaned outputs in: {out_dir}")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                  formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--mode", required=True, choices=["list", "mute", "title-phrases"])
    ap.add_argument("--input-dir", required=True,
                    help="Directory containing sequence_*.mp4 files")
    ap.add_argument("--target",
                    help="(--mode mute) Comma-separated sequence indices to mute, e.g. '23,24,26'")
    ap.add_argument("--asr-url", default="http://localhost:8001/v1/audio/transcriptions",
                    help="OpenAI-compatible ASR endpoint (default: qwen3-asr on localhost:8001)")
    ap.add_argument("--out-dir",
                    help="(--mode title-phrases) Output directory. Default: <input-dir>/cleaned")
    args = ap.parse_args()

    if args.mode == "list":
        cmd_list(args)
    elif args.mode == "mute":
        if not args.target:
            ap.error("--mode mute requires --target with comma-separated sequence indices")
        cmd_mute(args)
    elif args.mode == "title-phrases":
        cmd_title_phrases(args)


if __name__ == "__main__":
    main()
