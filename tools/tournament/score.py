#!/usr/bin/env python3
"""Scorer for the transcript-adjudicator tournament.

CONTAINS GROUND TRUTH (Lara's by-ear transcriptions, ASR_SHOWDOWN.md §7).
This module must NEVER be imported by, or its contents leaked into, anything
that builds a prompt. Packets are sealed; scoring happens here only.

Metrics per cell (design doc, round 3 + round 4):
  wer_delta          WER of the corrected transcript vs raw Whisper, over the
                     human-validated excerpt window (negative = improvement)
  name_recovery      did the ruling recover Teeny Trout / Funk / Monty
  pun_preservation   does the crap-pie / crappie distinction survive
  false_corrections  "correct" verdicts against spans the human text confirms
                     were already right  (heavily penalised)
  coherence          are the produced corrections well-formed utterances
  escalation         did it flag the genuinely-hard spans as beyond its reach
"""
import json, re, sys
from difflib import SequenceMatcher
from pathlib import Path

FILLERS = {"uh", "um", "mm", "hmm", "mmhmm", "ah", "er", "eh", "oh", "hah", "ha"}


def norm(text):
    text = (text or "").lower().replace("gimme", "give me").replace("'em", "them")
    text = re.sub(r"[^a-z0-9\s']", " ", text)
    return [t.strip("'") for t in text.split() if t.strip("'") and t.strip("'") not in FILLERS]


# ---------------------------------------------------------------- ground truth
# Lara, by ear, 2026-08-24. Excerpt-level: only the spans she validated.
GT = {
    "a": {
        "ref": "today we are targeting some crap pie also known as crappie",
        # spans where the Whisper draft is WRONG and a good judge should fix it
        "errors": [
            {"id": "pun", "draft": "crappie, also known as crappie",
             "accept": [r"crap[\s\-]pie.{0,30}also known as.{0,15}crappie"]},
        ],
        # spans the human text CONFIRMS are already right — changing them is a
        # false correction
        "confirmed": ["targeting", "also known as", "bluegills", "unsuccessful fishing show",
                      "ladies and gentlemen", "ss tin can"],
    },
    "b": {
        "ref": ("i caught like seven crappies ish i let one or two go "
                "captain teeny trout gave me one"),
        "errors": [
            {"id": "teeny_trout", "draft": "Captain Tea Truck",
             "accept": [r"captain\s+teeny\s+trout"]},
        ],
        "confirmed": ["seven", "crappies", "ish", "i let one or two go",
                      "gave me one", "bluegills", "nice gills"],
    },
    "c": {
        "ref": "say hi funk hi go get it monty",
        "errors": [
            {"id": "say_hi", "draft": "Funk. Hi.",
             "accept": [r"say hi,?\s+funk"]},
        ],
        "confirmed": ["funk", "go get it", "monty", "he won't give it to me",
                      "you little stinker", "give me that"],
        # traps: witnesses 2+3 say "punk"; the human reference says Funk.
        "traps": [{"id": "funk_to_punk", "bad": r"\bpunk\b"}],
    },
}

NAME_TARGETS = {"b": [("teeny trout", r"teeny\s+trout")],
                "c": [("funk", r"\bfunk\b"), ("monty", r"\bmonty\b")]}


def wer(ref_tokens, hyp_tokens):
    n, m = len(ref_tokens), len(hyp_tokens)
    d = [[0] * (m + 1) for _ in range(n + 1)]
    for i in range(n + 1):
        d[i][0] = i
    for j in range(m + 1):
        d[0][j] = j
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            c = 0 if ref_tokens[i - 1] == hyp_tokens[j - 1] else 1
            d[i][j] = min(d[i - 1][j] + 1, d[i][j - 1] + 1, d[i - 1][j - 1] + c)
    return d[n][m] / max(1, n)


def best_window_wer(ref, hyp_text):
    """WER of the reference against its best-matching window of the hypothesis."""
    ref_t = norm(ref)
    hyp_t = norm(hyp_text)
    if not hyp_t:
        return 1.0
    n = len(ref_t)
    best = 1.0
    for size in (n, int(n * 1.4) + 2):
        for i in range(0, max(1, len(hyp_t) - size + 1)):
            best = min(best, wer(ref_t, hyp_t[i:i + size]))
    return best


