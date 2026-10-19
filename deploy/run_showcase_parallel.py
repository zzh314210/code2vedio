"""Independent background sample jobs with bounded concurrency and durable status.

This is an operator acceptance tool, not part of the public generation API.
Successful rendering never publishes a sample without a separate human review.
"""
from __future__ import annotations

import argparse
import fcntl
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
JOBS = {
    "history_map": ("showcase-history_map-v4", ["deploy/polish_history_showcase.py"]),
    "word_story": ("showcase-word_story-v4", ["deploy/polish_word_showcase.py"]),
    "documentary": ("showcase-documentary-v4", ["deploy/polish_documentary_showcase.py"]),
    "math_visual": ("showcase-math_visual-v6", ["deploy/render_showcase_local.py", "math_visual", "--revision", "v6"]),
    "explainer": ("showcase-explainer-v4", ["deploy/render_showcase_local.py", "explainer", "--revision", "v4", "--resume"]),
}


def process_identity(pid: int) -> str | None:
    try:
        fields = Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()
        return None if fields[0] == "Z" else fields[19]
    except (OSError, IndexError):
        return None


def save(path: Path, value: dict) -> None:
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")
    temporary.replace(path)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--jobs", nargs="+", choices=[*JOBS, 'product'])
    parser.add_argument("--refined-v7", action="store_true")
    parser.add_argument("--max-jobs", type=int, choices=[1, 2], default=2)
    parser.add_argument("--status-dir", type=Path, default=ROOT / ".tmp/showcase-parallel")
    parser.add_argument("--adopt-notes-pid", type=int)
    parser.add_argument("--timeout", type=int, default=5400)
    args = parser.parse_args()
    catalog = {name: (f'showcase-{name}-v7', ['deploy/refine_showcases.py', name]) for name in ['documentary', 'math_visual', 'explainer', 'product']} if args.refined_v7 else JOBS
    selected = args.jobs or list(catalog)
    if any(name not in catalog for name in selected):parser.error('Selected job is not available in this batch')
    output = args.status_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)
    guard = (output / "runner.lock").open("a")
    fcntl.flock(guard, fcntl.LOCK_EX | fcntl.LOCK_NB)
    records = {}
    running = {}
    pending = list(dict.fromkeys(selected))
    for name in pending:
        project, command = catalog[name]
        records[name] = {
            "job": name, "state": "queued", "project": project,
            "command": command, "log": str(output / f"{name}.log"),
        }
    adopted = None
    if args.adopt_notes_pid:
        pid = args.adopt_notes_pid
        identity = process_identity(pid)
        if identity:
            command = Path(f"/proc/{pid}/cmdline").read_bytes().replace(b"\0", b" ").decode()
            expected = 'refine_showcases.py notes' if args.refined_v7 else 'render_showcase_local.py notes --revision v5'
            if expected not in command:
                raise RuntimeError("The adopted process is not the expected notes sample")
            adopted = (pid, identity)
            records["notes"] = {
                "job": "notes", "state": "running", "pid": pid,
                "project": "showcase-notes-v7" if args.refined_v7 else "showcase-notes-v5", "adopted": True,
                "log": str(ROOT / ('.tmp/notes-refinement-v7.log' if args.refined_v7 else '.tmp/showcase-batch-v5/notes.log')),
            }

    def persist() -> None:
        for name, record in records.items():
            save(output / f"{name}.json", record)
        save(output / "status.json", {
            "updated_at": time.time(), "runner_pid": os.getpid(),
            "max_jobs": args.max_jobs, "jobs": list(records.values()),
            "publication": "Every sample requires separate actual-film acceptance.",
        })

    def stop(signum, _frame) -> None:
        raise KeyboardInterrupt(f"Signal {signum}")

    signal.signal(signal.SIGTERM, stop)
    persist()
    try:
        while pending or running or adopted:
            if adopted and process_identity(adopted[0]) != adopted[1]:
                receipt = ROOT / 'video_projects' / records['notes']['project'] / 'showcase_receipt.json'
                complete = receipt.is_file() and json.loads(receipt.read_text()).get("status") == "generated"
                records["notes"].update(state="generated_pending_review" if complete else "needs_fix", ended_at=time.time())
                adopted = None
            for name, (process, log) in list(running.items()):
                code = process.poll()
                record = records[name]
                if code is None:
                    elapsed = time.time() - record["started_at"]
                    if elapsed > args.timeout and not record.get("timeout_at"):
                        record.update(state="stopping_after_timeout", timeout_at=time.time())
                        os.killpg(process.pid, signal.SIGINT)
                    elif record.get("timeout_at") and time.time() - record["timeout_at"] > 40:
                        os.killpg(process.pid, signal.SIGKILL)
                    continue
                record.update(state="timed_out" if record.get("timeout_at") else "generated_pending_review" if code == 0 else "needs_fix", exit_code=code, ended_at=time.time())
                log.close()
                del running[name]
                print(json.dumps({"job": name, "state": record["state"], "exit_code": code}), flush=True)
            while pending and len(running) + int(adopted is not None) < args.max_jobs:
                name = pending.pop(0)
                log = (output / f"{name}.log").open("a")
                command = [sys.executable, "-u", *catalog[name][1]]
                try:
                    process = subprocess.Popen(command, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
                except OSError as error:
                    log.close()
                    records[name].update(state="needs_fix", error=str(error), ended_at=time.time())
                    continue
                records[name].update(state="running", pid=process.pid, started_at=time.time())
                running[name] = (process, log)
                print(json.dumps({"job": name, "state": "running", "pid": process.pid}), flush=True)
            persist()
            if pending or running or adopted:
                time.sleep(3)
    finally:
        # An adopted task was started elsewhere: never terminate it here.
        for name, (process, log) in running.items():
            if process.poll() is None:
                os.killpg(process.pid, signal.SIGINT)
        for name, (process, log) in running.items():
            try:
                process.wait(timeout=40)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait()
            records[name].update(state="interrupted", ended_at=time.time())
            log.close()
        persist()


if __name__ == "__main__":
    main()
