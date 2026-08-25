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

## Methodology note — the v0 style-card contamination and restart

**The first screening round was discarded.** Style card **v0** (machine-drafted
at the start of this session) illustrated its principles using the tournament's
own test passages, quoting the correct readings verbatim: the crap-pie / crappie
resolution, "Say hi, Funk", and the canonical "Captain Teeny Trout" spelling
alongside the three engines' wrong renderings. Any judge given that card was
handed the answer key. Lara caught this; card **v1** keeps every principle and
swaps in non-test validated examples.

Consequences, applied:

- All cells run with the v0 card are **invalid and discarded** — moved aside to
  `invalidated_v0card/` in the session scratchpad, not deleted.
- The whole screening round was re-run against v1 with rebuilt packets.
- **Standing rule going forward:** the style card may never quote a span that is
  under evaluation.

**What is *not* contamination:** the entity roster carrying "Captain Teeny Trout"
as Lucas's alias, and the packet carrying the episode title. Both are real
production metadata that a deployed judge would have, and the roster's
contribution is exactly what the ±lexicon arm is there to measure.

**A second, smaller leak, also caught and also restarted:** v1 still illustrated
self-interruption with passage **b**'s own cadence. Card **v1.1** genericised it.
The screening round was restarted a second time; the run is checked clean of
every test-passage string before use. Three rounds were therefore started and
only the third counts.

**A finding from the discarded round, kept because it is informative:** even
*with* the answer key in the card, no screened model recovered the crap-pie pun
or "Captain Teeny Trout". Whatever is blocking those two spans is not a lack of
information.

## Screening round (complete)

Every judge, full packet (style card + lexicon + flags), witness set W+YT+P,
all three passages. 10 judges x 3 passages = 30 cells, **0 parse failures** —
the "JSON array and nothing else" output spec held across every model down to
3.8B.

| judge | n | score | WER Δ | errors fixed | pun | Teeny | Funk | false corr | null corr | escalations (on-hard) | parse fail | avg s |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| qwen3.5-27b | 3 | 4.53 | -0.007 | 2/3 | 1 | 1 | 1 | 0 | 2 | 1 (0) | 0 | 119.9 |
| qwen3.5-35b-a3b | 3 | 3.62 | -0.007 | 2/3 | 1 | 1 | 1 | 1 | 2 | 20 (0) | 0 | 38.6 |
| mistral-small3.2 | 3 | 2.97 | -0.061 | 1/3 | 1 | 0 | 1 | 0 | 0 | 30 (1) | 0 | 78.4 |
| minicpm-v | 3 | 2.08 | +0.000 | 1/3 | 0 | 0 | 1 | 0 | 0 | 1 (1) | 0 | 12.5 |
| qwen38-27b-iq3m | 3 | 1.92 | +0.000 | 1/3 | 0 | 0 | 1 | 0 | 0 | 5 (0) | 0 | 27.0 |
| gemma3-27b-qat | 3 | 0.83 | +0.268 | 2/3 | 0 | 1 | 1 | 3 | 3 | 9 (0) | 0 | 140.7 |
| robody-brainstem | 3 | 0.08 | +0.000 | 1/3 | 0 | 0 | 1 | 4 | 3 | 3 (0) | 0 | 4.5 |
| qwen3.5-9b | 3 | -0.26 | +0.306 | 2/3 | 0 | 1 | 1 | 5 | 6 | 0 (0) | 0 | 18.2 |
| phi3.5 | 3 | -1.26 | +0.226 | 1/3 | 0 | 0 | 1 | 4 | 4 | 1 (0) | 0 | 10.1 |
| gutenberg-12b | 3 | -5.91 | +0.420 | 0/3 | 1 | 0 | 0 | 10 | 6 | 1 (0) | 0 | 27.9 |

## By witness set

`errors fixed` counts the one hard error per passage (the pun in a, the nickname
in b, the dropped "Say hi" in c). `pun` counts cells where a crap/pie split
survived anywhere. `false corr` is outcome-based: a phrase the human reference
confirms was already right, present in the draft, missing after the rulings are
applied. `null corr` is a "correct" verdict whose correction changes nothing —
a claimed error the model did not actually fix.