def apply_rulings(draft, rulings):
    """Apply 'correct' verdicts to the draft, sentence-wise."""
    text = draft
    applied, unmatched = 0, 0
    for r in rulings or []:
        if not isinstance(r, dict):
            continue
        if str(r.get("verdict", "")).lower() != "correct":
            continue
        corr = r.get("correction")
        if not corr or not isinstance(corr, str):
            unmatched += 1
            continue
        span = str(r.get("span") or "").strip()
        sents = re.split(r"(?<=[.!?])\s+", text)
        sim = [SequenceMatcher(None, " ".join(norm(s)), " ".join(norm(corr))).ratio()
               for s in sents]
        # candidate sentences: those containing the span (exactly or normalised)
        cands = []
        if span and span != "(nothing)":
            sn = " ".join(norm(span))
            for i, s in enumerate(sents):
                if span.lower() in s.lower() or (sn and sn in " ".join(norm(s))):
                    cands.append(i)
        # the judge rules on the sentence CONTAINING the span; where the span is
        # ambiguous (one-word spans match many sentences) the correction itself
        # disambiguates, so pick the candidate the correction most resembles
        if cands:
            hit = max(cands, key=lambda i: sim[i])
            if sim[hit] < 0.2 and len(cands) > 1:
                hit = None
        else:
            hit = sim.index(max(sim)) if sim and max(sim) > 0.45 else None
        if hit is None:
            unmatched += 1
            continue
        sents[hit] = corr.strip()
        text = " ".join(sents)
        applied += 1
    return text, applied, unmatched


def coherence(rulings):
    """Well-formedness of produced corrections, 0..1. Null-corrections penalised."""
    corrs = [r.get("correction") for r in (rulings or [])
             if isinstance(r, dict) and str(r.get("verdict", "")).lower() == "correct"]
    corrs = [c for c in corrs if isinstance(c, str) and c.strip()]
    if not corrs:
        return None
    good = 0
    for c in corrs:
        c = c.strip()
        toks = c.split()
        ok = len(toks) >= 3
        ok &= bool(re.search(r"[.!?\"']$", c)) or len(toks) >= 3
        # adjacent duplicated bigrams read as ASR debris, not human speech
        nt = norm(c)
        ok &= not any(nt[i:i + 2] == nt[i + 2:i + 4] for i in range(len(nt) - 3))
        good += bool(ok)
    return good / len(corrs)


