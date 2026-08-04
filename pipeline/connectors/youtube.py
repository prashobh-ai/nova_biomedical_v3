"""YouTube connector — the company channel is product documentation that happens to be spoken.

Design notes, because two decisions here are load-bearing:

1. TWO RECORD TIERS, NOT ONE.
   A video contributes two kinds of knowledge with very different provenance:

     'video_metadata'   Title, description and playlist membership. Written by Nova.
                        Publisher-authored, short, clean prose, and dated by the
                        upload timestamp. Fully citable, same tier as a document.

     'video_transcript' What the presenter said, recovered by speech recognition.
                        Machine-derived. Retrievable and able to *support* an answer,
                        but marked as such so the UI can say so and the citation can
                        deep-link to the second where it was spoken.

   Collapsing these into one tier would let an ASR artefact be presented with the
   same authority as a printed IFU sentence. The whole product argument is that we
   can tell the difference, so the ingest layer has to preserve it.

2. PLAYLIST MEMBERSHIP IS AN ASSERTED EDGE, NOT AN INFERRED ONE.
   Nova put each video in 'StatSensor®' or 'Bioprocessing' by hand. That is a
   publisher assertion linking a video to a product entity that already exists in
   the document corpus — stronger evidence than anything our NER infers from the
   text. We seed entities from it directly, which is what makes a video answer a
   question alongside a 510(k) record.

Everything is read from the committed cache under knowledge_sources/youtube/.
This connector never touches the network — see scripts/youtube_refresh.py.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Iterator

from .base import KnowledgeRecord

YOUTUBE_WATCH = "https://www.youtube.com/watch?v="

# Playlist title -> (facet kind, canonical value). Nova's own taxonomy, three axes.
# Product values MUST match _infer_product() in documents.py or the graph will not
# join videos to documents — that join is the entire point.
PLAYLIST_FACETS = {
    "StatSensor®": ("product", "StatSensor Creatinine"),
    "StatStrip®": ("product", "StatStrip Glucose"),
    "Stat Profile®": ("product", "Stat Profile Prime Plus"),
    "Allegro®": ("product", "Nova Allegro"),
    "Nova Max Pro™": ("product", "Nova Max"),
    "Nova Pro™": ("product", "Nova Primary Glucose Analyzer"),
    "BioProfile®": ("product", "BioProfile FLEX2"),
    "Artel®": ("product", "Artel MVS"),
    "NanoCellect®": ("product", "NanoCellect"),
    "Nova Vet™": ("product", "Nova Vet"),
    "Hospital": ("segment", "Hospital"),
    "Outpatient Care": ("segment", "Outpatient Care"),
    "Bioprocessing": ("segment", "Bioprocessing"),
    "Veterinary": ("segment", "Veterinary"),
    "Product Demonstrations (Virtual & In-Person)": ("content_type", "Product Demonstration"),
    "On-Demand Educational Webinars": ("content_type", "Webinar"),
    "Educational In-Person Seminars": ("content_type", "Seminar"),
    "ArtelWare™ Training Program | Artel MVS® & Artel PCS®": ("content_type", "Software Training"),
}

# Language playlists — publisher-declared, so no detection heuristic is needed.
LANGUAGE_PLAYLISTS = {
    "English (US)": "en",
    "Japanese | 日本語": "ja",
    "French (France) | Français": "fr",
    "Spanish (Spain) | Español": "es",
    "Portuguese (Portugal) | Português": "pt",
}

TARGET_CHARS = 700          # matches chunker.TARGET_CHARS
MIN_SEGMENT_CHARS = 120     # below this a transcript segment cites badly


def _facets(playlists: list[str]) -> dict:
    """Fold playlist membership into typed facets."""
    out: dict = {"product": "", "segment": "", "content_type": "", "language": "en"}
    for title in playlists:
        if title in LANGUAGE_PLAYLISTS:
            out["language"] = LANGUAGE_PLAYLISTS[title]
            continue
        hit = PLAYLIST_FACETS.get(title)
        if hit:
            kind, value = hit
            if not out[kind]:
                out[kind] = value
    return out


def _timestamp_url(video_id: str, start_sec: float) -> str:
    """Deep link to the exact second. This is the citation — one click and the
    user hears the sentence being spoken, which is stronger verification than a
    page number in a PDF."""
    return f"{YOUTUBE_WATCH}{video_id}&t={int(start_sec)}s"


def _clock(seconds: float) -> str:
    s = int(seconds)
    h, rem = divmod(s, 3600)
    m, sec = divmod(rem, 60)
    return f"{h}:{m:02d}:{sec:02d}" if h else f"{m}:{sec:02d}"


def pack_cues(cues: list[dict], target: int = TARGET_CHARS) -> Iterator[dict]:
    """Repack timestamped ASR cues into citable passages.

    Cues arrive as fragments with no paragraph structure. We accumulate until the
    target size, preferring to break on a sentence boundary, and carry the start
    time of the first cue and the end time of the last. That start time becomes
    the citation anchor, so a passage must never span a topic change silently —
    breaking on sentence ends keeps the anchor honest.
    """
    buf: list[str] = []
    start = end = 0.0
    size = 0

    for cue in cues:
        text = (cue.get("text") or "").strip()
        if not text:
            continue
        if not buf:
            start = float(cue.get("start", 0.0))
        buf.append(text)
        end = float(cue.get("end", start))
        size += len(text) + 1

        ends_sentence = text.endswith((".", "!", "?"))
        if size >= target and ends_sentence:
            yield {"text": " ".join(buf), "start": start, "end": end}
            buf, size = [], 0
        elif size >= target * 1.6:      # hard stop — never let a passage run away
            yield {"text": " ".join(buf), "start": start, "end": end}
            buf, size = [], 0

    if buf and size >= MIN_SEGMENT_CHARS:
        yield {"text": " ".join(buf), "start": start, "end": end}


class YouTubeConnector:
    """Reads the committed cache. Never fetches."""

    name = "Nova Biomedical YouTube"
    source_type = "video"

    def __init__(self, root: Path):
        self.root = Path(root)
        self.manifest_path = self.root / "manifest.json"
        self.transcript_dir = self.root / "transcripts"

    # ------------------------------------------------------------------ cache
    def _videos(self) -> list[dict]:
        if not self.manifest_path.exists():
            return []
        data = json.loads(self.manifest_path.read_text(encoding="utf-8"))
        return list(data.get("videos", {}).values())

    def _transcript(self, video_id: str) -> list[dict]:
        path = self.transcript_dir / f"{video_id}.json"
        if not path.exists():
            return []
        try:
            return json.loads(path.read_text(encoding="utf-8")).get("cues", [])
        except (json.JSONDecodeError, OSError):
            return []

    # ----------------------------------------------------------------- fetch
    def fetch(self) -> Iterator[KnowledgeRecord]:
        for video in self._videos():
            # A withdrawn video keeps its manifest entry so supersession stays
            # checkable, but must not answer questions.
            if video.get("withdrawn"):
                continue

            vid = video.get("video_id")
            if not vid:
                continue

            playlists = video.get("playlists", [])
            facets = _facets(playlists)
            title = video.get("title", "").strip()
            description = (video.get("description") or "").strip()
            published = video.get("published_at", "")[:10]
            duration = video.get("duration_sec", 0)

            entity_seeds = []
            if facets["product"]:
                entity_seeds.append(("Product", facets["product"]))
            if facets["segment"]:
                entity_seeds.append(("Segment", facets["segment"]))

            base_meta = {
                "video_id": vid,
                "channel": video.get("channel", "Nova Biomedical"),
                "published_at": published,
                "duration_sec": duration,
                "playlists": playlists,
                "product": facets["product"] or "Unclassified",
                "segment": facets["segment"],
                "content_type": facets["content_type"] or "Video",
                "language": facets["language"],
                "domain": "Product Media",
            }

            # ---- Tier 1: publisher-authored metadata -----------------------
            # Verbalised, not dumped as fields — same reasoning as the FDA
            # connector: a title on its own is invisible to lexical retrieval.
            parts = [f"Nova Biomedical published the video '{title}'"]
            if facets["product"]:
                parts.append(f"covering {facets['product']}")
            if published:
                parts.append(f"on {published}")
            sentence = " ".join(parts) + "."
            if description:
                sentence += f" {description}"
            if facets["content_type"]:
                sentence += f" It is published as a {facets['content_type'].lower()}."
            if playlists:
                sentence += f" It appears in the following channel playlists: {', '.join(playlists)}."

            yield KnowledgeRecord(
                source_type=self.source_type,
                source_system=self.name,
                source_id=f"{vid}#meta",
                title=title,
                text=sentence,
                section_path=[facets["content_type"] or "Video", title],
                page=1,
                url=f"{YOUTUBE_WATCH}{vid}",
                metadata={
                    **base_meta,
                    "record_type": "video_metadata",
                    "evidence_tier": "publisher_authored",
                    "provenance_label": "Published video description",
                    "start_sec": 0,
                    "timestamp_label": "",
                },
                entities=entity_seeds,
            )

            # ---- Tier 2: transcript, provenance-marked ---------------------
            cues = self._transcript(vid)
            if not cues:
                continue

            asr = json.loads((self.transcript_dir / f"{vid}.json").read_text(encoding="utf-8"))
            model = asr.get("model", "unknown")

            for idx, seg in enumerate(pack_cues(cues), start=1):
                if len(seg["text"]) < MIN_SEGMENT_CHARS:
                    continue
                yield KnowledgeRecord(
                    source_type=self.source_type,
                    source_system=self.name,
                    source_id=f"{vid}#t{idx}",
                    title=title,
                    text=seg["text"],
                    # The four-level address, video edition:
                    #   playlist -> video -> timestamp
                    section_path=[facets["content_type"] or "Video", title,
                                  f"at {_clock(seg['start'])}"],
                    page=idx,                       # segment index, mirrors page
                    url=_timestamp_url(vid, seg["start"]),
                    metadata={
                        **base_meta,
                        "record_type": "video_transcript",
                        "evidence_tier": "machine_transcribed",
                        "provenance_label": f"Spoken at {_clock(seg['start'])} — "
                                            f"transcribed automatically ({model}), "
                                            f"verify against the recording",
                        "segment_index": idx,
                        "start_sec": round(seg["start"], 2),
                        "end_sec": round(seg["end"], 2),
                        "timestamp_label": _clock(seg["start"]),
                        "asr_model": model,
                    },
                    entities=entity_seeds,
                )
