#!/usr/bin/env python3
"""Harvest video transcripts from youtubetranscriptdownload.com, resumably.

    export YTD_API_KEY=ytd_sk_...
    python scripts/youtube_fetch_transcripts.py              # English queue
    python scripts/youtube_fetch_transcripts.py --all        # every video
    python scripts/youtube_fetch_transcripts.py --dry-run    # what would be fetched

Built to be run repeatedly with different keys as credits are topped up. Three
properties make that safe:

  RESUMABLE   A video with a transcript file on disk is never requested again, so
              re-running costs nothing for work already done. Each request is one
              credit and repeats are charged, so this matters.

  HONEST ABOUT FAILURES
              402 means out of credits — the video may well have captions and is
              left pending for the next run. 403/404 mean no captions exist, are
              charged nothing, and are recorded as permanent so later runs skip
              them. Conflating the two either wastes credits or silently drops
              videos that could have been transcribed.

  RATE-LIMITED
              5 requests per 10 seconds, enforced with a 2.2s gap and honouring
              Retry-After on 429.

Transcripts land in knowledge_fabric/youtube/transcripts/ in the pipeline's cue
format, with the domain-correction pass applied. Run build_index afterwards.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

CACHE = Path("knowledge_fabric/youtube")
MANIFEST = CACHE / "manifest.json"
QUEUE = CACHE / "transcribe_queue.json"
TRANSCRIPTS = CACHE / "transcripts"
NO_CAPTIONS = CACHE / "no_captions.json"     # permanent negatives, so we stop asking

BASE = "https://youtubetranscriptdownload.com/api/v1"
GAP = 2.2                                    # 5 requests / 10 s

NON_ENGLISH = {
    "Japanese | 日本語", "French (France) | Français",
    "Spanish (Spain) | Español", "Portuguese (Portugal) | Português",
}

# Same corrections as youtube_transcribe.py. Auto-captions mis-hear domain terms
# consistently, and a wrong product name in a citation is worse than a clumsy one.
HARD_FIXES = {
    r"\bartell?ware\b": "ArtelWare", r"\bartel ware\b": "ArtelWare",
    r"\bpipet\b": "pipette", r"\bpipets\b": "pipettes",
    r"\bstat sensor\b": "StatSensor", r"\bstat strip\b": "StatStrip",
    r"\bstat profile\b": "Stat Profile", r"\bnova max\b": "Nova Max",
    r"\be gfr\b": "eGFR", r"\begfr\b": "eGFR",
    r"\bmbs\b": "MVS", r"\bmvs\b": "MVS", r"\bpcs\b": "PCS",
    r"\bnano cellect\b": "NanoCellect", r"\bbio profile\b": "BioProfile",
}


def correct(text: str) -> str:
    import re
    for pattern, replacement in HARD_FIXES.items():
        text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)
    return text


def log(msg: str) -> None:
    print(f"  {msg}", flush=True)


def api(path: str, key: str, method: str = "GET", body: dict | None = None):
    """Returns (status, payload). Never raises for HTTP errors — the caller needs
    to tell 402 from 404 to decide whether to retry later."""
    data = json.dumps(body).encode() if body else None
    req = urllib.request.Request(
        BASE + path, data=data, method=method,
        headers={"Authorization": f"Bearer {key}",
                 **({"Content-Type": "application/json"} if body else {})})
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        try:
            payload = json.loads(exc.read().decode("utf-8"))
        except Exception:
            payload = {}
        if exc.code == 429:
            wait = int(exc.headers.get("Retry-After", 8))
            log(f"rate limited, waiting {wait}s")
            time.sleep(wait + 1)
            return api(path, key, method, body)
        return exc.code, payload
    except Exception as exc:
        return 0, {"error": str(exc)[:80]}


def to_cues(segments: list[dict]) -> list[dict]:
    cues = []
    for seg in segments:
        text = (seg.get("text") or "").strip()
        if not text or text.startswith("["):        # [Music], [Applause]
            continue
        start = float(seg.get("start", 0)) / 1000.0  # API returns milliseconds
        dur = float(seg.get("duration", 0)) / 1000.0
        cues.append({"start": round(start, 2), "end": round(start + dur, 2),
                     "text": correct(" ".join(text.split()))})
    return cues


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--all", action="store_true", help="include non-English videos")
    ap.add_argument("--limit", type=int, default=0, help="max videos this run")
    ap.add_argument("--dry-run", action="store_true", help="list targets, fetch nothing")
    ap.add_argument("--retry-negatives", action="store_true",
                    help="re-test videos previously found to have no captions")
    args = ap.parse_args()

    key = os.environ.get("YTD_API_KEY", "").strip()
    if not key and not args.dry_run:
        print("Set YTD_API_KEY first:  export YTD_API_KEY=ytd_sk_...", file=sys.stderr)
        return 1
    if not MANIFEST.exists():
        print("No manifest — run scripts/youtube_refresh.py first", file=sys.stderr)
        return 1

    TRANSCRIPTS.mkdir(parents=True, exist_ok=True)
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    negatives = set(json.loads(NO_CAPTIONS.read_text()).get("video_ids", [])) \
        if NO_CAPTIONS.exists() and not args.retry_negatives else set()

    videos = manifest.get("videos", {})
    targets = []
    for vid, v in videos.items():
        if v.get("withdrawn"):
            continue
        if (TRANSCRIPTS / f"{vid}.json").exists():
            continue                                   # already have it — never re-charge
        if vid in negatives:
            continue                                   # known captionless
        if not args.all and (set(v.get("playlists", [])) & NON_ENGLISH):
            continue
        targets.append((vid, v.get("title", ""), v.get("duration_sec", 0)))

    targets.sort(key=lambda t: t[2])                   # cheapest/shortest first
    if args.limit:
        targets = targets[:args.limit]

    have = len(list(TRANSCRIPTS.glob("*.json")))
    print(f"  have {have} transcripts · {len(negatives)} known captionless · "
          f"{len(targets)} to try")

    if args.dry_run:
        for vid, title, dur in targets:
            print(f"    {dur:5}s  {vid}  {title[:58]}")
        return 0

    status, me = api("/me", key)
    if status != 200:
        print(f"  ! key rejected ({status}): {me.get('error', '')}", file=sys.stderr)
        return 1
    credits = me.get("credits", 0)
    print(f"  key ok — {credits} credits available\n")
    if credits <= 0:
        print("  no credits on this key")
        return 0

    got = nocaps = 0
    exhausted = False
    for vid, title, _dur in targets:
        if got >= credits:
            exhausted = True
            break
        status, payload = api(f"/transcript?videoId={vid}", key)

        if status == 200:
            cues = to_cues(payload.get("transcript") or [])
            if not cues:
                nocaps += 1
                negatives.add(vid)
            else:
                (TRANSCRIPTS / f"{vid}.json").write_text(json.dumps({
                    "video_id": vid,
                    "model": "youtube/captions (transcript API)",
                    "transcribed_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                    "cue_count": len(cues), "cues": cues,
                }, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
                manifest["videos"].setdefault(vid, {})["transcript_status"] = "done"
                got += 1
                log(f"OK  {len(cues):5} cues  credits={payload.get('credits_remaining','?')}  {title[:46]}")
        elif status == 402:
            exhausted = True
            break
        elif status in (403, 404):
            # Charged nothing. Recorded so later runs, on any key, skip it.
            nocaps += 1
            negatives.add(vid)
        else:
            log(f"!   HTTP {status} {vid}: {payload.get('error','')[:50]}")

        time.sleep(GAP)

    MANIFEST.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
                        encoding="utf-8")
    NO_CAPTIONS.write_text(json.dumps(
        {"note": "Videos the transcript API reports as having no captions. "
                 "Charged nothing; skipped on later runs. Re-test with "
                 "--retry-negatives if captions are added later.",
         "video_ids": sorted(negatives)}, indent=1) + "\n", encoding="utf-8")

    total = len(list(TRANSCRIPTS.glob("*.json")))
    print()
    print(f"  fetched {got} · no captions {nocaps} · transcripts on disk {total}")
    if exhausted:
        remaining = len([t for t in targets if not (TRANSCRIPTS / f'{t[0]}.json').exists()
                         and t[0] not in negatives])
        print(f"  credits exhausted — {remaining} still pending, re-run with a new key")
    print("  then: python -m pipeline.build_index")
    return 0


if __name__ == "__main__":
    sys.exit(main())
