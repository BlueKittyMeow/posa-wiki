#!/usr/bin/env python3
"""Tournament runner — drives local MarshLair models over the ollama HTTP API.

Runs on MysteryOfGlass. Ships only sealed packets; ground truth stays in score.py.

Endpoints:
  default store  http://192.168.1.156:11434   (LAN-bound ollama)
  agent store    http://127.0.0.1:11435       (via `ssh -L 11435:127.0.0.1:11435`)

Discipline: ONE model resident at a time. Every model is explicitly unloaded
(`keep_alive: 0`) before the next is loaded, and VRAM is checked between models.

Usage:
  runner.py screen  <packetdir> <outdir>          # full packet, 3 witness sets? no: full/W+YT+P, 3 passages
  runner.py full    <packetdir> <outdir> M1 M2..  # complete ablation grid for named models
"""
import json, os, re, subprocess, sys, time, urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from judge_prompt import build_prompt, ABLATIONS  # noqa: E402

DEFAULT_STORE = "http://192.168.1.156:11434"
AGENT_STORE = "http://127.0.0.1:11435"

JUDGES = [
    # (label, endpoint, ollama model tag, store)
    ("phi3.5",             DEFAULT_STORE, "phi3.5:latest",                              "default"),
    ("minicpm-v",          DEFAULT_STORE, "minicpm-v:latest",                           "default"),
    ("robody-brainstem",   DEFAULT_STORE, "robody-brainstem:latest",                    "default"),
    ("qwen3.5-9b",         AGENT_STORE,   "qwen3.5:9b",                                 "agent"),
    ("gutenberg-12b",      AGENT_STORE,   "vanilj/mistral-nemo-gutenberg-12b-v2:Q8_0",  "agent"),
    ("mistral-small3.2",   AGENT_STORE,   "mistral-small3.2:24b",                       "agent"),
    ("qwen38-27b-iq3m",    AGENT_STORE,   "marshlair-qwen38-27b-uncensored:iq3_m-text", "agent"),
    ("gemma3-27b-qat",     AGENT_STORE,   "gemma3:27b-it-qat",                          "agent"),
    ("qwen3.5-27b",        AGENT_STORE,   "qwen3.5:27b",                                "agent"),
    ("qwen3.5-35b-a3b",    AGENT_STORE,   "qwen3.5:35b-a3b",                            "agent"),
]
BY_LABEL = {j[0]: j for j in JUDGES}

TIMEOUT = 1200


def ssh(cmd, timeout=60):
    return subprocess.run(
        ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10",
         "Blue Kitty@192.168.1.156", cmd],
        capture_output=True, text=True, timeout=timeout)


def health():
    r = ssh("echo ok")
    if r.returncode != 0 or "ok" not in r.stdout:
        raise RuntimeError(f"MarshLair health check FAILED: {r.stderr[:300]}")
    v = ssh("nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits")
    used = int(v.stdout.strip().splitlines()[0]) if v.returncode == 0 else -1
    return used


