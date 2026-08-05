#!/usr/bin/env python3
"""Local transcription backfill. Free, offline, one-time.

    pip install faster-whisper yt-dlp
    python scripts/youtube_transcribe.py --limit 5        # try a few first
    python scripts/youtube_transcribe.py                  # full queue, overnight

Runs on your own machine, not in CI, for three reasons: the free runner caps a job
at six hours, YouTube throttles datacentre IPs so audio fetch is unreliable there,
and the backfill is a one-time job whose output is committed. After this runs once,
CI only ever handles the one or two new videos a month.

Audio is fetched, transcribed, and deleted. Nothing but JSON is committed.

TWO ACCURACY PASSES, BOTH FREE — this is what replaces a paid LLM cleanup step:

  1. Domain priming. Whisper's initial_prompt biases decoding toward supplied
     vocabulary. Feeding it the product and analyte names measurably reduces the
     'pipet' / 'Artellware' class of error before it happens.

  2. Corpus vocabulary correction. pipeline/textnorm.py already builds the
     corpus's own vocabulary and already refuses merges it has never seen. That
     is the right lexicon for this text — it was built from Nova's own documents
     — so we reuse it rather than inventing a second one.

Whisper emits punctuation and casing natively, which is why the transcript can be
segmented on sentence boundaries without any generative model in the loop.
"""
from __future__ import annotations

import argparse
import json
import re
import os
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

CACHE = Path("knowledge_fabric/youtube")
MANIFEST = CACHE / "manifest.json"
QUEUE = CACHE / "transcribe_queue.json"
TRANSCRIPTS = CACHE / "transcripts"

# Seeds Whisper's decoder. Keep it under ~200 tokens — it is a bias, not a lexicon.
DOMAIN_PROMPT = (
    "Nova Biomedical point-of-care testing. Products: StatStrip Glucose, "
    "StatStrip Lactate, StatSensor Creatinine, Stat Profile Prime Plus, "
    "Nova Allegro, Nova Max, BioProfile FLEX2, Artel MVS, ArtelWare, NanoCellect. "
    "Terms: eGFR, hematocrit, whole blood, capillary fingerstick, in vitro "
    "diagnostic, analyte, pipette, calibration, verification, meter, cartridge, "
    "reagent, quality control, 510(k), Instructions For Use."
)


def log(msg: str) -> None:
    print(f"  {msg}", flush=True)


# ------------------------------------------- captions via transcript API
def fetch_via_api(video_id: str, vocab: set[str], key: str) -> list[dict] | None:
    """youtubetranscriptdownload.com — a hosted proxy for YouTube's caption feed.

    Worth having as the FIRST option because it works from IPs YouTube blocks
    outright (CI runners, cloud shells, anywhere the direct caption endpoints
    return IpBlocked). It costs one credit per successful video; videos without
    captions fail for free and fall through to the next method.

    Set YTD_API_KEY in the environment. Results are cached on disk, so a video is
    never fetched - or charged - twice.
    """
    import urllib.error
    import urllib.request

    url = f"https://youtubetranscriptdownload.com/api/v1/transcript?videoId={video_id}"
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {key}"})
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        if exc.code == 402:
            log("! transcript API credits exhausted — falling back")
        elif exc.code == 429:
            time.sleep(10)
            return fetch_via_api(video_id, vocab, key)
        return None                      # 403/404 = no captions, charged nothing
    except Exception:
        return None

    cues = []
    for seg in data.get("transcript") or []:
        text = (seg.get("text") or "").strip()
        if not text or text.startswith("["):
            continue
        start = float(seg.get("start", 0)) / 1000.0        # API returns ms
        dur = float(seg.get("duration", 0)) / 1000.0
        cues.append({"start": round(start, 2), "end": round(start + dur, 2),
                     "text": correct(" ".join(text.split()), vocab)})
    return cues or None


# ---------------------------------------------------- captions (fast path)
def fetch_captions(video_id: str, vocab: set[str]) -> list[dict] | None:
    """Publisher or auto-generated captions, straight from YouTube.

    Tried BEFORE audio because it is instant, needs no model download, and costs
    nothing - roughly a fifth of this channel carries auto-captions. Quality is
    below Whisper's (no punctuation, more domain-term errors), so the same
    correction pass runs over it, but a real timestamp from captions beats a
    perfect transcript nobody got round to generating.

    Returns None when the video has no captions, so the caller falls through to
    audio + Whisper.
    """
    try:
        from youtube_transcript_api import YouTubeTranscriptApi
    except ImportError:
        return None
    try:
        api = YouTubeTranscriptApi()
        fetched = api.fetch(video_id, languages=["en", "en-US", "en-GB"])
        raw = fetched.to_raw_data() if hasattr(fetched, "to_raw_data") else list(fetched)
    except Exception:
        return None

    cues = []
    for seg in raw:
        text = (seg.get("text") if isinstance(seg, dict) else getattr(seg, "text", "")) or ""
        text = correct(" ".join(text.split()), vocab)
        if not text or text.startswith("["):          # [Music], [Applause]
            continue
        start = float(seg.get("start") if isinstance(seg, dict) else getattr(seg, "start", 0.0))
        dur = float(seg.get("duration") if isinstance(seg, dict) else getattr(seg, "duration", 0.0))
        cues.append({"start": round(start, 2), "end": round(start + dur, 2), "text": text})
    return cues or None


