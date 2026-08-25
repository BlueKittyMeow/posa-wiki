#!/usr/bin/env python3
"""Aggregate scored cells into the markdown tables used in TOURNAMENT_RESULTS.md.

Usage: report.py <packetdir> <rundir> [<rundir> ...]
"""
import json, sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from score import score_cell  # noqa: E402


def load(packetdir, rundirs):
    packets = {p.stem: json.loads(p.read_text())
               for p in Path(packetdir).glob("*.json") if p.name != "manifest.json"}
    rows = []
    for rd in rundirs:
        for f in sorted(Path(rd).glob("*.json")):
            rec = json.loads(f.read_text())
            if "judge" not in rec:
                continue
            try:
                rows.append(score_cell(rec, packets))
            except Exception as e:
                rows.append({"judge": rec.get("judge"), "passage": rec.get("passage"),
                             "witness_set": rec.get("witness_set"),
                             "ablation": rec.get("ablation"), "score": None,
                             "note": str(e)})
    return rows


def agg(rows, keyf):
    g = defaultdict(list)
    for r in rows:
        g[keyf(r)].append(r)
    out = []
    for k, rs in g.items():
        sc = [r["score"] for r in rs if r.get("score") is not None]
        out.append({
            "key": k, "n": len(rs),
            "parse_fail": sum(1 for r in rs if not r.get("parse_ok")),
            "score": round(sum(sc) / len(sc), 2) if sc else None,
            "wer_delta": round(sum(r.get("wer_delta") or 0 for r in rs) / max(1, len(rs)), 3),
            "errors_fixed": sum(r.get("errors_fixed") or 0 for r in rs),
            "errors_total": sum(r.get("errors_total") or 0 for r in rs),
            "pun": sum(1 for r in rs if r.get("pun_preserved")),
            "teeny": sum(1 for r in rs if (r.get("names") or {}).get("teeny trout")),
            "funk": sum(1 for r in rs if (r.get("names") or {}).get("funk")),
            "false_corr": sum(r.get("false_corrections") or 0 for r in rs),
            "null_corr": sum(r.get("null_corrections") or 0 for r in rs),
            "esc": sum(r.get("escalations") or 0 for r in rs),
            "esc_hard": sum(r.get("escalate_on_hard") or 0 for r in rs),
            "sec": round(sum(r.get("elapsed") or 0 for r in rs) / max(1, len(rs)), 1),
        })
    return sorted(out, key=lambda x: (x["score"] is None, -(x["score"] or 0)))


def table(rowdicts, keyname):
    hdr = (f"| {keyname} | n | score | WER Δ | errors fixed | pun | Teeny | Funk | "
           f"false corr | null corr | escalations (on-hard) | parse fail | avg s |")
    sep = "|" + "---|" * 13
    lines = [hdr, sep]
    for r in rowdicts:
        lines.append(
            f"| {r['key']} | {r['n']} | {r['score'] if r['score'] is not None else '—'} | "
            f"{r['wer_delta']:+.3f} | {r['errors_fixed']}/{r['errors_total']} | {r['pun']} | "
            f"{r['teeny']} | {r['funk']} | {r['false_corr']} | {r['null_corr']} | "
            f"{r['esc']} ({r['esc_hard']}) | {r['parse_fail']} | {r['sec']} |")
    return "\n".join(lines)


if __name__ == "__main__":
    rows = load(sys.argv[1], sys.argv[2:])
    print("## By judge\n")
    print(table(agg(rows, lambda r: r["judge"]), "judge"))
    print("\n## By witness set\n")
    print(table(agg(rows, lambda r: r["witness_set"]), "witness set"))
    print("\n## By ablation\n")
    print(table(agg(rows, lambda r: r["ablation"]), "packet"))
    print("\n## By passage\n")
    print(table(agg(rows, lambda r: r["passage"]), "passage"))
    print("\n## By judge x ablation\n")
    print(table(agg(rows, lambda r: f"{r['judge']} / {r['ablation']}"), "cell"))
    Path("scored_rows.json").write_text(json.dumps(rows, indent=2))
