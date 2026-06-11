"""Local web console for running and observing the shale gas agent."""

from __future__ import annotations

import json
import os
import re
import signal
import subprocess
import sys
import threading
import time
import uuid
import webbrowser
from dataclasses import dataclass, field
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse


ROOT_DIR = Path(__file__).resolve().parent
FRONTEND_DIR = ROOT_DIR / "frontend"
PROJECT_DIR = ROOT_DIR if (ROOT_DIR / "pyproject.toml").exists() else ROOT_DIR / "shale_gas_analyzer"
REPORT_PATH = PROJECT_DIR / "shale_gas_production_report.md"
START_SCRIPT = ROOT_DIR / "start_project.py"
UPLOAD_DIR = PROJECT_DIR / "data" / "uploads"


def _now() -> float:
    return time.time()


def _mime_type(path: Path) -> str:
    suffix = path.suffix.lower()
    return {
        ".html": "text/html; charset=utf-8",
        ".css": "text/css; charset=utf-8",
        ".js": "application/javascript; charset=utf-8",
        ".json": "application/json; charset=utf-8",
        ".svg": "image/svg+xml",
    }.get(suffix, "application/octet-stream")


@dataclass
class RunState:
    id: str
    mode: str
    well_name: str
    status: str = "starting"
    started_at: float = field(default_factory=_now)
    ended_at: float | None = None
    return_code: int | None = None
    stop_requested: bool = False
    command: list[str] = field(default_factory=list)
    data_file: str = ""
    events: list[dict[str, Any]] = field(default_factory=list)
    process: subprocess.Popen[str] | None = None


