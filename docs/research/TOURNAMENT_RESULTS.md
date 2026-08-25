# Transcript-Adjudicator Tournament — results

**Status:** IN PROGRESS (screening round running). This file is written
incrementally so partial results survive.

Protocol: `TRANSCRIPT_VERIFICATION_DESIGN.md` (rounds 1–4).
Ground truth: `ASR_SHOWDOWN.md` §7, sealed — never enters a packet.
Tooling: `tools/tournament/` (build_packets, judge_prompt, runner, score, report).

## Setup

- **Material:** *Crap-Pie — The Unsuccessful Fishing Show — Episode 15* `[-zr_N8CDKUA]`,
  three human-validated passages: **a** 63–100 s (the crappie/crap-pie pun),
  **b** 1650–1700 s (Captain Teeny Trout + fish counts), **c** 1790–1835 s (dog chaos).
- **Witnesses:** Whisper large-v3 prompted (`E:\ai\asr_showdown\out\whisper`),
  YouTube auto-subs (Factotum `transcript_segments`, 522 segs), Parakeet TDT.
- **Packets:** per passage × witness set, carrying aligned excerpts with timestamps,
  word-level disagreement flags (ASR_SHOWDOWN §7b normalisation), Whisper
  word-confidence lows, the wiki entity roster, and video title/description.
- **Style card:** `POSA_STYLE_CARD.md` v0 (drafted this session, awaiting Lara).

(results tables follow when the round completes)
