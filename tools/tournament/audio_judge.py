#!/usr/bin/env python3
"""Audio bracket (appellate judge) — runs INSIDE WSL on MarshLair.

Qwen2-Audio-7B-Instruct is the only audio-multimodal model fully present in
/mnt/d/ai/hf_cache, so it is the only entrant. It receives the same sealed
packet as the text judges, plus (optionally) the actual disputed clip.

Model is ~16 GB bf16 against ~14.8 GB of free VRAM, so it is loaded with
device_map="auto" and a GPU cap, letting the tail of the model sit on CPU.
One model at a time; the process exits (freeing VRAM) when done.

Usage (in the lingbot-map conda env):
  audio_judge.py <packetdir> <clipdir> <outdir> [--no-audio]
"""
import json, os, sys, time
from pathlib import Path

os.environ.setdefault("HF_HOME", "/mnt/d/ai/hf_cache")

MODEL = "Qwen/Qwen2-Audio-7B-Instruct"


def main():
    packetdir, clipdir, outdir = sys.argv[1], sys.argv[2], sys.argv[3]
    use_audio = "--no-audio" not in sys.argv
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from judge_prompt import build_prompt

    import librosa, torch
    from transformers import AutoProcessor, Qwen2AudioForConditionalGeneration

    proc = AutoProcessor.from_pretrained(MODEL)
    t0 = time.time()
    model = Qwen2AudioForConditionalGeneration.from_pretrained(
        MODEL, dtype=torch.float16, device_map="auto",
        max_memory={0: "12GiB", "cpu": "24GiB"})
    model.eval()
    print(f"model loaded in {time.time()-t0:.1f}s", flush=True)

    out = Path(outdir); out.mkdir(parents=True, exist_ok=True)
    for pid in ["a", "b", "c"]:
        pk = json.loads((Path(packetdir) / f"{pid}__W_YT_P.json").read_text())
        prompt = build_prompt(pk, style=True, lex=True, flags=True)
        tag = "withClip" if use_audio else "noClip"
        key = f"qwen2-audio__{pid}__W_YT_P__{tag}"
        if (out / f"{key}.json").exists():
            print("cached", key); continue

        audios = []
        if use_audio:
            clip = Path(clipdir) / f"{pid}.wav"
            wav, _ = librosa.load(clip, sr=proc.feature_extractor.sampling_rate)
            audios.append(wav)
            content = [{"type": "audio", "audio_url": str(clip)},
                       {"type": "text", "text":
                        "The audio above is the disputed clip. Listen to it, then rule.\n\n"
                        + prompt}]
        else:
            content = [{"type": "text", "text": prompt}]

        conv = [{"role": "user", "content": content}]
        text = proc.apply_chat_template(conv, add_generation_prompt=True, tokenize=False)
        inputs = proc(text=text, audio=audios or None,
                      sampling_rate=proc.feature_extractor.sampling_rate,
                      return_tensors="pt", padding=True)
        inputs = {k: (v.to(model.device) if hasattr(v, "to") else v)
                  for k, v in inputs.items()}
        t1 = time.time()
        with torch.no_grad():
            gen = model.generate(**inputs, max_new_tokens=1200, do_sample=False)
        gen = gen[:, inputs["input_ids"].shape[1]:]
        raw = proc.batch_decode(gen, skip_special_tokens=True)[0]
        rec = {"judge": "qwen2-audio", "model": MODEL, "passage": pid,
               "witness_set": "W+YT+P", "ablation": tag, "raw": raw,
               "elapsed": round(time.time() - t1, 1)}
        (out / f"{key}.json").write_text(json.dumps(rec, indent=2))
        print(f"{key}: {rec['elapsed']}s  {len(raw)} chars", flush=True)
    print("AUDIO_BRACKET_DONE", flush=True)


if __name__ == "__main__":
    main()
