#!/usr/bin/env python3
"""Audio bracket (appellate judge) — runs INSIDE WSL on MarshLair.

Entrants are limited to models already fully present in /mnt/d/ai/hf_cache.
Each receives the same sealed packet as the text judges, plus (optionally) the
actual disputed clip.

Witness set is **W+YT** — the text bracket found Parakeet actively harmful
(fix rate 46% W+YT vs 26% W+YT+P), so the appellate tier inherits that finding.

Sizing. Every entrant is ~16-17 GB in fp16 against ~15.4 GB of free VRAM, and
the WSL VM has only 8 GB of RAM (the MCE-crash cap in CLAUDE.md), so fp16 +
CPU offload is both slow (weights stream over PCIe every token) and fragile
(a consolidated 16 GB safetensors cannot even be mmap'd). Default is therefore
bitsandbytes **8-bit**, which puts a 7-8B entrant at ~9-10 GB fully resident on
the GPU. `--quant 4bit|none` overrides. ONE model at a time; the process exits
(freeing VRAM) between entrants.

Clips are 30 s windows (clips30/) — every audio encoder here is Whisper-derived
and truncates at 30 s, so a longer clip silently drops its tail.

Schema discipline: a `correct` verdict that carries no `correction` states
nothing. Such a cell gets ONE repair re-prompt; anything still missing a
correction is rewritten to `escalate` before scoring.

Usage (in the lingbot-map conda env):
  audio_judge.py <packetdir> <clipdir> <outdir> <entrant> [--no-audio] [--quant X]
    entrant: qwen2-audio | flamingo | moss-thinking | moss-instruct
"""
import json, os, sys, time
from pathlib import Path

os.environ.setdefault("HF_HOME", "/mnt/d/ai/hf_cache")

# label -> (repo, trust_remote_code, family)
ENTRANTS = {
    "qwen2-audio":   ("Qwen/Qwen2-Audio-7B-Instruct", False, "qwen2audio"),
    "flamingo":      ("nvidia/audio-flamingo-3-hf",   False, "af3"),
    "moss-thinking": ("OpenMOSS-Team/MOSS-Audio-8B-Thinking", True, "moss"),
    "moss-instruct": ("OpenMOSS-Team/MOSS-Audio-8B-Instruct", True, "moss"),
}

WITNESS_SET, WS_KEY = "W+YT", "W_YT"
MAX_NEW_TOKENS = 800
CELL_BUDGET_S = 1500          # hard wall-clock stop per cell
PASSAGES = ["a", "b", "c"]

REPAIR = """Your previous answer used the verdict "correct" for one or more spans
without supplying a "correction". A "correct" verdict with no correction states
nothing and will be discarded.

Re-emit the FULL JSON array. Every element with "verdict": "correct" must carry
a "correction" holding the full corrected sentence. If you cannot say what was
actually said, change that element's verdict to "escalate".

JSON array and nothing else."""


def needs_repair(rulings):
    return [r for r in (rulings or [])
            if isinstance(r, dict)
            and str(r.get("verdict", "")).lower() == "correct"
            and not (isinstance(r.get("correction"), str) and r["correction"].strip())]


def demote(rulings):
    """Rewrite still-uncorrected 'correct' verdicts to 'escalate'."""
    n = 0
    for r in needs_repair(rulings):
        r["verdict"] = "escalate"
        r["_demoted"] = "correct-without-correction"
        n += 1
    return n


