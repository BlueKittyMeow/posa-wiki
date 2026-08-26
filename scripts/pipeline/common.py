"""Shared plumbing for the transcript pipeline: ledgers, hosts, transfers.

Everything the three stage scripts have in common lives here.  The design
constraints come straight from the house rules:

* **No deletes.**  Nothing in this pipeline removes a file.  Scratch WAVs on
  Factotum and on MarshLair reuse one fixed filename each and are simply
  overwritten by the next video, so the working set never grows and nothing
  ever has to be cleaned up.
* **Never hold a long SSH session.**  MarshLair's sshd resets long-lived
  connections and WSL kills a session's processes when ``wsl.exe`` exits, so
  the GPU work runs in a ``systemd-run`` unit inside WSL and this side polls it
  with short reconnecting calls.
* **scp/rsync cannot parse ``Blue Kitty``.**  Transfers to MarshLair go over
  ``sftp`` (which can) or over an ``ssh ... wsl dd`` pipe.
* **Ledgers are append-only JSONL.**  A crash mid-write loses at most the line
  being written, and replaying the file gives the current state, so every stage
  is resumable by construction.
"""

from __future__ import annotations

import json
import os
import shlex
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterable, List, Optional

REPO_ROOT = Path(__file__).resolve().parents[2]

# --------------------------------------------------------------------------
# hosts
# --------------------------------------------------------------------------

FACTOTUM = os.environ.get("POSA_FACTOTUM", "bluekitty@192.168.1.201")
MARSHLAIR = os.environ.get("POSA_MARSHLAIR", "Blue Kitty@192.168.1.156")

ARCHIVE_DIR = os.environ.get("POSA_ARCHIVE_DIR", "/mnt/media6t/archive/posa")
WHISPER_DIR = f"{ARCHIVE_DIR}/transcripts_whisper"
VERDICTS_DIR = f"{ARCHIVE_DIR}/transcripts_verdicts"
#: Never /tmp on the Pi -- it is a 4 GB tmpfs (CLAUDE.md).
STAGING_WAV = os.environ.get("POSA_STAGING_WAV",
                             "/mnt/media6t/staging/posa_pipeline_current.wav")
FACTOTUM_DB = os.environ.get("POSA_FACTOTUM_DB", "/srv/posa-wiki/posa_wiki.db")

#: Inside the WSL Ubuntu distro on MarshLair.
MARSH_WORKDIR = "/home/bluekitty/posa_asr"
MARSH_UNIT = "posa-whisper"

# --------------------------------------------------------------------------
# local paths (all gitignored)
# --------------------------------------------------------------------------

PIPELINE_DIR = Path(os.environ.get("POSA_PIPELINE_DIR",
                                   str(REPO_ROOT / "data" / "pipeline")))
CACHE_DIR = PIPELINE_DIR / "cache"
LOG_DIR = PIPELINE_DIR / "logs"


def ensure_dirs() -> None:
    for path in (PIPELINE_DIR, CACHE_DIR, LOG_DIR):
        path.mkdir(parents=True, exist_ok=True)


def now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def log(message: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {message}", flush=True)


# --------------------------------------------------------------------------
# ledger
# --------------------------------------------------------------------------

class Ledger:
    """Append-only JSONL keyed by ``video_id``; last line per key wins."""

    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def read(self) -> Dict[str, dict]:
        state: Dict[str, dict] = {}
        if not self.path.exists():
            return state
        with self.path.open("r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                except ValueError:
                    continue  # a torn final line from a crash; ignore it
                key = record.get("video_id")
                if key:
                    state[key] = record
        return state

    def append(self, record: dict) -> dict:
        record = dict(record)
        record.setdefault("at", now())
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, sort_keys=True) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        return record

    def done_ids(self, status: str = "ok") -> set:
        return {vid for vid, rec in self.read().items()
                if rec.get("status") == status}


# --------------------------------------------------------------------------
# remote execution
# --------------------------------------------------------------------------

class RemoteError(RuntimeError):
    pass


def _run(argv: List[str], timeout: int, stdin=None, capture_binary=False):
    return subprocess.run(argv, input=stdin,
                          capture_output=True, timeout=timeout,
                          text=not capture_binary)


def ssh(host: str, command: str, timeout: int = 120, check: bool = True,
        stdin: Optional[bytes] = None):
    """Run ``command`` on ``host``.  Returns the CompletedProcess."""
    argv = ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=15", host, command]
    if stdin is not None:
        result = subprocess.run(argv, input=stdin, capture_output=True,
                                timeout=timeout)
        stdout = result.stdout.decode("utf-8", "replace")
        stderr = result.stderr.decode("utf-8", "replace")
    else:
        result = subprocess.run(argv, capture_output=True, text=True,
                                timeout=timeout)
        stdout, stderr = result.stdout, result.stderr
    if check and result.returncode != 0:
        raise RemoteError(f"{host}: {command[:120]!r} exited "
                          f"{result.returncode}: {stderr[:400]}")
    return result.returncode, stdout, stderr


def factotum(command: str, **kwargs):
    return ssh(FACTOTUM, command, **kwargs)


def wsl(script: str, timeout: int = 180, check: bool = True):
    """Run a bash *script* inside MarshLair's WSL via heredoc-stdin.

    The command line stays free of shell operators (CLAUDE.md: everything goes
    through ``cmd.exe`` first, which mangles pipes, redirects and nested
    quotes); the script itself arrives on stdin where nothing touches it.
    """
    argv = ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=15", MARSHLAIR,
            "wsl -d Ubuntu -u bluekitty bash"]
    result = subprocess.run(argv, input=script, capture_output=True,
                            text=True, timeout=timeout)
    if check and result.returncode != 0:
        raise RemoteError(f"WSL script exited {result.returncode}: "
                          f"{result.stderr[:400]}")
    return result.returncode, result.stdout, result.stderr


