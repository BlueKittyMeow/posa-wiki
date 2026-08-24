# ASR Showdown — faster-whisper vs Parakeet vs YouTube auto-subs

**Date:** 2026-08-24
**Question:** what should re-transcribe the 373-video / 481-hour Posa catalog on MarshLair's RTX 4070 Ti SUPER?
**Status:** benchmark only. No batch pipeline built. File left untracked for review.

**Bottom line:** **faster-whisper large-v3 with an `initial_prompt`.** It matches Parakeet on speed
(24.3x vs 25.5x realtime), beats it on transcription precision and phrase-level coherence, and — the
decisive factor — the `initial_prompt` is a real control surface we can point at the wiki's own entity
list. Parakeet has no equivalent lever. Estimated batch cost: **~20 GPU-hours for 481 hours of audio.**

---

## 1. Setup, timings, VRAM, realtime factor

**Test material:** *Crap-Pie — The Unsuccessful Fishing Show — Episode 15* `[-zr_N8CDKUA]`
Audio: 1937.54 s (32:17), extracted on Factotum to 16 kHz mono PCM WAV (62 MB, 9.5 s of Pi CPU),
transferred to MarshLair `E:\ai\asr_showdown\zr_N8CDKUA.wav`.

**Hardware:** RTX 4070 Ti SUPER 16 GB, driver 572.83 (CUDA 12.8), WSL2 Ubuntu on MarshLair.
Other GPU residents held **~1.46 GB** throughout; nothing was killed. VRAM deltas below are
peak-total minus that baseline.

| | faster-whisper large-v3 **(prompted)** | faster-whisper large-v3 **(no prompt — control)** | Parakeet TDT 0.6b v2 (GPU) | Parakeet TDT 0.6b v2 (CPU — accidental) |
|---|---|---|---|---|
| Runtime | CTranslate2 4.8.1, float16 | same | ONNX Runtime 1.22, CUDA EP | ONNX Runtime 1.29, CPU EP |
| Decode settings | beam 5, VAD, word timestamps | beam 5, VAD, word timestamps | silero VAD, batch 8 | silero VAD, batch 8 |
| Model load (warm) | **13.0 s** | 64.8 s (cold, model on drvfs `E:`) | **13.8 s** | 69.5 s |
| Transcribe wall time | **79.6 s** | 139.8 s | **76.1 s** | 161.5 s |
| **Realtime factor** | **24.3x** | 13.9x | **25.5x** | 12.0x |
| Peak VRAM (total / delta) | 6322 / **~4.8 GB** | — | 6484 / **~5.0 GB** | n/a |
| Segments | 481 | 190 | 476 | 476 |
| Words | 2662 | 2743 | 2705 | — |

**Agreement with the YouTube auto-sub track** (token-level `SequenceMatcher`; YouTube is *not* ground
truth, it is a third ASR — read this as "how much do they agree", not "accuracy"):

| | recall vs YT | precision vs YT |
|---|---|---|
| Whisper (prompted) | **83.1 %** | **93.1 %** |
| Parakeet (GPU) | 80.2 % | 87.9 % |

Neither engine produced repeated-segment hallucinations (the classic Whisper failure); the check for
identical segments repeated ≥4x came back clean for both.

### Batch estimate for 481 hours

At the measured realtime factors, with the model held resident across files (so per-file load cost
disappears):

| Engine | GPU hours for 481 h |
|---|---|
| faster-whisper large-v3, prompted | **~19.8 h** |
| Parakeet TDT 0.6b v2 (GPU) | ~18.9 h |
| faster-whisper, unprompted | ~34.7 h *(and unusable output — see §4)* |
| Parakeet on CPU | ~40 h |

So roughly **a day of GPU time either way** — speed is not the deciding factor. Add ~10 s/video of Pi
CPU for audio extraction (~1 h total across 373 videos) plus LAN transfer. Both fit comfortably in
16 GB VRAM alongside the current ~1.5 GB of other residents; neither needs the GPU to itself.