### By passage

| passage | n | score | WER Δ | errors fixed | pun | Teeny | Funk | false corr | null corr | escalations (on-hard) | parse fail | avg s |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| c | 10 | 3.78 | +0.025 | 9/10 | 0 | 0 | 9 | 6 | 10 | 31 (0) | 0 | 47.8 |
| b | 10 | 0.24 | +0.128 | 4/10 | 0 | 4 | 0 | 10 | 6 | 33 (2) | 0 | 47.4 |
| a | 10 | -1.44 | +0.191 | 0/10 | 4 | 0 | 0 | 11 | 10 | 7 (0) | 0 | 48.1 |

### What the screening round actually shows

**1. The dog-chaos passage is solved, and by consensus rather than brilliance.**
9 of 10 judges recovered "Say hi, Funk" — Whisper alone had "Funk. Hi." and
dropped the "Say hi"; YouTube and Parakeet both had "Say hi" but heard "punk".
Every judge that got it did the same thing: took the phrase from witnesses 2+3
and the name from witness 1. This is exactly the case the three-witness design
was built for, and it is the strongest result in the tournament. Passage c
averages +3.78 while a averages -1.44.

**2. Nobody gets the pun right, but the good models fail in a revealing way.**
Ground truth is "some **crap pie**, also known as **crappie**". `qwen3.5:27b`
and `qwen3.5:35b-a3b` both detect that a pun exists, cite the episode title and
the style card in their reasoning, correctly call Whisper's flattening an
error — and then write it **backwards**: "some crappie, also known as
**crap-pie**." They have the mechanism and lose the direction.
`mistral-small3.2` gets the first half right ("some crap pie") and then adopts
Parakeet's "crap copy" for the second. `gutenberg-12b` emits a bare correction
string ("crap pie") with no sentence, so it never lands.

So the pun is *detectable from text alone* — the title plus the disagreement
flag is enough to know something is there — but *which side carries the joke*
appears not to be recoverable without the audio. This is the clearest argument
in the whole run for the appellate audio tier.

**3. The nickname is a pure lexicon lookup.** 4 of 10 recovered "Captain Teeny
Trout", and all four did it by matching Whisper's "Captain Tea Truck" against
Lucas's alias in the entity roster. No judge derived it from context. This
confirms ASR_SHOWDOWN's engine-independent finding from the other direction: the
name is not in the audio evidence any engine produces, it is in the wiki.

**4. Fluency is anti-correlated with usefulness.** `gutenberg-12b` — a model
fine-tuned on literary prose — finished last (-5.91) with 10 false corrections,
rewriting confirmed-correct disfluent speech into clean sentences. It is the
style card's warning made flesh: it smooths. `phi3.5` and `qwen3.5:9b` fail the
same way at smaller scale (WER Δ +0.23 and +0.31 — they make the transcript
*worse*).

**5. Two models win by abstaining.** `minicpm-v` emits exactly 1 ruling per
passage and `qwen38-27b-iq3m` emits 1 on passage b. They score positively
(2.08, 1.92) almost entirely by not breaking anything. Under a
false-correction-penalising metric, doing nothing is a viable strategy — which
is a warning about the metric as much as about the models. Neither is a
production candidate; they are the null judge, and any real candidate has to
beat *them*, not just beat zero.

**6. Escalation is mostly noise.** 71 escalations across the round, only 2 of
them on a genuinely hard span. `mistral-small3.2` escalated 21 spans on passage
b alone. Nobody has calibrated uncertainty; they escalate on disfluency, which
is the one thing that is reliably *not* an error.

### Finalists for the full ablation grid

`qwen3.5:27b` (4.53, cleanest — 0 false corrections, recovers both the nickname
and Funk, only judge with a negative WER Δ on b), `qwen3.5:35b-a3b` (3.62 and
3x faster — MoE, 38.6 s/cell vs 119.9), `mistral-small3.2` (2.97, the only
judge with a meaningfully negative overall WER Δ and 0 false corrections).