def score_cell(rec, packets):
    pid = rec["passage"]
    gt = GT[pid]
    pk = packets[f"{pid}__{rec['witness_set'].replace('+','_')}"]
    draft = pk["draft_transcript"]
    rulings = rec.get("rulings")
    out = {"judge": rec["judge"], "passage": pid, "witness_set": rec["witness_set"],
           "ablation": rec["ablation"], "elapsed": rec.get("elapsed"),
           "n_rulings": None, "parse_ok": rulings is not None}
    if rulings is None:
        out.update({"score": None, "note": rec.get("parse_note") or rec.get("error")})
        return out

    corrected, applied, unmatched = apply_rulings(draft, rulings)
    out["n_rulings"] = len(rulings)
    out["applied"] = applied
    out["unmatched"] = unmatched

    base_wer = best_window_wer(gt["ref"], draft)
    new_wer = best_window_wer(gt["ref"], corrected)
    out["wer_raw"] = round(base_wer, 4)
    out["wer_after"] = round(new_wer, 4)
    out["wer_delta"] = round(new_wer - base_wer, 4)   # negative = improvement

    # --- error-span recovery (incl. pun) --------------------------------------
    fixed = []
    for e in gt["errors"]:
        got = any(re.search(p, corrected, re.I | re.S) for p in e["accept"])
        fixed.append(e["id"] if got else None)
        out[f"fix_{e['id']}"] = bool(got)
    out["errors_fixed"] = sum(1 for f in fixed if f)
    out["errors_total"] = len(gt["errors"])

    # --- pun preservation (passage a) -----------------------------------------
    if pid == "a":
        m = re.search(r"targeting some (.{0,14}?),? also known as (.{0,14}?)[.,]",
                      corrected, re.I)
        if m:
            lhs, rhs = norm(m.group(1)), norm(m.group(2))
            out["pun_preserved"] = lhs != rhs and "crap" in " ".join(lhs)
        else:
            out["pun_preserved"] = bool(re.search(r"crap[\s\-]pie", corrected, re.I))

    # --- name recovery ---------------------------------------------------------
    if pid in NAME_TARGETS:
        rec_names = {n: bool(re.search(p, corrected, re.I))
                     for n, p in NAME_TARGETS[pid]}
        out["names"] = rec_names
        out["name_recovery"] = sum(rec_names.values()) / len(rec_names)

    # --- traps (e.g. Funk -> punk) --------------------------------------------
    trapped = []
    for t in gt.get("traps", []):
        if re.search(t["bad"], corrected, re.I) and not re.search(t["bad"], draft, re.I):
            trapped.append(t["id"])
    out["traps_hit"] = trapped

    # --- false corrections -----------------------------------------------------
    # Outcome-based: a phrase the human text confirms was already right, present
    # in the draft, is missing after the rulings are applied. Span-matching is
    # unreliable because weak judges emit one-word spans.
    nd, nc = " ".join(norm(draft)), " ".join(norm(corrected))
    destroyed = [c for c in gt["confirmed"]
                 if " ".join(norm(c)) in nd and " ".join(norm(c)) not in nc]
    out["destroyed_confirmed"] = destroyed
    out["false_corrections"] = len(destroyed) + len(trapped)

    # verdict discipline: "correct" rulings whose correction leaves the located
    # sentence unchanged, i.e. the model claimed an error it did not actually fix
    null_corr = 0
    for r in rulings:
        if isinstance(r, dict) and str(r.get("verdict", "")).lower() == "correct":
            c = " ".join(norm(str(r.get("correction") or "")))
            if c and c in nd:
                null_corr += 1
    out["null_corrections"] = null_corr

    # --- escalation quality ----------------------------------------------------
    esc_spans = [" ".join(norm(str(r.get("span") or ""))) for r in rulings
                 if isinstance(r, dict) and str(r.get("verdict", "")).lower() == "escalate"]
    hard = [" ".join(norm(e["draft"])) for e in gt["errors"]]
    esc_on_hard = sum(1 for h in hard if any(h in s or s in h for s in esc_spans if s))
    esc_on_confirmed = sum(1 for s in esc_spans
                           if s and any(s in " ".join(norm(c)) for c in gt["confirmed"]))
    out["escalations"] = len(esc_spans)
    out["escalate_on_hard"] = esc_on_hard
    out["escalate_on_confirmed"] = esc_on_confirmed

    # --- composite -------------------------------------------------------------
    coh = coherence(rulings)
    out["coherence"] = None if coh is None else round(coh, 3)
    s = 0.0
    s += 3.0 * (out["errors_fixed"] / max(1, out["errors_total"]))
    if pid == "a":
        s += 2.0 * float(out.get("pun_preserved") or 0)
    if "name_recovery" in out:
        s += 2.0 * out["name_recovery"]
    s += -1.0 * out["wer_delta"] * 5.0            # improvement rewarded
    s -= 1.5 * out["false_corrections"]           # heavily penalised
    s += 0.5 * (coh if coh is not None else 0.5)
    s += 0.5 * min(1.0, esc_on_hard)              # knew what it didn't know
    s -= 0.25 * esc_on_confirmed
    out["score"] = round(s, 3)
    return out


def main():
    packets = {p.stem: json.loads(p.read_text())
               for p in Path(sys.argv[1]).glob("*.json") if p.name != "manifest.json"}
    rows = []
    for f in sorted(Path(sys.argv[2]).glob("*.json")):
        rec = json.loads(f.read_text())
        if "judge" not in rec:
            continue
        try:
            rows.append(score_cell(rec, packets))
        except Exception as e:
            rows.append({"judge": rec.get("judge"), "passage": rec.get("passage"),
                         "witness_set": rec.get("witness_set"),
                         "ablation": rec.get("ablation"), "score": None,
                         "note": f"scorer-error: {e}"})
    outp = Path(sys.argv[3]) if len(sys.argv) > 3 else None
    if outp:
        outp.write_text(json.dumps(rows, indent=2))
    print(json.dumps(rows, indent=2))


if __name__ == "__main__":
    main()