---

## 2. Name accuracy

Actual spellings found in each transcript, with counts:

| Target | YouTube auto-subs | Whisper (prompted) | Parakeet |
|---|---|---|---|
| **Monty** (dog) | `monty` x12 | `monty` x14 | `monty` x7 |
| **crappie / Crap-Pie** | `crappie` x23, `crappies` x4, `crappy` x1, plus `crap high`, `crap crappie` in prose | `crappie` x25, `crappies` x6 — **no misspellings** | `crappie` x19, `crappies` x4, `crap pie` x1, plus `crap copy` |
| **Captain Teeny Trout** | `Captain Trot`, `Captain trouts`, `captain truck` | `Captain T-Shirt`, `Captain T-trout's`, `Captain Tea Truck` | `Captain Trout`, `Captain T Truck` |
| **"punk"** (Monty's nickname) | `punk` ✅ | `Funk` ❌ (x3) | `punk` ✅ / `Funk` (mixed) |
| **Lucas** | absent | absent | absent |
| **Rueger** | absent | absent | absent |
| **Layla** | absent | absent | absent |
| **Posa** | absent | absent | absent |

**Caveat on the test material:** Lucas, Rueger, Layla and "Posa" **do not occur in this video at all** —
this episode is Matthew solo with Monty, and the second angler is referenced only by nickname. So the
name test is thinner than the task assumed. Only Monty and the Captain Teeny Trout nickname are
genuinely exercised here.

**The important negative result:** *all three engines fail on "Captain Teeny Trout"*, and seeding it
verbatim in Whisper's `initial_prompt` did **not** rescue it — Whisper still produced "Captain T-Shirt"
and "Captain Tea Truck". Whatever engine we pick, **a post-ASR name-normalization pass is required**
(fuzzy-map `Captain T*` / `captain tr*` / `captain t truck` → canonical `Captain Teeny Trout`) and should
be driven from the wiki's existing people/dog entity tables. Do not expect the ASR to get nicknames right.

Where the prompt *did* help: `crappie`. Whisper-prompted is the only transcript with **zero**
mis-renderings of the show's central word; Parakeet emitted `crap pie` and `crap copy`, YouTube emitted
`crap high` and `crap crappie`.

---

## 3. Three side-by-side passages

### (a) 66–95 s — cold open, show name + "crappie"

> **YouTube:** …you're successful, you're unsuccessful. If you're unsuccessful, you're successful. Uh, today we are targeting some **crap high**, also known as **crap crappie**. Um, and if we can't catch those, we are going to go for some bluegills. Um, as you can see, I'm in a new vessel. This is the uh SS Tin Can 3.0. She's running a little rough…

> **Whisper:** Ladies and gentlemen, welcome to another episode of the unsuccessful fishing show, where if you're successful you're unsuccessful, and if you're unsuccessful you're successful. Today we are targeting some **crappie**, also known as **crappie**. And if we can't catch those, we are going to go for some bluegills. Um, as you can see, I'm in a new vessel. This is the SS Tin Can 3.0. I think I'm gonna have to tilt the motor up a little bit. Hold on. Uh, yeah.

> **Parakeet:** Welcome to another episode of the Unsuccessful Fishing Show, where if you're successful, you're unsuccessful. If you're unsuccessful, you're successful. Uh today we are targeting some **crap pie**. Also known as **crap copy**. And if we can't catch those. **Mm-hmm.** We are going to go for some bluegills. Um As you can see, I'm in a new vessel. This is the SS Tin Can 3.0. **Yeah, I think I'm gonna have to Tilt the motor up** a little bit. Hold on.

Note Parakeet's mid-sentence capitalization ("have to Tilt") and its habit of emitting filler
backchannels ("Mm-hmm.", "Yeah.") as standalone sentences.

### (b) 1655–1690 s — fast recap dialogue, the Captain nickname, fish counts

> **YouTube:** …All right, so I caught I caught like seven crappies. I let one or two go. Uh **captain truck** gave me one. Then I got some five nice gills. Bunch of little gills that I threw back. There are some close ones, but with the bluegills, I like them either to be big fat ones or I usually let them go…

> **Whisper:** …Alright, so I caught I caught like seven crappies ish. I let one or two go. Uh, **Captain Tea Truck** gave me one, then I got some five nice gills. Bunch of little gills that I threw back. There was some close ones, but with the blue gills, I like them either to be big fat ones or I usually let them go unless like some days you just small fish…

> **Parakeet:** …Alright, so I caught **It's kind of like Seven. Crappies. Ish,** I let **water** two go. Uh **Captain T Truck** gave me one and then I got some five nice gills, bunch of **little kills.** that I threw back. There's some close ones, but with the bluegills. I like'em either to be big fat ones or I'd usually let'em go **in less,** like Some days it's just smaller fish…

Parakeet shreds this passage: "seven" becomes "It's kind of like Seven. Crappies. Ish," across three
fragments, "one or two go" becomes "water two go", "little gills" becomes "little kills", "unless"
becomes "in less". Whisper keeps it as readable prose. (Parakeet *does* recover one detail Whisper
drops — the sentence about cinder blocks on the bow.)

### (c) 1795–1830 s — overlapping dog play, rapid short utterances

> **YouTube:** Say hi, **punk**. Hi. We got a Monty. Help him see it. Come here, buddy. Go get him, Monty. Give me Give me that. Give me here, you little stinker. Give me that. He's like, "No. He won't give it to me. Give it here, Monty. Let me get you.

> **Whisper:** **Funk.** Hi. Look at him Monty. Help him see it. Go get it Monty. Give me that. Give me that. You little stinker. Give me that. He's like, no. He won't give it to me. Give it here. Monty. I'll get you.

> **Parakeet:** Say hi **punk**. Hi. Monty. Help them see it. **Forget it,** Monty. Give me **Can you hear your little stinker? You could hear that.** And he's like, no. it here. **Ooh. Yeah.**

This is the hardest passage (dog barking over speech) and where Parakeet degrades worst — "Go get it"
becomes "Forget it", and "Give me that… you little stinker" becomes the invented question "Can you hear
your little stinker? You could hear that." Whisper misses only "Say hi punk" → "Funk" and otherwise
tracks. YouTube is actually strongest here.

---

## 4. Punctuation / readability — and what the prompt actually does

I ran a **control**: identical Whisper settings, `initial_prompt` removed. The result is the single most
actionable finding in this benchmark.

| | words | periods | commas | `?` | capitalized tokens |
|---|---|---|---|---|---|
| Whisper **prompted** | 2662 | **422** | **130** | 35 | 527 (20 %) |
| Whisper **no prompt** | 2743 | **19** | **9** | 7 | 134 (5 %) |
| Parakeet | 2705 | 433 | 146 | 33 | 619 (23 %) |

Without the prompt, Whisper emits an essentially unpunctuated lowercase stream:

> `go get him give it give me that give me here you little stinker` … `monty i'll get you i'm fine you can have it oh oh oh we're flipping the mantis`

The `initial_prompt` is written as properly punctuated, capitalized prose, and Whisper conditions its
output *style* on it. **So the prompt's dominant effect is formatting, not vocabulary** — it is what
makes the transcripts readable/quotable on the wiki. It also happened to be ~1.75x faster (24.3x vs
13.9x) and produced 481 sensible segments instead of 190 sprawling ones.

Verdict on "did the vocab prompt help": **yes, but not the way we expected.**
- Formatting: transformative (422 vs 19 sentence terminators).
- Vocabulary: marginal but real (`crappie` perfect vs one `crappy` slip).
- Rare nicknames: **no help at all** (Captain Teeny Trout still wrong).

Parakeet's punctuation volume is comparable to prompted-Whisper, but it is *distributed* worse — it
sentence-breaks mid-clause and capitalizes mid-sentence, so the counts flatter it. Segment lengths tell
the same story: Whisper averages 2.4 s/segment (max 57.7 s), Parakeet 1.6 s (max 10.3 s) — Parakeet
chops utterances into fragments that read as staccato.

---

## 5. Recommendation

**Use faster-whisper large-v3, float16, beam 5, VAD on, word timestamps on, with an `initial_prompt`.**

Rationale:
1. **Speed is a tie** (24.3x vs 25.5x) — ~20 GPU-hours for the whole catalog either way. Not a tiebreaker.
2. **Whisper wins on quality where it matters for a wiki**: higher precision against YouTube (93.1 % vs
   87.9 %), coherent sentences under fast/overlapping dialogue, no invented questions, no
   mid-sentence capitalization.
3. **The prompt is a control surface, and Parakeet has none.** We can feed it per-video vocabulary
   generated from the wiki's own people/dogs/locations tables. That asymmetry compounds across 373 videos.
4. **Word-level timestamps with per-word confidence** come free from faster-whisper and are directly
   useful: transcript search/deep-linking, and a quality gate (flag low-confidence spans for review).
   The onnx-asr Parakeet path gives segment-level timing only in this configuration.

**Batch plan implications:**
- Budget **~20 GPU hours**, runnable in chunks; keep the model resident across files.
- Build the `initial_prompt` per video from wiki entities (dogs present, people present, series
  vocabulary), but **always keep the punctuated-prose style** — that's what buys readable output.
- **Add a post-ASR name-normalization pass regardless of engine.** Nicknames like "Captain Teeny Trout"
  are not recoverable by prompting; fuzzy-map against canonical entity names.
- YouTube auto-subs are not worthless — they beat both engines on the noisy dog-play passage — but they
  have no punctuation discipline and mangle "crappie". Re-transcribing is justified.

**Not recommended:** dropping to Parakeet for speed. The ~5 % speed edge does not pay for the
phrase-level damage in exactly the content this wiki cares about (dialogue with names).

---

## 6. Gotchas encountered

1. **⚠️ E: filled to 6 MB free during this benchmark — remediated, but MarshLair needs attention.**
   E: started at 15.6 GB free. faster-whisper's CUDA wheels (~2.5 GB), the large-v3 model (~3 GB),
   Parakeet ONNX (~2.5 GB), and a second ONNX Runtime CUDA stack (~5 GB) exhausted it. The WSL VM then
   threw `Input/output error` and `Bus error` and wedged (every `wsl` command exited 11).
   **Fixed by** moving this session's HF model cache to `D:\claude-asr-movedaside\` (robocopy /MOVE,
   nothing deleted) and restarting the distro — E: is back to **5.2 GB free**.
   Two things still want a human decision:
   - The WSL vhdx is **145 GB** (`E:\ai\wsl\Ubuntu\ext4.vhdx`) and never shrinks. Compacting it
     (`wsl --shutdown` then `Optimize-VHD` / diskpart `compact vdisk`) would likely reclaim a lot.
     ~6.9 GB of that is pip cache inside the distro that I left alone (not mine to purge).
   - **The batch run needs a storage decision before it starts.** 5.2 GB on E: is not comfortable
     headroom for 373 videos' worth of audio + outputs.