# ------------------------------------------------------------------- audio
def fetch_audio(video_id: str, dest: Path) -> Path | None:
    """Audio only, smallest usable. Deleted immediately after transcription."""
    out = dest / f"{video_id}.m4a"
    cmd = [
        "yt-dlp", "--no-check-certificates", "--quiet", "--no-warnings",
        "-f", "bestaudio[ext=m4a]/bestaudio",
        "--extract-audio", "--audio-format", "m4a", "--audio-quality", "5",
        "-o", str(dest / f"{video_id}.%(ext)s"),
        f"https://www.youtube.com/watch?v={video_id}",
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=900)
    except (subprocess.TimeoutExpired, FileNotFoundError) as exc:
        log(f"! audio fetch failed: {exc}")
        return None
    if proc.returncode != 0 and not out.exists():
        log(f"! audio fetch failed: {proc.stderr.strip()[:200]}")
        return None
    if out.exists():
        return out
    for cand in dest.glob(f"{video_id}.*"):
        return cand
    return None


# ------------------------------------------------- corpus vocabulary repair
def load_corpus_vocabulary() -> set[str]:
    """Reuse the fabric's own vocabulary. If the index is not built yet we simply
    skip correction rather than guessing — a wrong 'correction' is worse than
    none, and the raw Whisper output is already punctuated and cased."""
    index = Path("site/data/index.json")
    if not index.exists():
        return set()
    try:
        data = json.loads(index.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return set()
    vocab: set[str] = set()
    for chunk in data.get("chunks", []):
        for tok in re.findall(r"[A-Za-z][A-Za-z0-9-]+", chunk.get("text", "")):
            if len(tok) > 3:
                vocab.add(tok.lower())
    return vocab


# Explicit, auditable overrides for errors observed in this channel's audio.
# Deliberately a short, reviewable list rather than fuzzy matching: every
# substitution here is one a human approved, and it shows up in a git diff.
HARD_FIXES = {
    r"\bartell?ware\b": "ArtelWare",
    r"\bartel ware\b": "ArtelWare",
    r"\bpipet\b": "pipette",
    r"\bpipets\b": "pipettes",
    r"\bstat sensor\b": "StatSensor",
    r"\bstat strip\b": "StatStrip",
    r"\bstat profile\b": "Stat Profile",
    r"\bnova max\b": "Nova Max",
    r"\be gfr\b": "eGFR",
    r"\begfr\b": "eGFR",
    r"\bhematocrit\b": "hematocrit",
    r"\bmvs\b": "MVS",
    r"\bpcs\b": "PCS",
}


def correct(text: str, vocab: set[str]) -> str:
    for pattern, replacement in HARD_FIXES.items():
        text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)

    if not vocab:
        return text

    # Repair split words only when the joined form is attested in the corpus —
    # the same conservative rule textnorm.py already applies to PDF text.
    def join_if_attested(m: re.Match) -> str:
        a, b = m.group(1), m.group(2)
        if (a + b).lower() in vocab and a.lower() not in vocab:
            return a + b
        return m.group(0)

    return re.sub(r"\b([A-Za-z]{2,})\s+([a-z]{2,})\b", join_if_attested, text)