def api(endpoint, path, payload, timeout=TIMEOUT):
    req = urllib.request.Request(
        endpoint + path, data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def unload(endpoint, model):
    try:
        api(endpoint, "/api/generate",
            {"model": model, "prompt": "", "keep_alive": 0}, timeout=120)
    except Exception as e:
        print(f"    (unload note: {e})")


def strip_think(t):
    t = re.sub(r"<think>.*?</think>", "", t, flags=re.S | re.I)
    t = re.sub(r"^.*?</think>", "", t, flags=re.S | re.I)
    return t.strip()


def parse_rulings(text):
    """Best-effort extraction of the JSON array of rulings."""
    t = strip_think(text)
    t = re.sub(r"```(?:json)?", "", t)
    # first balanced [...] containing an object
    start = t.find("[")
    while start != -1:
        depth = 0
        for i in range(start, len(t)):
            if t[i] == "[":
                depth += 1
            elif t[i] == "]":
                depth -= 1
                if depth == 0:
                    try:
                        v = json.loads(t[start:i + 1])
                        if isinstance(v, list):
                            return v, None
                    except Exception:
                        pass
                    break
        start = t.find("[", start + 1)
    # fallback: concatenate individual objects
    objs = []
    for m in re.finditer(r"\{[^{}]*\}", t):
        try:
            objs.append(json.loads(m.group()))
        except Exception:
            pass
    if objs:
        return objs, "recovered-objects"
    return None, "unparseable"


def run_cell(endpoint, model, packet, ablation, seed=7):
    prompt = build_prompt(packet, **ABLATIONS[ablation])
    t0 = time.time()
    payload = {
        "model": model, "prompt": prompt, "stream": False, "think": False,
        "keep_alive": "10m",
        "options": {"temperature": 0, "seed": seed, "num_ctx": 8192,
                    "num_predict": 1600},
    }
    try:
        r = api(endpoint, "/api/generate", payload)
        raw = r.get("response", "")
    except Exception as e:
        # some builds reject think:false on non-thinking models
        if "think" in str(e).lower():
            payload.pop("think")
            r = api(endpoint, "/api/generate", payload)
            raw = r.get("response", "")
        else:
            return {"error": str(e)[:400], "elapsed": round(time.time() - t0, 1)}
    rulings, note = parse_rulings(raw)
    return {"raw": raw, "rulings": rulings, "parse_note": note,
            "elapsed": round(time.time() - t0, 1),
            "prompt_chars": len(prompt)}


def load_packets(packetdir):
    d = Path(packetdir)
    return {p.stem: json.loads(p.read_text())
            for p in d.glob("*.json") if p.name != "manifest.json"}


def save(outdir, key, rec):
    out = Path(outdir); out.mkdir(parents=True, exist_ok=True)
    (out / f"{key}.json").write_text(json.dumps(rec, indent=2))


def main():
    mode, packetdir, outdir = sys.argv[1], sys.argv[2], sys.argv[3]
    packets = load_packets(packetdir)
    which = sys.argv[4:] or [j[0] for j in JUDGES]

    if mode == "screen":
        cells = [(pid, "W+YT+P", "full") for pid in ["a", "b", "c"]]
    else:
        cells = [(pid, ws, ab)
                 for pid in ["a", "b", "c"]
                 for ws in ["W", "W+YT", "W+YT+P"]
                 for ab in ["full", "noStyle", "noLex", "noFlags", "bare"]]
        # ablations only vary meaningfully at the full witness set for -flags/-bare;
        # keep the grid but skip duplicate W-only x flags-off combos
        cells = [c for c in cells if not (c[1] == "W" and c[2] in ("noFlags", "bare"))]

    for label in which:
        if label not in BY_LABEL:
            print(f"!! unknown judge {label}"); continue
        _, endpoint, model, store = BY_LABEL[label]
        used = health()
        print(f"\n### {label} ({model}) [{store}]  VRAM before: {used} MiB", flush=True)
        for pid, ws, ab in cells:
            key = f"{label}__{pid}__{ws.replace('+','_')}__{ab}"
            outp = Path(outdir) / f"{key}.json"
            if outp.exists():
                print(f"  - {key} (cached)"); continue
            pk = packets[f"{pid}__{ws.replace('+','_')}"]
            res = run_cell(endpoint, model, pk, ab)
            res.update({"judge": label, "model": model, "passage": pid,
                        "witness_set": ws, "ablation": ab})
            save(outdir, key, res)
            n = len(res.get("rulings") or []) if res.get("rulings") is not None else "PARSE-FAIL"
            print(f"  - {key}: {res.get('elapsed')}s  rulings={n}"
                  f"{'  ERR=' + res['error'][:80] if res.get('error') else ''}", flush=True)
        unload(endpoint, model)
        time.sleep(4)
        print(f"### {label} done. VRAM after unload: {health()} MiB", flush=True)


if __name__ == "__main__":
    main()
