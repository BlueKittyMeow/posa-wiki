#!/usr/bin/env python3
"""Build sealed adjudication packets for the transcript-adjudicator tournament.

Reads the three ASR witness transcripts (Whisper large-v3 prompted, YouTube auto-subs,
Parakeet TDT) for video -zr_N8CDKUA plus the wiki entity roster, and emits one JSON
packet per (passage x witness-set) combination.

GROUND TRUTH NEVER ENTERS A PACKET. Lara's human transcriptions (ASR_SHOWDOWN.md §7)
live only in score.py and are never serialised here.

Usage: build_packets.py <datadir> <outdir>
  datadir must contain whisper.segments.json, parakeet.segments.json, factotum.json
"""
import json, re, sys, itertools
from difflib import SequenceMatcher
from pathlib import Path

# The three human-validated passages (ASR_SHOWDOWN §3 / §7).
PASSAGES = {
    "a": {"start": 63.0, "end": 100.0, "label": "cold open - show name + the crappie/crap-pie pun"},
    "b": {"start": 1650.0, "end": 1700.0, "label": "fast recap - the Captain nickname + fish counts"},
    "c": {"start": 1790.0, "end": 1835.0, "label": "overlapping dog play - rapid short utterances"},
}

WITNESS_SETS = {
    "W":     ["whisper"],
    "W+YT":  ["whisper", "youtube"],
    "W+YT+P": ["whisper", "youtube", "parakeet"],
}

# Same normalisation as ASR_SHOWDOWN §7b.
FILLERS = {"uh", "um", "mm", "hmm", "mmhmm", "ah", "er", "eh", "oh"}


def norm_tokens(text):
    text = text.lower().replace("gimme", "give me").replace("'em", "them")
    text = re.sub(r"[^a-z0-9\s']", " ", text)
    toks = [t.strip("'") for t in text.split()]
    return [t for t in toks if t and t not in FILLERS]


def load_witnesses(datadir):
    d = Path(datadir)
    w = json.loads((d / "whisper.segments.json").read_text())
    p = json.loads((d / "parakeet.segments.json").read_text())
    f = json.loads((d / "factotum.json").read_text())
    yt = [{"start": s["start_seconds"],
           "end": s["start_seconds"] + (s["duration_seconds"] or 0),
           "text": s["text"]}
          for s in f["yt_segments"]]
    whisper = [{"start": s["start"], "end": s["end"], "text": s["text"].strip(),
                "words": s.get("words", [])} for s in w]
    parakeet = [{"start": s["start"], "end": s["end"], "text": s["text"].strip()} for s in p]
    return {"whisper": whisper, "youtube": yt, "parakeet": parakeet}, f


def slice_segments(segs, start, end):
    """Segments overlapping the window."""
    return [s for s in segs if s["end"] > start and s["start"] < end]


def excerpt_text(segs):
    return " ".join(s["text"].strip() for s in segs).strip()


def whisper_low_conf(segs, thresh=0.55):
    """Words with faster-whisper probability below threshold."""
    lows = []
    for s in segs:
        for wd in s.get("words", []):
            if wd.get("p") is not None and wd["p"] < thresh:
                lows.append({"word": wd["w"].strip(), "t": round(wd["s"], 2),
                             "p": round(wd["p"], 3)})
    return sorted(lows, key=lambda x: x["p"])


def disagreement_flags(texts_by_witness):
    """Word-level diff across available witnesses, Whisper as the pivot.

    Returns spans where any witness disagrees with Whisper, with each witness's
    reading of that span.
    """
    if len(texts_by_witness) < 2:
        return []
    base_name = "whisper"
    base = norm_tokens(texts_by_witness[base_name])
    flags = {}
    for name, text in texts_by_witness.items():
        if name == base_name:
            continue
        other = norm_tokens(text)
        sm = SequenceMatcher(a=base, b=other, autojunk=False)
        for tag, i1, i2, j1, j2 in sm.get_opcodes():
            if tag == "equal":
                continue
            # context window in the pivot for locating the span
            lo, hi = max(0, i1 - 3), min(len(base), i2 + 3)
            key = (i1, i2)
            fl = flags.setdefault(key, {
                "whisper_span": " ".join(base[i1:i2]) or "(nothing)",
                "context": " ".join(base[lo:hi]),
                "alternatives": {},
            })
            fl["alternatives"][name] = " ".join(other[j1:j2]) or "(nothing)"
    out = [v for k, v in sorted(flags.items())]
    # drop pure-filler noise
    return [f for f in out if f["whisper_span"] != "(nothing)"
            or any(a != "(nothing)" for a in f["alternatives"].values())]


def build(datadir, outdir):
    wits, fact = load_witnesses(datadir)
    outdir = Path(outdir); outdir.mkdir(parents=True, exist_ok=True)

    people = []
    for p in fact["people"]:
        al = p.get("aliases")
        try:
            al = json.loads(al) if al else []
        except Exception:
            al = [a.strip() for a in str(al).split(",") if a.strip()]
        people.append({"name": p["canonical_name"], "aliases": al})
    roster = {
        "people": people,
        # nickname used in this episode for the second angler; not a DB row
        "nicknames_in_play": ["Captain Teeny Trout"],
        "dogs": [{"name": d["name"], "breed": d.get("breed_primary")} for d in fact["dogs"]],
        "domain_terms": ["crappie", "crappies", "bluegill", "bluegills", "gills",
                         "Boundary Waters", "steel eater", "SS Tin Can"],
    }
    video = {"title": fact["video"]["title"],
             "description": (fact["video"]["description"] or "")[:1500]}

    manifest = []
    for pid, p in PASSAGES.items():
        per_wit = {}
        for name, segs in wits.items():
            sl = slice_segments(segs, p["start"], p["end"])
            per_wit[name] = {
                "segments": [{"t": round(s["start"], 2), "text": s["text"]} for s in sl],
                "text": excerpt_text(sl),
                "_raw": sl,
            }
        lows = whisper_low_conf(per_wit["whisper"]["_raw"])

        for ws_name, members in WITNESS_SETS.items():
            texts = {m: per_wit[m]["text"] for m in members}
            flags = disagreement_flags(texts)
            packet = {
                "packet_id": f"{pid}__{ws_name.replace('+','_')}",
                "passage": pid,
                "passage_window": [p["start"], p["end"]],
                "passage_label": p["label"],
                "witness_set": ws_name,
                "video": video,
                "entity_roster": roster,
                "witnesses": {m: {"segments": per_wit[m]["segments"],
                                  "text": per_wit[m]["text"]} for m in members},
                "draft_transcript": per_wit["whisper"]["text"],
                "disagreement_flags": flags,
                "whisper_low_confidence": lows,
            }
            (outdir / f"{packet['packet_id']}.json").write_text(
                json.dumps(packet, indent=2))
            manifest.append({"packet_id": packet["packet_id"], "passage": pid,
                             "witness_set": ws_name, "n_flags": len(flags),
                             "n_lowconf": len(lows)})
    (outdir / "manifest.json").write_text(json.dumps(manifest, indent=2))
    for m in manifest:
        print(m)


if __name__ == "__main__":
    build(sys.argv[1], sys.argv[2])