# -------------------------------------------------------------- transcribe
def transcribe(audio: Path, model, vocab: set[str]) -> list[dict]:
    segments, _info = model.transcribe(
        str(audio),
        language="en",
        beam_size=5,
        vad_filter=True,                 # skip silence — faster and avoids hallucinated text
        vad_parameters={"min_silence_duration_ms": 500},
        initial_prompt=DOMAIN_PROMPT,
        condition_on_previous_text=False,  # stops one bad segment cascading
    )
    cues = []
    for seg in segments:
        text = correct((seg.text or "").strip(), vocab)
        if text:
            cues.append({"start": round(seg.start, 2),
                         "end": round(seg.end, 2),
                         "text": text})
    return cues


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0, help="max videos this run (0 = all)")
    ap.add_argument("--model", default="small.en",
                    help="tiny.en | base.en | small.en | medium.en")
    ap.add_argument("--device", default="cpu", help="cpu | cuda")
    ap.add_argument("--compute-type", default="int8",
                    help="int8 on CPU, float16 on GPU")
    ap.add_argument("--video", default="", help="transcribe a single video id")
    ap.add_argument("--captions-only", action="store_true",
                    help="use YouTube captions only; never download audio or load a model")
    ap.add_argument("--no-captions", action="store_true",
                    help="skip the caption fast path and always run speech recognition")
    args = ap.parse_args()

    if not MANIFEST.exists():
        print("No manifest. Run scripts/youtube_refresh.py first.")
        return 1

    try:
        from faster_whisper import WhisperModel
    except ImportError:
        if not args.captions_only:
            print("pip install faster-whisper yt-dlp youtube-transcript-api")
            print("(or run with --captions-only, which needs only youtube-transcript-api)")
            return 1
        WhisperModel = None

    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    TRANSCRIPTS.mkdir(parents=True, exist_ok=True)

    if args.video:
        pending = [{"video_id": args.video,
                    "title": manifest["videos"].get(args.video, {}).get("title", "")}]
    else:
        if not QUEUE.exists():
            print("No queue. Run scripts/youtube_refresh.py first.")
            return 1
        pending = json.loads(QUEUE.read_text(encoding="utf-8"))["queue"]
        pending = [q for q in pending if not (TRANSCRIPTS / f"{q['video_id']}.json").exists()]
    if args.limit:
        pending = pending[:args.limit]

    if not pending:
        print("Nothing to transcribe — all queued videos already have transcripts.")
        return 0

    total_sec = sum(q.get("duration_sec", 0) for q in pending)
    vocab = load_corpus_vocabulary()
    model = None
    if not args.captions_only:
        log(f"loading {args.model} on {args.device} ({args.compute_type})")
        model = WhisperModel(args.model, device=args.device, compute_type=args.compute_type)
    log(f"corpus vocabulary: {len(vocab)} terms"
        if vocab else "corpus vocabulary unavailable — hard fixes only")
    log(f"{len(pending)} videos, {total_sec / 3600:.1f} hours of audio")
    print()

    done = failed = 0
    workdir = Path(tempfile.mkdtemp(prefix="kf_audio_"))
    try:
        for i, item in enumerate(pending, start=1):
            vid = item["video_id"]
            title = (item.get("title") or vid)[:58]
            print(f"[{i}/{len(pending)}] {title}", flush=True)

            # Captions first: instant, free, and enough to make the citation
            # seek to the right second.
            api_key = os.environ.get("YTD_API_KEY", "").strip()
            cues = None
            if not args.no_captions:
                if api_key:
                    cues = fetch_via_api(vid, vocab, api_key)
                    if cues:
                        time.sleep(2.2)          # 5 requests / 10 s
                if not cues:
                    cues = fetch_captions(vid, vocab)
            if cues:
                (TRANSCRIPTS / f"{vid}.json").write_text(json.dumps({
                    "video_id": vid, "model": "youtube/captions" if not os.environ.get("YTD_API_KEY") else "youtube/captions (transcript API)",
                    "transcribed_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                    "cue_count": len(cues), "cues": cues,
                }, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
                manifest["videos"].setdefault(vid, {})["transcript_status"] = "done"
                log(f"{len(cues)} cues from YouTube captions")
                done += 1
                continue
            if args.captions_only:
                log("no captions; skipping (--captions-only)")
                manifest["videos"].setdefault(vid, {})["transcript_status"] = "no_captions"
                continue

            audio = fetch_audio(vid, workdir)
            if audio is None:
                manifest["videos"].setdefault(vid, {})["transcript_status"] = "fetch_failed"
                failed += 1
                continue

            started = datetime.now(timezone.utc)
            try:
                cues = transcribe(audio, model, vocab)
            except Exception as exc:
                log(f"! transcription failed: {exc}")
                manifest["videos"].setdefault(vid, {})["transcript_status"] = "asr_failed"
                failed += 1
                continue
            finally:
                audio.unlink(missing_ok=True)

            if not cues:
                log("! no speech detected")
                manifest["videos"].setdefault(vid, {})["transcript_status"] = "no_speech"
                continue

            (TRANSCRIPTS / f"{vid}.json").write_text(json.dumps({
                "video_id": vid,
                "model": f"faster-whisper/{args.model}",
                "transcribed_at": started.isoformat(timespec="seconds"),
                "cue_count": len(cues),
                "cues": cues,
            }, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")

            manifest["videos"].setdefault(vid, {})["transcript_status"] = "done"
            elapsed = (datetime.now(timezone.utc) - started).total_seconds()
            log(f"{len(cues)} cues in {elapsed:.0f}s")
            done += 1
    finally:
        shutil.rmtree(workdir, ignore_errors=True)
        MANIFEST.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
                            encoding="utf-8")

    print()
    print(f"  transcribed {done}, failed {failed}")
    print("  commit knowledge_fabric/youtube/ to publish")
    return 0


if __name__ == "__main__":
    sys.exit(main())