class RunManager:
    def __init__(self, python_path: Path) -> None:
        self.python_path = python_path
        self._lock = threading.RLock()
        self._condition = threading.Condition(self._lock)
        self._current: RunState | None = None
        self._sequence = 0

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            if not self._current:
                return {"running": False, "run": None}
            run = self._current
            return {
                "running": run.status in {"starting", "running", "stopping"},
                "run": self._public_run(run),
                "eventCount": len(run.events),
                "sequence": self._sequence,
            }

    def start(self, payload: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            if self._current and self._current.status in {"starting", "running"}:
                raise RuntimeError("An agent run is already active.")

            mode = str(payload.get("mode") or "run")
            if mode not in {"run", "hierarchical"}:
                raise ValueError("Unsupported run mode.")

            well_name = str(payload.get("wellName") or "").strip()
            run = RunState(id=uuid.uuid4().hex[:12], mode=mode, well_name=well_name)
            data_file_id = str(payload.get("dataFileId") or "").strip()
            data_file = str(payload.get("dataFile") or "").strip()
            if data_file_id:
                data_file = str((UPLOAD_DIR / Path(data_file_id).name).resolve())
            if data_file:
                path = Path(data_file).resolve()
                if not path.exists() or path.suffix.lower() != ".csv":
                    raise ValueError(
                        f"Uploaded data file is missing or not a CSV: path={path}, "
                        f"exists={path.exists()}, suffix={path.suffix}"
                    )
                try:
                    path.relative_to(UPLOAD_DIR.resolve())
                except ValueError as exc:
                    raise ValueError("Uploaded data file is outside the upload directory.") from exc
                run.data_file = str(path)
            run.command = self._build_command(run, payload)
            self._current = run
            self._add_event(run, "status", f"Run {run.id} queued.", phase="queued")

            thread = threading.Thread(target=self._run_process, args=(run,), daemon=True)
            thread.start()
            return self._public_run(run)

    def stop(self) -> dict[str, Any]:
        with self._lock:
            run = self._current
            if not run or run.status not in {"starting", "running"} or not run.process:
                return {"stopped": False}
            run.stop_requested = True
            run.status = "stopping"
            self._add_event(run, "status", "Stop requested.", phase="stopping")
            process = run.process

        self._terminate_process_tree(process)
        return {"stopped": True}

    def wait_events(self, after: int, timeout: float = 20.0) -> tuple[int, list[dict[str, Any]], dict[str, Any]]:
        deadline = _now() + timeout
        with self._condition:
            while True:
                events = self._events_after(after)
                if events:
                    return self._sequence, events, self.snapshot()
                remaining = deadline - _now()
                if remaining <= 0:
                    return self._sequence, [], self.snapshot()
                self._condition.wait(timeout=min(remaining, 1.0))

    def _build_command(self, run: RunState, payload: dict[str, Any]) -> list[str]:
        command = [str(self.python_path), str(START_SCRIPT), run.mode]
        if run.well_name:
            command.append(run.well_name)
        command.append("--skip-install")
        if payload.get("skipRag"):
            command.append("--skip-rag")
        if payload.get("ragRebuild"):
            command.append("--rag-rebuild")
        return command

    def _run_process(self, run: RunState) -> None:
        env = os.environ.copy()
        env.setdefault("PYTHONUTF8", "1")
        env.setdefault("PYTHONIOENCODING", "utf-8")
        env["PYTHONUNBUFFERED"] = "1"
        if run.data_file:
            env["SHALE_GAS_DATA_FILE"] = run.data_file

        try:
            self._mark_running(run)
            process = subprocess.Popen(
                run.command,
                cwd=ROOT_DIR,
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
            )
            with self._lock:
                run.process = process

            assert process.stdout is not None
            for line in process.stdout:
                clean = line.rstrip("\n")
                if clean:
                    self._add_event(run, "log", clean, phase=self._classify_phase(clean))

            return_code = process.wait()
            self._finish(run, return_code)
        except Exception as exc:
            self._add_event(run, "error", str(exc), phase="error")
            self._finish(run, 1)

    @staticmethod
    def _terminate_process_tree(process: subprocess.Popen[str]) -> None:
        if process.poll() is not None:
            return
        if os.name == "nt":
            subprocess.run(
                ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
            )
            return
        process.send_signal(signal.SIGTERM)

    def _mark_running(self, run: RunState) -> None:
        with self._lock:
            run.status = "running"
            self._add_event(run, "status", "Agent process started.", phase="agent")

    def _finish(self, run: RunState, return_code: int) -> None:
        with self._lock:
            run.return_code = return_code
            run.ended_at = _now()
            if run.stop_requested:
                run.status = "stopped"
                self._add_event(run, "status", "Agent run stopped.", phase="done")
                return

            run.status = "completed" if return_code == 0 else "failed"
            message = "Agent run completed." if return_code == 0 else f"Agent run failed with exit code {return_code}."
            self._add_event(run, "status", message, phase="done" if return_code == 0 else "error")
            if return_code == 0 and REPORT_PATH.exists():
                self._add_event(run, "report", "Report is ready.", phase="report")

    def _add_event(self, run: RunState, kind: str, message: str, phase: str = "agent") -> None:
        with self._condition:
            self._sequence += 1
            run.events.append(
                {
                    "seq": self._sequence,
                    "runId": run.id,
                    "kind": kind,
                    "phase": phase,
                    "message": message,
                    "timestamp": _now(),
                }
            )
            if len(run.events) > 3000:
                run.events = run.events[-3000:]
            self._condition.notify_all()

    def _events_after(self, after: int) -> list[dict[str, Any]]:
        if not self._current:
            return []
        return [event for event in self._current.events if int(event["seq"]) > after]

    def _public_run(self, run: RunState) -> dict[str, Any]:
        return {
            "id": run.id,
            "mode": run.mode,
            "wellName": run.well_name,
            "status": run.status,
            "startedAt": run.started_at,
            "endedAt": run.ended_at,
            "returnCode": run.return_code,
            "command": run.command,
            "dataFile": run.data_file,
        }

    @staticmethod
    def _classify_phase(line: str) -> str:
        lower = line.lower()
        if "rag" in lower or "向量库" in line or "知识库" in line:
            return "rag"
        if "read_shale_data" in lower or "calculate_decline" in lower or "数据" in line:
            return "data"
        if "retrieve_engineering" in lower or "工程" in line or "knowledge" in lower:
            return "engineering"
        if "report" in lower or "报告" in line:
            return "report"
        if "error" in lower or "failed" in lower or "失败" in line:
            return "error"
        return "agent"


class ConsoleHandler(BaseHTTPRequestHandler):
    manager: RunManager

    server_version = "ShaleGasAgentConsole/0.1"

    def log_message(self, format: str, *args: Any) -> None:
        return

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path
        if path == "/":
            self._serve_file(FRONTEND_DIR / "index.html")
        elif path.startswith("/static/"):
            self._serve_file(FRONTEND_DIR / path.removeprefix("/static/"))
        elif path == "/api/state":
            self._send_json(self.manager.snapshot())
        elif path == "/api/report":
            self._send_json(self._report_payload())
        elif path == "/api/events":
            self._serve_events(parsed.query)
        else:
            self.send_error(HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/api/runs":
            payload = self._read_json()
            try:
                run = self.manager.start(payload)
            except RuntimeError as exc:
                self._send_json({"error": str(exc)}, HTTPStatus.CONFLICT)
                return
            except ValueError as exc:
                self._send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
                return
            self._send_json({"run": run})
        elif parsed.path == "/api/upload":
            try:
                self._send_json({"file": self._handle_upload()})
            except ValueError as exc:
                self._send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
        elif parsed.path == "/api/stop":
            self._send_json(self.manager.stop())
        else:
            self.send_error(HTTPStatus.NOT_FOUND)

    def _read_json(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0") or "0")
        if not length:
            return {}
        raw = self.rfile.read(length).decode("utf-8", errors="replace")
        return json.loads(raw)

    def _handle_upload(self) -> dict[str, Any]:
        raw_name = self.headers.get("X-File-Name", "uploaded.csv")
        name = _safe_upload_name(raw_name)
        if not name.lower().endswith(".csv"):
            raise ValueError("Only CSV files can be uploaded.")

        length = int(self.headers.get("Content-Length", "0") or "0")
        if length <= 0:
            raise ValueError("Uploaded file is empty.")
        if length > 50 * 1024 * 1024:
            raise ValueError("Uploaded file is larger than 50 MB.")

        UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
        target = UPLOAD_DIR / f"{int(time.time())}_{uuid.uuid4().hex[:8]}_{name}"
        data = self.rfile.read(length)
        target.write_bytes(data)
        return {
            "id": target.name,
            "name": name,
            "path": str(target.resolve()),
            "size": target.stat().st_size,
        }

    def _serve_file(self, path: Path) -> None:
        if not path.exists() or not path.is_file():
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        data = path.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", _mime_type(path))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _serve_events(self, query: str) -> None:
        params = {}
        for part in query.split("&"):
            if "=" in part:
                key, value = part.split("=", 1)
                params[key] = value
        after = int(params.get("after", "0") or "0")

        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.end_headers()

        while True:
            after, events, state = self.manager.wait_events(after)
            payload = json.dumps({"events": events, "state": state}, ensure_ascii=False)
            self.wfile.write(f"data: {payload}\n\n".encode("utf-8"))
            self.wfile.flush()
            if not state.get("running") and events:
                break

    def _send_json(self, payload: dict[str, Any], status: HTTPStatus = HTTPStatus.OK) -> None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    @staticmethod
    def _report_payload() -> dict[str, Any]:
        if not REPORT_PATH.exists():
            return {"exists": False, "content": "", "updatedAt": None}
        stat = REPORT_PATH.stat()
        return {
            "exists": True,
            "content": REPORT_PATH.read_text(encoding="utf-8", errors="replace"),
            "updatedAt": stat.st_mtime,
            "size": stat.st_size,
        }


def _safe_upload_name(name: str) -> str:
    stem = Path(unquote(name)).name.strip() or "uploaded.csv"
    stem = re.sub(r"[^A-Za-z0-9._\-\u4e00-\u9fff]+", "_", stem)
    return stem[:120] or "uploaded.csv"


def run_server(
    python_path: str | Path | None = None,
    host: str = "127.0.0.1",
    port: int = 8765,
    open_browser: bool = True,
) -> None:
    if python_path is None:
        python_path = PROJECT_DIR / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        if not Path(python_path).exists():
            python_path = Path(sys.executable)

    ConsoleHandler.manager = RunManager(Path(python_path))

    server = None
    selected_port = port
    for candidate_port in range(port, port + 20):
        try:
            server = ThreadingHTTPServer((host, candidate_port), ConsoleHandler)
            selected_port = candidate_port
            break
        except OSError:
            continue
    if server is None:
        raise SystemExit(f"No available port found from {port} to {port + 19}.")

    url = f"http://{host}:{selected_port}"
    print(f"Agent console: {url}", flush=True)
    if open_browser:
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("Stopping agent console.", flush=True)
    finally:
        server.server_close()


if __name__ == "__main__":
    run_server()
