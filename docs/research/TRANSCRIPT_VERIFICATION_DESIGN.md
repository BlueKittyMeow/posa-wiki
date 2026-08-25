# Transcript Verification Pass — design (agreed with Lara, 2026-08-24)

*The "feed it back through for uncertainty checks" pipeline. Runs after the
Whisper batch; this doc is the build spec.*

## Uncertainty signals (cheap → expensive)

1. **Whisper word/segment confidence** — per-word probabilities kept from the
   batch run (not discarded). Low-probability spans flagged.
2. **3-engine consensus voting** — we hold THREE independent transcripts per
   video: YouTube ASR (already ingested), Whisper large-v3 (batch), Parakeet
   TDT (runs as third juror — author-quality irrelevant, independence is the
   point; adds ~19 GPU-hours). 2-of-3 agreement auto-resolves most flags;
   3-way splits escalate. Validated by the listening-sheet findings: crap-pie,
   Teeny Trout, and Funk/punk ALL lived in the disagreement zone.
3. **Lexicon anomaly detection** — fuzzy near-misses of known entities
   (people/dogs/lakes/Posaisms) flag the span AND carry a proposed correction
   ("Captain Tea Truck" ≈ Captain Teeny Trout).
4. **LLM re-read (adjudication)** — a model receives: draft transcript,
   flags from 1–3, entity roster, video title/description. Verdict per flag:
   confirm / propose correction / escalate-to-human. Bulk pass on local
   MarshLair models (free); hardest spans optionally to a cheap Claude tier.
   ALL LLM output is candidate-only, never direct write.

## Write rules

- Auto-apply only: 2-of-3 consensus + lexicon-exact corrections, provenance
  `source='whisper+consensus'`.
- Everything else → review queue, provenance trail intact.
- Human decisions untouchable (same rule as seasons/nights).

## Review dashboard (Lara's spec)

A transcript-review page with a **pinned persistent player** (IFrame API, same
as /watch): sticky player at top, uncertainty cards below. Clicking a card:
same video already loaded → `player.seekTo(t)`; different video →
`loadVideoById({videoId, startSeconds})`. No page loads, no external tabs,
Premium session preserved. Pattern should later retrofit onto the
lake-mentions queue (same watch-the-moment review shape).

## Local-model adjudication tournament (prereq for signal 4)

Blind eval using the Crap-Pie listening-sheet passages: Lara's ground-truth
transcript exists (ASR_SHOWDOWN.md §7) and is **hidden from all contestants**.
Each local MarshLair model (enumerate ALL ollama stores: default C: store +
`E:\ai\ollama-agent\models` + `D:\ai\ollama-quant-survival`, plus the
marshlair-chat stack's models) gets the identical packet (Whisper draft +
disagreement flags + entity roster + title/description) and returns
corrections + escalations. Score against hidden ground truth:
- WER improvement over raw Whisper
- name recovery (Teeny Trout, Funk)
- **pun preservation** (does it protect "crap-pie" or smooth it like Whisper?)
- **false-correction rate** (fixing correct text into plausible text is worse
  than useless — heavily penalized)
- escalation judgment (does it know what it doesn't know?)
Winner becomes the pipeline's resident adjudicator.

## Sequencing

nights facet → Whisper+Parakeet batch pipeline (signals 1–3 built in) →
model tournament (MarshLair, after the E: reshuffle finishes — box is busy)
→ signal 4 wired with the winner → review dashboard → then CRUD (Phase 2B
Step 3, explicitly next per Lara).

## Amendments (Lara, 2026-08-24, round 2)

**Court metaphor, to keep roles straight:** YouTube/Whisper/Parakeet are
WITNESSES (independent transcripts; independence matters, brilliance doesn't).
The text-LLM is the JUDGE (never transcribes; reads conflicting testimony +
context and rules). An audio-capable LLM is the APPELLATE JUDGE (re-listens to
the actual disputed clip when text-jurors deadlock). Lara is the supreme court.

**Dashboard additions:** playback speed toggle (IFrame setPlaybackRate,
0.25x–2x) and an A–B section loop (timer on getCurrentTime → seekTo(start))
per flagged span — looping dog-chaos at 0.75x is how humans win.

**Style card for the judge:** a validated "how Posa talks" doc in the
adjudicator packet — speech patterns, domain lexicons (fishing incl.
real-but-odd terms e.g. "steel eater"; camping/bushcraft; dog-directed
speech), and the explicit instruction that HE MAKES PUNS AND SINGS —
implausible is not evidence of error (the anti-crap-pie inoculation).
Seeded from validated sections + Lara's descriptions; grows with validation.

**Audio bracket in the tournament:** local audio-multimodal models that fit
16 GB (Voxtral, Qwen2-Audio/Qwen2.5-Omni, Phi-4-multimodal, Gemma 3n) compete
on the same blind passages WITH the audio clips. Winner becomes the appellate
tier: flagged span → judge rules on text → deadlock → audio judge re-listens
→ still unsure → human, with speed/loop controls waiting.

## Tournament protocol: the adjudicator matrix (Lara, 2026-08-24, round 3)

Not a single-winner bake-off — a full configuration matrix over the three
human-validated passages (ASR_SHOWDOWN §7 ground truth, sealed from all
contestants). Dimensions:

- **Adjudicator**: each viable local text model (all ollama stores +
  marshlair-chat stack) · each audio-capable model (audio bracket) ·
  optionally one cheap Claude tier as ceiling reference.
- **Witness set**: Whisper-only · Whisper+YouTube · Whisper+YouTube+Parakeet
  (does the third witness actually help the judge?).
- **Packet ablations**: ± style card · ± entity lexicon · ± disagreement
  flags (vs raw transcript) · audio bracket: ± the actual clip.
- **Passage**: a (pun) · b (nickname+counts) · c (dog chaos).

Per-cell metrics: WER delta vs raw Whisper · name recovery · pun preservation
· false-correction rate (heavily penalized) · escalation quality (flags the
right spans as beyond-its-pay-grade). Output: a results grid + the chosen
production config (model + packet + witness set), with the runner-up config
recorded as fallback. Runs on MarshLair after the E: reshuffle completes;
local models make the whole matrix ~free, just GPU-time.