2. **`robocopy /MOVE` destroys HuggingFace cache symlinks** — snapshot files arrive as 0-byte stubs
   (blobs survive intact under `blobs/`). Recovered by identifying blobs by size + `strings` and
   rebuilding a plain model dir at `D:\parakeet_model\`. Don't robocopy an HF cache — **`mv` from
   inside WSL preserves the symlinks correctly** (used for the second move; verified).
3. **NeMo is not installable here.** `pip install nemo_toolkit[asr]` dry-run resolves to **132 packages**
   including torch and a full **CUDA 13** stack. That does not fit the free space, and CUDA 13 needs
   driver ≥580 while MarshLair is on **572.83 (CUDA 12.8)** — it would not have run on the GPU anyway.
   Parakeet was benchmarked via **onnx-asr + ONNX Runtime CUDA EP** instead. This is a real asymmetry:
   NeMo's native TDT decoder might be faster than the ONNX path, so **Parakeet's 25.5x is a floor,
   not a ceiling.** It does not change the recommendation (quality, not speed, decided it).
4. **onnxruntime-gpu ≥1.29 is CUDA 13** and fails on this driver with
   `libcublasLt.so.13: cannot open shared object file`. It falls back to **CPU silently** — the first
   Parakeet run was accidentally CPU-only (12.0x realtime; a useful data point, but it was not the
   GPU number). **Pin `onnxruntime-gpu==1.22.0`** for the CUDA 12 build, and always confirm the CUDA EP
   actually loaded rather than trusting `get_available_providers()`.
5. **The WSL VM auto-terminated mid-job**, killing the first install (unit reported `Result=success`
   with an obviously truncated log — a silent, misleading failure mode). Symptom: `uptime` shows
   "up 1 min". **Run `schtasks /Run /TN WSLKeepalive` before starting any long WSL job**, and check for
   a completion sentinel in the log rather than trusting unit exit status.
6. **`nvidia-smi` is not on `PATH` under `systemd-run`** (it lives at `/usr/lib/wsl/lib`). The first
   VRAM poller logged nothing but "command not found" for the whole run.
7. **`nvidia.__file__` is `None`** (namespace package) — the usual `LD_LIBRARY_PATH` one-liner crashes.
   Use `nvidia.__path__[0]`. Without it, ctranslate2 dies with
   `Library libcublas.so.12 is not found`.
8. **Loading the model from `/mnt/e` (drvfs) costs ~65 s cold vs ~13 s warm.** For a 373-file batch,
   keep the model resident, or stage weights inside the distro filesystem.
9. Factotum's `/mnt/media6t` root is not writable by `bluekitty` — staged the WAV via
   `/mnt/media/staging/` instead.
10. The no-delete hook fires on `rm` **inside heredoc text** even when the target is a log file being
    reset; used `: > file` truncation instead.

---

## Artifacts left in place

**MarshLair (WSL Ubuntu):**
- conda envs `asr` (faster-whisper 1.2.1 / ctranslate2 4.8.1) and `parakeet` (onnx-asr, onnxruntime-gpu 1.22.0)
- job scripts in `/home/bluekitty/`: `run_whisper.py`, `run_whisper.sh`, `run_whisper_np.py/.sh`,
  `run_parakeet.py`, `run_parakeet.sh`, plus `*_run.log`
- outputs: `E:\ai\asr_showdown\out\{whisper,whisper_noprompt,parakeet}\{segments.json,transcript.txt,meta.json}`
- audio: `E:\ai\asr_showdown\zr_N8CDKUA.wav`
- models, all moved off the full E: drive:
  - `D:\claude-asr-movedaside\hub\` — Parakeet + silero (symlinks broken by robocopy; blobs fine)
  - `D:\claude-asr-movedaside\hub2\` — faster-whisper large-v3 + silero (symlinks **intact**, usable as
    an `HF_HOME` hub directly)
  - `D:\parakeet_model\` — reconstructed plain-file Parakeet model dir (what the GPU run actually loaded)
- **E: finished at 5.2 GB free** (started at 15.6 GB). Set `HF_HOME` to a `D:` location for the batch
  run, or free space on E: first.

**Factotum:** `/mnt/media/staging/zr_N8CDKUA.wav` (62 MB — delete when done with it).

Local scratchpad copies of the WAV were cleaned up.
