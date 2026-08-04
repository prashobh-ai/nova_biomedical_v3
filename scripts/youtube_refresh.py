#!/usr/bin/env python3
"""Refresh the committed YouTube cache. Fetches metadata only — never audio.

    python scripts/youtube_refresh.py --channel @NovaBiomedical

Why a full reconcile every run instead of "fetch new videos only":

  A channel does not only gain videos. Titles get corrected, descriptions get
  rewritten, videos get moved between playlists, and videos get unlisted or
  deleted. Incremental logic keyed on "newest ID I have seen" misses every one
  of those, and they are exactly the changes that matter for a fabric that
  claims to know when its knowledge changed.

  A full enumeration of this channel costs ~30 quota units against a 10,000/day
  free allowance, so the reconcile is cheaper than the bookkeeping needed to
  avoid it. Fetch everything, diff against the manifest, act on the delta.

Three outcomes per video:

    new       -> add to manifest, queue for transcription
    changed   -> update fields; re-queue for transcription only if the audio
                 itself could have changed (duration moved)
    gone      -> TOMBSTONE. Set withdrawn=true and keep the record.

The tombstone is not defensive coding. A video that disappears is the same event
as a withdrawn document revision, and the product's entire traceability argument
is that we can tell the difference between "current" and "withdrawn". Deleting
the row would make the fabric quietly forget that it ever knew something.

Two backends, in priority order:
    1. YouTube Data API v3 if YOUTUBE_API_KEY is set   (stable, 10k units/day free)
    2. yt-dlp otherwise                                (no key needed, scrapes)
Both are free. The API is preferred in CI because datacentre IPs get throttled.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

CACHE = Path("knowledge_fabric/youtube")
MANIFEST = CACHE / "manifest.json"
QUEUE = CACHE / "transcribe_queue.json"

# Videos on these playlists are transcribed first — they are the ones that join
# to the document corpus, so they carry the demo.
PRIORITY_PLAYLISTS = {
    "StatSensor®", "StatStrip®", "Stat Profile®", "Allegro®",
    "Nova Max Pro™", "Nova Pro®", "Nova Pro™", "BioProfile®",
    "Hospital", "Outpatient Care",
}
ENGLISH_PLAYLIST = "English (US)"
NON_ENGLISH_PLAYLISTS = {
    "Japanese | 日本語", "French (France) | Français",
    "Spanish (Spain) | Español", "Portuguese (Portugal) | Português",
}


# ---------------------------------------------------------------- utilities
def content_hash(video: dict) -> str:
    """Hash only the fields whose change should trigger downstream work."""
    payload = json.dumps({
        "title": video.get("title", ""),
        "description": video.get("description", ""),
        "duration_sec": video.get("duration_sec", 0),
        "playlists": sorted(video.get("playlists", [])),
    }, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def log(msg: str) -> None:
    print(f"  {msg}", flush=True)


# ------------------------------------------------------------------ backends
def _ytdlp_json(url: str, flat: bool = True) -> list[dict]:
    cmd = ["yt-dlp", "--no-check-certificates", "--ignore-errors",
           "--dump-json", "--no-warnings"]
    if flat:
        cmd.append("--flat-playlist")
    else:
        # mweb is not bot-checked; it exposes no playable formats, which is fine
        # because this path only ever wants metadata.
        cmd += ["--skip-download", "--ignore-no-formats-error",
                "--extractor-args", "youtube:player_client=mweb"]
    cmd.append(url)
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    except (subprocess.TimeoutExpired, FileNotFoundError) as exc:
        raise RuntimeError(f"yt-dlp unavailable or timed out: {exc}") from exc
    out = []
    for line in proc.stdout.splitlines():
        line = line.strip()
        if line.startswith("{"):
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    if not out and proc.returncode != 0:
        raise RuntimeError(f"yt-dlp failed: {proc.stderr[:300]}")
    return out


def fetch_via_ytdlp(channel: str) -> dict[str, dict]:
    log("backend: yt-dlp (no API key set)")
    videos: dict[str, dict] = {}

    for row in _ytdlp_json(f"https://www.youtube.com/{channel}/videos"):
        vid = row.get("id")
        if not vid:
            continue
        videos[vid] = {
            "video_id": vid,
            "title": (row.get("title") or "").strip(),
            "description": (row.get("description") or "").strip(),
            "duration_sec": int(row.get("duration") or 0),
            "published_at": "",
            "channel": row.get("uploader") or row.get("channel") or "Nova Biomedical",
            "playlists": [],
        }
    log(f"videos enumerated: {len(videos)}")

    for pl in _ytdlp_json(f"https://www.youtube.com/{channel}/playlists"):
        pid, ptitle = pl.get("id"), (pl.get("title") or "").strip()
        if not pid or not ptitle:
            continue
        try:
            items = _ytdlp_json(f"https://www.youtube.com/playlist?list={pid}")
        except RuntimeError as exc:
            log(f"! playlist '{ptitle}' unavailable: {exc}")
            continue
        for item in items:
            vid = item.get("id")
            if vid in videos and ptitle not in videos[vid]["playlists"]:
                videos[vid]["playlists"].append(ptitle)
    log(f"playlists mapped: {len({p for v in videos.values() for p in v['playlists']})}")

    # Flat enumeration omits upload_date and full descriptions. Backfill per video,
    # but only where the manifest does not already have them — this is the only
    # part that scales with catalogue size.
    return videos


BOT_CHECK = "confirm you"

# The channel RSS feed. Verified to work from a datacentre IP where per-video
# yt-dlp is bot-checked, and it carries a true <published> timestamp for the
# ~15 most recent uploads. That is exactly the window the daily job needs: new
# videos are new, so they are always in the feed when we first see them.
RSS_FEED = "https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"
DEFAULT_CHANNEL_ID = "UC9nZNv6VhSfItRggLrBDqCg"   # @NovaBiomedical


def fetch_rss_dates(channel_id: str) -> dict[str, str]:
    """Publication dates for recent uploads, straight from the channel feed.

    Parsed per <entry>. The feed also carries a channel-level <published>
    element before the entries, so scanning the whole document with two parallel
    regexes silently shifts every date by one position — a bug that produces
    plausible-looking wrong dates rather than an error.
    """
    import re
    import urllib.request

    url = RSS_FEED.format(channel_id=channel_id)
    try:
        with urllib.request.urlopen(url, timeout=45) as resp:
            xml = resp.read().decode("utf-8", errors="replace")
    except Exception as exc:
        log(f"! RSS feed unavailable: {exc}")
        return {}

    dates: dict[str, str] = {}
    for entry in re.findall(r"<entry>(.*?)</entry>", xml, re.S):
        vid = re.search(r"<yt:videoId>(.*?)</yt:videoId>", entry)
        pub = re.search(r"<published>(.*?)</published>", entry)
        if vid and pub:
            dates[vid.group(1)] = pub.group(1)[:10]
    return dates


def enrich_via_ytdlp(video_ids: list[str]) -> dict[str, dict]:
    """Per-video detail: upload date and full description. Called only for the delta.

    NOTE — verified behaviour, not a hypothetical: flat playlist enumeration works
    from a datacentre IP, but the default player client triggers YouTube's "Sign in
    to confirm you're not a bot" check. The mweb client is not bot-checked and
    still yields upload_date and description; it exposes no playable formats, so
    --ignore-no-formats-error is required and harmless (we never want the audio).

    Order of preference for dates overall: YOUTUBE_API_KEY > RSS feed > this.
    """
    out: dict[str, dict] = {}
    for vid in video_ids:
        try:
            rows = _ytdlp_json(f"https://www.youtube.com/watch?v={vid}", flat=False)
        except RuntimeError as exc:
            if BOT_CHECK in str(exc):
                log("! YouTube bot check hit — skipping per-video enrichment this run.")
                log("  Titles, durations, playlists and RSS dates are unaffected.")
                return out
            log(f"! detail fetch failed for {vid}: {exc}")
            continue
        if not rows:
            continue
        r = rows[0]
        raw = r.get("upload_date") or ""
        iso = f"{raw[:4]}-{raw[4:6]}-{raw[6:8]}" if len(raw) == 8 else ""
        out[vid] = {
            "description": (r.get("description") or "").strip(),
            "published_at": iso,
            "duration_sec": int(r.get("duration") or 0),
        }
    return out


def fetch_via_api(channel_id: str, api_key: str) -> dict[str, dict]:
    """YouTube Data API v3. Uses the uploads playlist (1 unit/page), never
    search.list (100 units/call and not exhaustive)."""
    import urllib.parse
    import urllib.request

    log("backend: YouTube Data API v3")
    base = "https://www.googleapis.com/youtube/v3/"

    def get(endpoint: str, **params) -> dict:
        params["key"] = api_key
        url = base + endpoint + "?" + urllib.parse.urlencode(params)
        with urllib.request.urlopen(url, timeout=60) as resp:
            return json.loads(resp.read().decode("utf-8"))

    ch = get("channels", part="contentDetails", id=channel_id)
    items = ch.get("items") or []
    if not items:
        raise RuntimeError(f"channel {channel_id} not found")
    uploads = items[0]["contentDetails"]["relatedPlaylists"]["uploads"]

    def playlist_items(pid: str) -> list[str]:
        ids, token = [], None
        while True:
            page = get("playlistItems", part="contentDetails", playlistId=pid,
                       maxResults=50, **({"pageToken": token} if token else {}))
            ids += [i["contentDetails"]["videoId"] for i in page.get("items", [])]
            token = page.get("nextPageToken")
            if not token:
                return ids

    video_ids = playlist_items(uploads)
    log(f"videos enumerated: {len(video_ids)}")

    videos: dict[str, dict] = {}
    for i in range(0, len(video_ids), 50):
        batch = video_ids[i:i + 50]
        page = get("videos", part="snippet,contentDetails", id=",".join(batch))
        for item in page.get("items", []):
            sn = item["snippet"]
            videos[item["id"]] = {
                "video_id": item["id"],
                "title": sn.get("title", "").strip(),
                "description": sn.get("description", "").strip(),
                "duration_sec": _iso8601_seconds(item["contentDetails"].get("duration", "")),
                "published_at": sn.get("publishedAt", "")[:10],
                "channel": sn.get("channelTitle", "Nova Biomedical"),
                "playlists": [],
            }

    token = None
    while True:
        page = get("playlists", part="snippet", channelId=channel_id, maxResults=50,
                   **({"pageToken": token} if token else {}))
        for pl in page.get("items", []):
            ptitle = pl["snippet"]["title"].strip()
            for vid in playlist_items(pl["id"]):
                if vid in videos and ptitle not in videos[vid]["playlists"]:
                    videos[vid]["playlists"].append(ptitle)
        token = page.get("nextPageToken")
        if not token:
            break
    return videos


def _iso8601_seconds(duration: str) -> int:
    import re
    m = re.fullmatch(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", duration or "")
    if not m:
        return 0
    h, mi, s = (int(g) if g else 0 for g in m.groups())
    return h * 3600 + mi * 60 + s


# ---------------------------------------------------------------- reconcile
def reconcile(fetched: dict[str, dict], previous: dict) -> tuple[dict, dict]:
    old_videos = previous.get("videos", {})
    new_videos: dict[str, dict] = {}
    delta = {"new": [], "changed": [], "withdrawn": [], "restored": [], "unchanged": 0}

    for vid, video in fetched.items():
        video["content_hash"] = content_hash(video)
        prior = old_videos.get(vid)

        if prior is None:
            video["first_seen"] = datetime.now(timezone.utc).date().isoformat()
            video["withdrawn"] = False
            video["transcript_status"] = "pending"
            new_videos[vid] = video
            delta["new"].append(vid)
            continue

        merged = {**prior, **video, "withdrawn": False}
        merged["first_seen"] = prior.get("first_seen", merged.get("first_seen", ""))

        if prior.get("withdrawn"):
            delta["restored"].append(vid)

        if prior.get("content_hash") != video["content_hash"]:
            delta["changed"].append(vid)
            # Only re-transcribe when the audio itself may differ. A retitle or a
            # playlist move changes the metadata record; it does not change what
            # was said, and re-running ASR would burn time for an identical result.
            if prior.get("duration_sec") != video.get("duration_sec"):
                merged["transcript_status"] = "pending"
        else:
            delta["unchanged"] += 1

        new_videos[vid] = merged

    for vid, prior in old_videos.items():
        if vid in fetched:
            continue
        if not prior.get("withdrawn"):
            delta["withdrawn"].append(vid)
        prior["withdrawn"] = True
        prior["withdrawn_detected"] = prior.get(
            "withdrawn_detected", datetime.now(timezone.utc).date().isoformat())
        new_videos[vid] = prior

    manifest = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "video_count": sum(1 for v in new_videos.values() if not v.get("withdrawn")),
        "withdrawn_count": sum(1 for v in new_videos.values() if v.get("withdrawn")),
        "videos": dict(sorted(new_videos.items())),
    }
    return manifest, delta


def build_queue(manifest: dict, english_only: bool = True) -> list[dict]:
    """Transcription queue, priority-ordered.

    Priority exists so an interrupted backfill still produces a demoable fabric:
    the product videos that join to the document corpus are transcribed first.
    """
    queue = []
    for vid, v in manifest["videos"].items():
        if v.get("withdrawn") or v.get("transcript_status") == "done":
            continue
        playlists = set(v.get("playlists", []))
        if english_only and (playlists & NON_ENGLISH_PLAYLISTS):
            continue
        queue.append({
            "video_id": vid,
            "title": v.get("title", ""),
            "duration_sec": v.get("duration_sec", 0),
            "priority": 0 if (playlists & PRIORITY_PLAYLISTS) else 1,
            "english_declared": ENGLISH_PLAYLIST in playlists,
        })
    queue.sort(key=lambda q: (q["priority"], q["duration_sec"]))
    return queue


# --------------------------------------------------------------------- main
def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--channel", default="@NovaBiomedical",
                    help="channel handle for the yt-dlp backend")
    ap.add_argument("--channel-id", default=os.environ.get("YOUTUBE_CHANNEL_ID", ""),
                    help="UC... id, required for the API backend")
    ap.add_argument("--all-languages", action="store_true",
                    help="queue non-English videos for transcription too")
    ap.add_argument("--enrich-limit", type=int, default=25,
                    help="max per-video detail fetches per run (yt-dlp backend)")
    args = ap.parse_args()

    CACHE.mkdir(parents=True, exist_ok=True)
    previous = json.loads(MANIFEST.read_text(encoding="utf-8")) if MANIFEST.exists() else {}

    api_key = os.environ.get("YOUTUBE_API_KEY", "").strip()
    channel_id = args.channel_id or DEFAULT_CHANNEL_ID
    try:
        if api_key and args.channel_id:
            fetched = fetch_via_api(args.channel_id, api_key)
            for video in fetched.values():
                if video.get("published_at"):
                    video["date_method"] = "channel_publication_date"
                    video["date_confidence"] = 0.90
        else:
            fetched = fetch_via_ytdlp(args.channel)

            # --- Date resolution, highest authority first -------------------
            # 1. RSS feed: true publication timestamps for recent uploads, and
            #    it works from CI where per-video fetch is bot-checked. Any
            #    genuinely new video is by definition recent, so this covers
            #    exactly what the daily job needs to do.
            rss = fetch_rss_dates(channel_id)
            if rss:
                log(f"RSS feed: {len(rss)} publication dates")
            for vid, video in fetched.items():
                if vid in rss:
                    video["published_at"] = rss[vid]
                    video["date_method"] = "channel_publication_date"
                    video["date_confidence"] = 0.90

            # 2. Carry forward anything already dated. Backfilled history is
            #    never re-fetched — a publication date does not change.
            for vid, video in fetched.items():
                prior = previous.get("videos", {}).get(vid, {})
                if not video.get("published_at") and prior.get("published_at"):
                    video["published_at"] = prior["published_at"]
                    video["date_method"] = prior.get("date_method", "channel_publication_date")
                    video["date_confidence"] = prior.get("date_confidence", 0.90)
                if not video.get("description") and prior.get("description"):
                    video["description"] = prior["description"]

            # 3. Per-video mweb fetch for whatever is still undated — older
            #    videos that have dropped out of the RSS window.
            undated = [v for v, d in fetched.items()
                       if not d.get("published_at")][:args.enrich_limit]
            if undated:
                log(f"fetching dates for {len(undated)} undated videos")
                for vid, extra in enrich_via_ytdlp(undated).items():
                    for k, v in extra.items():
                        if v:
                            fetched[vid][k] = v
                    if extra.get("published_at"):
                        fetched[vid]["date_method"] = "channel_publication_date"
                        fetched[vid]["date_confidence"] = 0.90
    except Exception as exc:
        # A fabric must degrade gracefully when one system is unavailable.
        # An upstream outage is not a reason to fail a deploy — the committed
        # cache is still valid, so we exit clean and leave it untouched.
        log(f"! refresh failed, keeping existing cache: {exc}")
        return 0

    if not fetched:
        log("! upstream returned nothing, keeping existing cache")
        return 0

    # 4. Last resort for a brand-new video we could not date any other way.
    #    The daily cadence is what makes this defensible: a video first seen on
    #    today's run appeared within the last 24 hours, so the observation date
    #    is a tight bound. It is recorded as a DIFFERENT method at lower
    #    confidence and never laundered into a publication date — an inferred
    #    date presented as an asserted one is exactly the failure Traceability
    #    exists to catch. A later run that finds a real date overwrites it,
    #    because step 1 runs before the carry-forward in step 2.
    today = datetime.now(timezone.utc).date().isoformat()
    inferred = 0
    for vid, video in fetched.items():
        if video.get("published_at") or vid in previous.get("videos", {}):
            continue
        video["published_at"] = today
        video["date_method"] = "first_observed_by_scheduler"
        video["date_confidence"] = 0.50
        inferred += 1
    if inferred:
        log(f"{inferred} new video(s) dated by observation (no upstream date yet)")

    manifest, delta = reconcile(fetched, previous)
    MANIFEST.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
                        encoding="utf-8")

    queue = build_queue(manifest, english_only=not args.all_languages)
    QUEUE.write_text(json.dumps(
        {"generated_at": manifest["generated_at"], "pending": len(queue), "queue": queue},
        indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    active = [v for v in manifest["videos"].values() if not v.get("withdrawn")]
    dated = sum(1 for v in active if v.get("published_at"))
    authoritative = sum(1 for v in active
                        if v.get("date_method") == "channel_publication_date")

    print()
    print(f"  active {manifest['video_count']}  withdrawn {manifest['withdrawn_count']}")
    print(f"  new {len(delta['new'])}  changed {len(delta['changed'])}  "
          f"unchanged {delta['unchanged']}")
    print(f"  dated {dated}/{len(active)}  ({authoritative} authoritative, "
          f"{dated - authoritative} observed)")
    if delta["withdrawn"]:
        print(f"  ! withdrawn this run: {', '.join(delta['withdrawn'])}")
    if delta["restored"]:
        print(f"  + restored this run: {', '.join(delta['restored'])}")
    print(f"  transcription queue: {len(queue)} pending")
    return 0


if __name__ == "__main__":
    sys.exit(main())