def marshlair_health() -> int:
    """Return GPU MiB in use; raises if the box is unreachable.

    ~556 MiB (up to ~1.5 GB with the chat stack resident) is the normal
    baseline on this box -- it is not a leak and nothing should be killed
    over it.
    """
    _rc, out, _err = ssh(MARSHLAIR,
                         "nvidia-smi --query-gpu=memory.used "
                         "--format=csv,noheader,nounits", timeout=60)
    try:
        return int(out.strip().splitlines()[0])
    except (ValueError, IndexError):
        raise RemoteError(f"unreadable nvidia-smi output: {out[:200]!r}")


# --------------------------------------------------------------------------
# transfers
# --------------------------------------------------------------------------

def scp_from_factotum(remote_path: str, local_path, timeout: int = 1800) -> None:
    local_path = Path(local_path)
    local_path.parent.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(
        ["scp", "-o", "BatchMode=yes", "-o", "ConnectTimeout=15",
         f"{FACTOTUM}:{remote_path}", str(local_path)],
        capture_output=True, text=True, timeout=timeout)
    if result.returncode != 0:
        raise RemoteError(f"scp from Factotum failed: {result.stderr[:400]}")


def scp_to_factotum(local_path, remote_path: str, timeout: int = 1800) -> None:
    result = subprocess.run(
        ["scp", "-o", "BatchMode=yes", "-o", "ConnectTimeout=15",
         str(local_path), f"{FACTOTUM}:{remote_path}"],
        capture_output=True, text=True, timeout=timeout)
    if result.returncode != 0:
        raise RemoteError(f"scp to Factotum failed: {result.stderr[:400]}")


def push_to_wsl(local_path, remote_path: str, timeout: int = 3600) -> None:
    """Stream a local file into MarshLair's WSL filesystem.

    ``scp``/``rsync`` cannot parse the space in ``Blue Kitty`` and Windows
    ``sftp`` would land the file on the near-full C: drive, so the bytes go
    over ssh stdin straight into ``dd`` inside WSL.  The remote command line
    carries no shell operators, so ``cmd.exe`` passes it through intact.
    """
    argv = ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=15", MARSHLAIR,
            f"wsl -d Ubuntu -u bluekitty dd of={remote_path} bs=1M status=none"]
    with open(local_path, "rb") as handle:
        result = subprocess.run(argv, stdin=handle, capture_output=True,
                                timeout=timeout)
    if result.returncode != 0:
        raise RemoteError("push_to_wsl failed: "
                          + result.stderr.decode("utf-8", "replace")[:400])


def pull_text_from_wsl(remote_path: str, timeout: int = 600) -> str:
    """Read a text file out of WSL (no operators on the command line)."""
    argv = ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=15", MARSHLAIR,
            f"wsl -d Ubuntu -u bluekitty cat {remote_path}"]
    result = subprocess.run(argv, capture_output=True, text=True, timeout=timeout)
    if result.returncode != 0:
        raise RemoteError("pull_text_from_wsl failed: " + result.stderr[:400])
    return result.stdout


# --------------------------------------------------------------------------
# archive discovery
# --------------------------------------------------------------------------

MEDIA_EXTENSIONS = (".mp4", ".mkv", ".webm", ".m4v", ".mov")


def archive_media(archive_dir: str = ARCHIVE_DIR) -> Dict[str, str]:
    """``{video_id: absolute media path}`` for everything in the archive.

    The video id is the last ``[...]`` group in the filename, exactly as
    ``scripts/ingest_transcripts.extract_video_id`` reads it.
    """
    from scripts.ingest_transcripts import extract_video_id

    names = " -o ".join(f"-name '*{ext}'" for ext in MEDIA_EXTENSIONS)
    _rc, out, _err = factotum(
        f"find {shlex.quote(archive_dir)} -type f \\( {names} \\) -print",
        timeout=300)
    found: Dict[str, str] = {}
    for line in out.splitlines():
        line = line.strip()
        if not line:
            continue
        video_id = extract_video_id(os.path.basename(line))
        if video_id:
            found.setdefault(video_id, line)
    return dict(sorted(found.items()))


def factotum_query(sql: str, params: Iterable = (), db: str = FACTOTUM_DB) -> List[list]:
    """Run a read-only query on Factotum's wiki DB and return rows as lists.

    The query and its parameters travel as base64'd JSON so no quoting ever
    reaches a shell.
    """
    import base64

    payload = base64.b64encode(
        json.dumps({"sql": sql, "params": list(params), "db": db}).encode()
    ).decode()
    script = (
        "import base64, json, sqlite3, sys\n"
        f"job = json.loads(base64.b64decode('{payload}'))\n"
        "conn = sqlite3.connect('file:' + job['db'] + '?mode=ro', uri=True)\n"
        "rows = [list(r) for r in conn.execute(job['sql'], job['params'])]\n"
        "sys.stdout.write(json.dumps(rows))\n"
    )
    encoded = base64.b64encode(script.encode()).decode()
    _rc, out, _err = factotum(
        f"python3 -c \"import base64,sys;exec(base64.b64decode('{encoded}'))\"",
        timeout=300)
    return json.loads(out or "[]")