def main():
    packetdir, clipdir, outdir = sys.argv[1], sys.argv[2], sys.argv[3]
    argv = sys.argv[4:]
    entrant = argv[0] if argv and not argv[0].startswith("-") else "qwen2-audio"
    model_id, remote, family = ENTRANTS[entrant]
    use_audio = "--no-audio" not in sys.argv
    quant = "8bit"
    if "--quant" in sys.argv:
        quant = sys.argv[sys.argv.index("--quant") + 1]
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from judge_prompt import build_prompt
    from runner import parse_rulings

    import librosa, torch
    from transformers import (AutoProcessor, AutoModel, BitsAndBytesConfig,
                              StoppingCriteria, StoppingCriteriaList)

    class TimeBudget(StoppingCriteria):
        def __init__(self, budget):
            self.deadline = time.time() + budget
            self.tripped = False

        def __call__(self, input_ids, scores, **kw):
            if time.time() > self.deadline:
                self.tripped = True
                return True
            return False

    proc = AutoProcessor.from_pretrained(model_id, trust_remote_code=remote)
    if family == "qwen2audio":
        from transformers import Qwen2AudioForConditionalGeneration as CLS
    elif family == "af3":
        from transformers import AudioFlamingo3ForConditionalGeneration as CLS
    else:
        CLS = AutoModel

    kwargs = dict(dtype=torch.float16, device_map="auto", trust_remote_code=remote)
    if quant == "8bit":
        kwargs["quantization_config"] = BitsAndBytesConfig(load_in_8bit=True)
        kwargs["max_memory"] = {0: "13GiB"}
    elif quant == "4bit":
        kwargs["quantization_config"] = BitsAndBytesConfig(
            load_in_4bit=True, bnb_4bit_quant_type="nf4",
            bnb_4bit_compute_dtype=torch.float16)
        kwargs["max_memory"] = {0: "13GiB"}
    else:
        kwargs["max_memory"] = {0: "12GiB", "cpu": "5GiB"}

    t0 = time.time()
    model = CLS.from_pretrained(model_id, **kwargs)
    model.eval()
    load_s = round(time.time() - t0, 1)
    print(f"{entrant} loaded in {load_s}s (quant={quant})", flush=True)

    sr = getattr(getattr(proc, "feature_extractor", None), "sampling_rate", 16000)
    out = Path(outdir); out.mkdir(parents=True, exist_ok=True)

    def generate(prompt_text, audios, clip):
        """One forward pass. Returns decoded text and whether it timed out."""
        lead = ("The audio above is the disputed clip. Listen to it, "
                "then rule.\n\n")
        if family == "moss":
            # MOSS ships a bespoke processor: it templates the prompt itself and
            # the model wants an explicit audio_input_mask (upstream
            # src/hf_inference.py).
            inputs = dict(proc(text=(lead + prompt_text) if audios else prompt_text,
                               audios=audios or None, return_tensors="pt"))
            inputs["audio_input_mask"] = inputs["input_ids"] == proc.audio_token_id
        else:
            if audios:
                content = [{"type": "audio", "audio_url": str(clip)},
                           {"type": "text", "text": lead + prompt_text}]
            else:
                content = [{"type": "text", "text": prompt_text}]
            conv = [{"role": "user", "content": content}]
            text = proc.apply_chat_template(conv, add_generation_prompt=True,
                                            tokenize=False)
            kw = dict(text=text, return_tensors="pt", padding=True)
            if audios:
                kw.update(audio=audios, sampling_rate=sr)
            inputs = dict(proc(**kw))

        def _mv(v):
            if not hasattr(v, "to"):
                return v
            v = v.to(model.device)
            # Whisper-style feature extractors emit fp32 mels; the model is fp16
            if torch.is_floating_point(v):
                v = v.to(model.dtype)
            return v
        inputs = {k: _mv(v) for k, v in inputs.items()}
        budget = TimeBudget(CELL_BUDGET_S)
        with torch.no_grad():
            gen = model.generate(**inputs, max_new_tokens=MAX_NEW_TOKENS,
                                 do_sample=False, use_cache=True,
                                 stopping_criteria=StoppingCriteriaList([budget]))
        gen = gen[:, inputs["input_ids"].shape[1]:]
        return proc.batch_decode(gen, skip_special_tokens=True)[0], budget.tripped

    for pid in PASSAGES:
        pk = json.loads((Path(packetdir) / f"{pid}__{WS_KEY}.json").read_text())
        prompt = build_prompt(pk, style=True, lex=True, flags=True)
        tag = "withClip" if use_audio else "noClip"
        key = f"{entrant}__{pid}__{WS_KEY}__{tag}"
        if (out / f"{key}.json").exists():
            print("cached", key, flush=True); continue

        rec = {"judge": entrant, "model": model_id, "passage": pid,
               "witness_set": WITNESS_SET, "ablation": tag, "quant": quant,
               "prompt_chars": len(prompt), "load_s": load_s}
        t1 = time.time()
        try:
            clip = Path(clipdir) / f"{pid}.wav"
            audios = [librosa.load(clip, sr=sr)[0]] if use_audio else []
            raw, tripped = generate(prompt, audios, clip)
            rulings, note = parse_rulings(raw)
            rec.update({"raw": raw, "rulings": rulings, "parse_note": note,
                        "timed_out": tripped})

            if needs_repair(rulings):
                rec["repair_attempted"] = True
                raw2, tripped2 = generate(
                    prompt + "\n\n=== YOUR PREVIOUS ANSWER ===\n" + raw
                    + "\n\n=== REPAIR INSTRUCTION ===\n" + REPAIR, audios, clip)
                r2, note2 = parse_rulings(raw2)
                rec.update({"raw_repair": raw2, "parse_note_repair": note2,
                            "timed_out_repair": tripped2})
                if r2 is not None and len(needs_repair(r2)) < len(needs_repair(rulings)):
                    rulings, rec["rulings"] = r2, r2
                    rec["repair_used"] = True
            rec["demoted_to_escalate"] = demote(rulings)
            rec["rulings"] = rulings
        except Exception as e:
            rec.update({"error": f"{type(e).__name__}: {e}"[:600], "rulings": None})
        rec["elapsed"] = round(time.time() - t1, 1)
        (out / f"{key}.json").write_text(json.dumps(rec, indent=2))
        n = "ERR" if rec.get("error") else (
            len(rec["rulings"]) if rec.get("rulings") is not None else "PARSE-FAIL")
        print(f"{key}: {rec['elapsed']}s rulings={n} "
              f"demoted={rec.get('demoted_to_escalate')}"
              f"{'  ' + rec['error'][:150] if rec.get('error') else ''}", flush=True)
    print("AUDIO_BRACKET_DONE", flush=True)


if __name__ == "__main__":
    main()
