import json
import os
import shlex
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Dict, Optional
from urllib.parse import urlparse


DEFAULT_BIND_HOST = "127.0.0.1"
DEFAULT_PORT = 8766
DEFAULT_HEARTBEAT_PATH = "enterprise_server.heartbeat"
DEFAULT_LOG_PATH = "enterprise_server.log"
DEFAULT_JOBS_DIR = "enterprise_jobs"
DEFAULT_SESSIONS_DIR = "enterprise_sessions"
JOB_RETENTION_SECONDS = 3600
SESSION_HISTORY_LIMIT = 12
PROTECTED_SERVER_CORE_PATHS = (
    ".env",
    "/home/userland/.profile",
    "/home/userland/bin/autostart_jarvis_bot.sh",
    "run_jarvis_supervisor.sh",
    "restart_jarvis_supervisor.sh",
    "run_enterprise_supervisor.sh",
    "start_enterprise_on_userland.sh",
    "enterprise_server.py",
    "enterprise_worker.py",
    ".enterprise_supervisor.pid",
    "enterprise_server.heartbeat",
    "tg_codex_bridge.lock",
    "tg_codex_bridge.heartbeat",
)


def now_ts() -> float:
    return time.time()


def normalize_whitespace(text: str) -> str:
    lines = [line.rstrip() for line in (text or "").replace("\r", "").split("\n")]
    collapsed = []
    blank_count = 0
    for line in lines:
        if not line.strip():
            blank_count += 1
            if blank_count <= 1:
                collapsed.append("")
            continue
        blank_count = 0
        collapsed.append(line.strip())
    return "\n".join(collapsed).strip()


def truncate_text(text: str, limit: int) -> str:
    cleaned = normalize_whitespace(text or "")
    if len(cleaned) <= limit:
        return cleaned
    if limit <= 3:
        return cleaned[:limit]
    return cleaned[: limit - 3].rstrip() + "..."


def append_event(events: list, text: str) -> list:
    clean = normalize_whitespace(text)
    if not clean:
        return events
    if events and events[-1] == clean:
        return events
    events.append(clean)
    return events[-160:]


def server_event(title: str, detail: str) -> str:
    return f"• {title}\n└ {detail}"


def build_session_context(entries: list) -> str:
    if not entries:
        return ""
    lines = ["Контекст предыдущих задач Enterprise:"]
    for entry in entries[-SESSION_HISTORY_LIMIT:]:
        user_text = normalize_whitespace(str(entry.get("user") or ""))
        answer_text = normalize_whitespace(str(entry.get("assistant") or ""))
        if user_text:
            lines.append(f"Пользователь: {user_text[:500]}")
        if answer_text:
            lines.append(f"Enterprise: {answer_text[:700]}")
    return "\n".join(lines).strip()


def build_session_summary(entries: list) -> str:
    if not entries:
        return ""
    topics = []
    decisions = []
    for entry in entries[-SESSION_HISTORY_LIMIT:]:
        user_text = truncate_text(str(entry.get("user") or ""), 180)
        answer_text = truncate_text(str(entry.get("assistant") or ""), 220)
        if user_text:
            topics.append(user_text)
        if answer_text:
            decisions.append(answer_text)
    lines = ["Краткая сводка предыдущих задач Enterprise:"]
    if topics:
        lines.append("Темы: " + " | ".join(topics[-4:]))
    if decisions:
        lines.append("Последние выводы: " + " | ".join(decisions[-3:]))
    return "\n".join(lines).strip()


def load_env(script_dir: Path) -> None:
    env_path = script_dir / ".env"
    if not env_path.exists():
        pass
    else:
        for raw_line in env_path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = value
    # Принудительно подставляем современный Node для Codex CLI.
    nvm_node_bin = Path("/home/userland/.nvm/versions/node/v18.20.8/bin")
    if nvm_node_bin.joinpath("node").exists():
        current_path = os.environ.get("PATH", "")
        os.environ["PATH"] = f"{nvm_node_bin}:{current_path}" if current_path else str(nvm_node_bin)


class RuntimeControl:
    def __init__(self, script_dir: Path, log_path: Path) -> None:
        self.script_dir = script_dir
        self.log_path = log_path
        self.lock = threading.RLock()

    def _log(self, message: str) -> None:
        line = f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {message}\n"
        with self.log_path.open("a", encoding="utf-8") as handle:
            handle.write(line)

    def _read_pid_file(self, path: Path) -> int:
        try:
            raw = path.read_text(encoding="utf-8").strip()
        except OSError:
            return 0
        return int(raw) if raw.isdigit() else 0

    def _is_alive(self, pid: int) -> bool:
        if pid <= 0:
            return False
        try:
            os.kill(pid, 0)
        except OSError:
            return False
        return True

    def _find_pid(self, pattern: str) -> int:
        try:
            result = subprocess.run(
                ["pgrep", "-fo", pattern],
                capture_output=True,
                text=True,
                cwd=str(self.script_dir),
                timeout=5,
            )
        except Exception:
            return 0
        raw = (result.stdout or "").strip()
        return int(raw) if raw.isdigit() else 0

    def status_snapshot(self) -> dict:
        supervisor_pid = self._read_pid_file(self.script_dir / ".jarvis_supervisor.pid")
        if not self._is_alive(supervisor_pid):
            supervisor_pid = self._find_pid("run_jarvis_supervisor.sh")
        bridge_lock_pid = self._read_pid_file(self.script_dir / "tg_codex_bridge.lock")
        bridge_pid = bridge_lock_pid if self._is_alive(bridge_lock_pid) else self._find_pid("tg_codex_bridge.py")
        enterprise_pid = self._find_pid("enterprise_server.py")
        return {
            "supervisor_pid": supervisor_pid,
            "supervisor_alive": self._is_alive(supervisor_pid),
            "bridge_pid": bridge_pid,
            "bridge_alive": self._is_alive(bridge_pid),
            "enterprise_pid": enterprise_pid,
            "enterprise_alive": self._is_alive(enterprise_pid),
        }

    def restart_bridge_runtime(self) -> dict:
        helper = self.script_dir / "restart_jarvis_supervisor.sh"
        if not helper.exists():
            raise FileNotFoundError(f"restart helper missing: {helper}")
        with self.lock:
            self._log("runtime control requested bridge restart")
            process = subprocess.run(
                [str(helper)],
                capture_output=True,
                text=True,
                cwd=str(self.script_dir),
                timeout=45,
            )
            stdout = normalize_whitespace(process.stdout or "")
            stderr = normalize_whitespace(process.stderr or "")
            snapshot = self.status_snapshot()
            self._log(
                "runtime control bridge restart "
                f"rc={process.returncode} stdout={truncate_text(stdout, 120)} stderr={truncate_text(stderr, 120)}"
            )
            return {
                "ok": process.returncode == 0,
                "returncode": process.returncode,
                "stdout": stdout,
                "stderr": stderr,
                "runtime": snapshot,
            }


class EnterpriseJobManager:
    def __init__(self, script_dir: Path, worker_path: Path, log_path: Path, jobs_dir: Path, sessions_dir: Path) -> None:
        self.script_dir = script_dir
        self.worker_path = worker_path
        self.log_path = log_path
        self.jobs_dir = jobs_dir
        self.sessions_dir = sessions_dir
        self.lock = threading.RLock()
        self.jobs: Dict[str, Dict[str, object]] = {}
        self.jobs_dir.mkdir(parents=True, exist_ok=True)
        self.sessions_dir.mkdir(parents=True, exist_ok=True)
        self._load_jobs_from_disk()
        self._resume_incomplete_jobs()

    def _log(self, message: str) -> None:
        line = f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {message}\n"
        with self.log_path.open("a", encoding="utf-8") as handle:
            handle.write(line)

    def _job_dir(self, job_id: str) -> Path:
        return self.jobs_dir / job_id

    def _job_state_path(self, job_id: str) -> Path:
        return self._job_dir(job_id) / "state.json"

    def _session_state_path(self, chat_id: int) -> Path:
        return self.sessions_dir / f"{int(chat_id)}.json"

    def _load_session_entries(self, chat_id: int) -> list:
        path = self._session_state_path(chat_id)
        if not path.exists():
            return []
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return []
        if not isinstance(payload, list):
            return []
        return payload

    def _append_session_entry(self, chat_id: int, user_text: str, answer_text: str) -> None:
        if int(chat_id or 0) == 0:
            return
        entries = self._load_session_entries(chat_id)
        entries.append(
            {
                "ts": now_ts(),
                "user": truncate_text(normalize_whitespace(user_text), 1200),
                "assistant": truncate_text(normalize_whitespace(answer_text), 1800),
            }
        )
        entries = entries[-SESSION_HISTORY_LIMIT:]
        self._session_state_path(chat_id).write_text(
            json.dumps(entries, ensure_ascii=False, sort_keys=True),
            encoding="utf-8",
        )

    def _persist_job_unlocked(self, job: Dict[str, object]) -> None:
        job_id = str(job.get("id") or "")
        if not job_id:
            return
        job_dir = self._job_dir(job_id)
        job_dir.mkdir(parents=True, exist_ok=True)
        self._job_state_path(job_id).write_text(
            json.dumps(job, ensure_ascii=False, sort_keys=True),
            encoding="utf-8",
        )

    def _load_jobs_from_disk(self) -> None:
        cutoff = now_ts() - JOB_RETENTION_SECONDS
        for state_path in self.jobs_dir.glob("*/state.json"):
            try:
                payload = json.loads(state_path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            job_id = str(payload.get("id") or "")
            updated_at = float(payload.get("updated_at") or 0.0)
            if not job_id or updated_at < cutoff:
                continue
            self.jobs[job_id] = payload

    def _resume_incomplete_jobs(self) -> None:
        for job_id, job in list(self.jobs.items()):
            if bool(job.get("done")):
                continue
            threading.Thread(target=self._monitor_existing_job, args=(job_id,), daemon=True).start()

    def _is_pid_alive(self, pid_value: object) -> bool:
        try:
            pid = int(pid_value or 0)
        except (TypeError, ValueError):
            return False
        if pid <= 0:
            return False
        try:
            os.kill(pid, 0)
        except OSError:
            return False
        return True

    def _finalize_job_from_files(self, job_id: str, return_code: int, stderr_text: str = "") -> None:
        result_path = self._job_dir(job_id) / "result.json"
        answer = ""
        error = normalize_whitespace(stderr_text or "")
        if result_path.exists():
            try:
                result_payload = json.loads(result_path.read_text(encoding="utf-8"))
            except ValueError as parse_error:
                result_payload = {"ok": False, "answer": f"Не удалось разобрать result.json: {parse_error}"}
            answer = normalize_whitespace(str(result_payload.get("answer") or ""))
            if not error:
                error = normalize_whitespace(str(result_payload.get("error") or ""))
        with self.lock:
            job = self.jobs.get(job_id)
            if job is None:
                return
            job["done"] = True
            job["exit_code"] = return_code
            job["answer"] = answer
            job["error"] = error
            job["updated_at"] = now_ts()
            events = list(job.get("events") or [])
            events = append_event(events, server_event("Завершаю", "Выполнение завершено"))
            if answer:
                events = append_event(events, server_event("Финал", "Готовлю итоговое сообщение"))
            elif error:
                events = append_event(events, server_event("Финал", "Готовлю описание ошибки"))
            job["events"] = events[-160:]
            self._persist_job_unlocked(job)

    def _mark_job_interrupted(self, job_id: str, message: str) -> None:
        with self.lock:
            job = self.jobs.get(job_id)
            if job is None or bool(job.get("done")):
                return
            job["done"] = True
            job["exit_code"] = -1
            job["error"] = normalize_whitespace(message)
            job["updated_at"] = now_ts()
            events = list(job.get("events") or [])
            events = append_event(events, server_event("Ошибка", message))
            job["events"] = events[-160:]
            self._persist_job_unlocked(job)

    def _monitor_existing_job(self, job_id: str) -> None:
        progress_path = self._job_dir(job_id) / "progress.log"
        result_path = self._job_dir(job_id) / "result.json"
        seen_progress_lines = 0
        while True:
            with self.lock:
                job = self.jobs.get(job_id)
                if job is None or bool(job.get("done")):
                    return
                worker_pid = job.get("worker_pid")
            if progress_path.exists():
                try:
                    progress_lines = [
                        normalize_whitespace(line)
                        for line in progress_path.read_text(encoding="utf-8").splitlines()
                    ]
                except OSError:
                    progress_lines = []
                progress_lines = [line for line in progress_lines if line]
                if seen_progress_lines < len(progress_lines):
                    new_lines = progress_lines[seen_progress_lines:]
                    seen_progress_lines = len(progress_lines)
                    with self.lock:
                        job = self.jobs.get(job_id)
                        if job is not None and not bool(job.get("done")):
                            events = list(job.get("events") or [])
                            for line in new_lines:
                                events = append_event(events, line)
                            job["events"] = events[-160:]
                            job["updated_at"] = now_ts()
                            self._persist_job_unlocked(job)
            if result_path.exists() and not self._is_pid_alive(worker_pid):
                self._finalize_job_from_files(job_id, int((self.jobs.get(job_id) or {}).get("exit_code") or 0))
                return
            if not self._is_pid_alive(worker_pid):
                self._mark_job_interrupted(job_id, "Задача оборвалась во время рестарта сервера.")
                return
            time.sleep(0.5)

    def create_job(self, payload: dict) -> str:
        job_id = os.urandom(8).hex()
        prompt = str(payload.get("prompt") or "").strip()
        chat_id = int(payload.get("chat_id") or 0)
        job = {
            "id": job_id,
            "chat_id": chat_id,
            "prompt": prompt,
            "created_at": now_ts(),
            "updated_at": now_ts(),
            "done": False,
            "exit_code": None,
            "answer": "",
            "error": "",
            "events": [
                server_event("Старт", "Запрос принят"),
                server_event("Подключаю", "Подключаю Enterprise"),
            ],
            "cwd": str(self.script_dir),
        }
        with self.lock:
            self.jobs[job_id] = job
            self._persist_job_unlocked(job)
        threading.Thread(target=self._run_job, args=(job_id, payload), daemon=True).start()
        return job_id

    def _run_job(self, job_id: str, payload: dict) -> None:
        try:
            with self.lock:
                job = self.jobs.get(job_id)
                if job is None:
                    return
                job["events"] = [
                    server_event("Старт", "Запрос принят"),
                    server_event("Подключаю", "Подключаю Enterprise"),
                    server_event("Готовлю", "Готовлю изолированную среду"),
                    server_event("Передаю", "Передаю задачу в движок"),
                ]
                job["updated_at"] = now_ts()
                self._persist_job_unlocked(job)
            chat_id = int(payload.get("chat_id") or 0)
            session_entries = self._load_session_entries(chat_id)
            session_context = build_session_context(session_entries)
            session_summary = build_session_summary(session_entries)
            effective_prompt = payload.get("prompt") or ""
            prefix_parts = [part for part in (session_summary, session_context) if part]
            if prefix_parts:
                effective_prompt = f"{chr(10).join(prefix_parts)}\n\nТекущая задача:\n{effective_prompt}"

            job_dir = self._job_dir(job_id)
            job_dir.mkdir(parents=True, exist_ok=True)
            task_path = job_dir / "task.json"
            result_path = job_dir / "result.json"
            progress_path = job_dir / "progress.log"
            if progress_path.exists():
                progress_path.unlink()
            if result_path.exists():
                result_path.unlink()
            with self.lock:
                job = self.jobs.get(job_id)
                if job is not None:
                    events = list(job.get("events") or [])
                    job["events"] = append_event(events, server_event("Запускаю", "Среда запущена"))
                    job["updated_at"] = now_ts()
                    self._persist_job_unlocked(job)
            worker_payload = dict(payload)
            worker_payload["prompt"] = effective_prompt
            worker_payload["progress_path"] = str(progress_path)
            worker_payload["protected_paths"] = list(PROTECTED_SERVER_CORE_PATHS)
            task_path.write_text(json.dumps(worker_payload, ensure_ascii=False), encoding="utf-8")
            process = subprocess.Popen(
                ["python3", str(self.worker_path), str(task_path), str(result_path)],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                cwd=str(self.script_dir),
                env=os.environ.copy(),
            )
            with self.lock:
                job = self.jobs.get(job_id)
                if job is not None:
                    job["worker_pid"] = process.pid
                    job["updated_at"] = now_ts()
                    self._persist_job_unlocked(job)
            timeout_seconds = int(payload.get("codex_timeout") or 180) or 180
            started_at = now_ts()
            seen_progress_lines = 0
            while True:
                return_code = process.poll()
                current_ts = now_ts()
                elapsed = int(max(1, current_ts - started_at))
                if progress_path.exists():
                    try:
                        progress_lines = [
                            normalize_whitespace(line)
                            for line in progress_path.read_text(encoding="utf-8").splitlines()
                        ]
                    except OSError:
                        progress_lines = []
                    progress_lines = [line for line in progress_lines if line]
                    if seen_progress_lines < len(progress_lines):
                        new_lines = progress_lines[seen_progress_lines:]
                        seen_progress_lines = len(progress_lines)
                        with self.lock:
                            job = self.jobs.get(job_id)
                            if job is not None:
                                events = list(job.get("events") or [])
                                for line in new_lines:
                                    events = append_event(events, line)
                                job["events"] = events[-160:]
                                job["updated_at"] = current_ts
                                self._persist_job_unlocked(job)
                if return_code is not None:
                    break
                if elapsed >= timeout_seconds:
                    process.kill()
                    process.wait(timeout=5)
                    with self.lock:
                        job = self.jobs.get(job_id)
                        if job is not None:
                            events = list(job.get("events") or [])
                            job["events"] = append_event(events, server_event("Таймаут", "Превышено время ожидания выполнения"))
                            job["updated_at"] = current_ts
                            self._persist_job_unlocked(job)
                    raise TimeoutError(f"worker timeout after {timeout_seconds} seconds")
                time.sleep(0.5)
            _stdout_text, stderr_text = process.communicate()
            self._finalize_job_from_files(job_id, process.returncode or 0, stderr_text or "")
            with self.lock:
                job = self.jobs.get(job_id)
                if job is not None and bool(job.get("done")) and str(job.get("answer") or "").strip():
                    self._append_session_entry(
                        int(job.get("chat_id") or 0),
                        str(job.get("prompt") or ""),
                        str(job.get("answer") or ""),
                    )
            self._log(f"job={job_id} done rc={process.returncode}")
        except Exception as error:
            with self.lock:
                job = self.jobs.get(job_id)
                if job is not None:
                    job["done"] = True
                    job["exit_code"] = -1
                    job["error"] = normalize_whitespace(str(error))
                    job["updated_at"] = now_ts()
                    events = list(job.get("events") or [])
                    job["events"] = append_event(events, server_event("Ошибка", normalize_whitespace(str(error))))
                    self._persist_job_unlocked(job)
            self._log(f"job={job_id} crashed error={error}")

    def get_job(self, job_id: str) -> Optional[Dict[str, object]]:
        with self.lock:
            job = self.jobs.get(job_id)
            if job is None:
                return None
            return {
                "id": str(job.get("id") or ""),
                "prompt": str(job.get("prompt") or ""),
                "started_at": float(job.get("created_at") or 0.0),
                "updated_at": float(job.get("updated_at") or 0.0),
                "done": bool(job.get("done")),
                "exit_code": job.get("exit_code"),
                "answer": str(job.get("answer") or ""),
                "error": str(job.get("error") or ""),
                "events": list(job.get("events") or []),
                "cwd": str(job.get("cwd") or ""),
                "output": str(job.get("answer") or "") or "\n".join(job.get("events") or []),
                "command": str(job.get("prompt") or ""),
            }

    def cleanup(self) -> None:
        cutoff = now_ts() - JOB_RETENTION_SECONDS
        with self.lock:
            stale_ids = [job_id for job_id, job in self.jobs.items() if float(job.get("updated_at") or 0.0) < cutoff]
            for job_id in stale_ids:
                self.jobs.pop(job_id, None)
                state_path = self._job_state_path(job_id)
                try:
                    if state_path.exists():
                        state_path.unlink()
                except OSError:
                    pass


def build_handler(job_manager: EnterpriseJobManager, runtime_control: RuntimeControl):
    class EnterpriseAPIHandler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args) -> None:
            return

        def _send_cors_headers(self) -> None:
            origin = self.headers.get("Origin", "*") or "*"
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Vary", "Origin")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
            self.send_header("Access-Control-Allow-Private-Network", "true")

        def _write_json(self, payload: dict, status: int = 200) -> None:
            encoded = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self._send_cors_headers()
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(encoded)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(encoded)

        def _read_payload(self) -> dict:
            content_length = int(self.headers.get("Content-Length", "0") or "0")
            raw = self.rfile.read(content_length) if content_length > 0 else b"{}"
            try:
                return json.loads(raw.decode("utf-8") or "{}")
            except json.JSONDecodeError:
                return {}

        def do_OPTIONS(self) -> None:
            self.send_response(204)
            self._send_cors_headers()
            self.send_header("Content-Length", "0")
            self.end_headers()

        def do_GET(self) -> None:
            parsed = urlparse(self.path)
            if parsed.path == "/health":
                self._write_json({"ok": True, "service": "enterprise_server", "ts": now_ts()})
                return
            if parsed.path == "/api/runtime/status":
                snapshot = runtime_control.status_snapshot()
                snapshot["ok"] = True
                self._write_json(snapshot)
                return
            if parsed.path.startswith("/api/jobs/"):
                job_id = parsed.path.rsplit("/", 1)[-1]
                snapshot = job_manager.get_job(job_id)
                if snapshot is None:
                    self._write_json({"ok": False, "error": "not found"}, status=404)
                    return
                snapshot["ok"] = True
                self._write_json(snapshot)
                return
            self._write_json({"ok": False, "error": "not found"}, status=404)

        def do_POST(self) -> None:
            parsed = urlparse(self.path)
            payload = self._read_payload()
            if parsed.path == "/api/jobs":
                prompt = str(payload.get("prompt") or "").strip()
                if not prompt:
                    self._write_json({"ok": False, "error": "empty prompt"}, status=400)
                    return
                job_id = job_manager.create_job(payload)
                self._write_json({"ok": True, "job_id": job_id})
                return
            if parsed.path == "/api/runtime/restart_bridge":
                try:
                    result = runtime_control.restart_bridge_runtime()
                except Exception as error:
                    self._write_json({"ok": False, "error": normalize_whitespace(str(error))}, status=500)
                    return
                status = 200 if result.get("ok") else 500
                self._write_json(result, status=status)
                return
            if parsed.path == "/api/run_sync":
                prompt = str(payload.get("prompt") or "").strip()
                if not prompt:
                    self._write_json({"ok": False, "error": "empty prompt"}, status=400)
                    return
                job_id = job_manager.create_job(payload)
                deadline = now_ts() + max(30, int(payload.get("codex_timeout") or 180))
                while now_ts() < deadline:
                    snapshot = job_manager.get_job(job_id)
                    if snapshot and snapshot.get("done"):
                        snapshot["ok"] = True
                        self._write_json(snapshot)
                        return
                    time.sleep(0.2)
                self._write_json({"ok": False, "error": "timeout", "answer": "Задача не завершилась вовремя."}, status=504)
                return
            self._write_json({"ok": False, "error": "not found"}, status=404)

    return EnterpriseAPIHandler


def main() -> int:
    script_dir = Path(__file__).resolve().parent
    load_env(script_dir)
    bind_host = (os.getenv("ENTERPRISE_SERVER_BIND_HOST", DEFAULT_BIND_HOST).strip() or DEFAULT_BIND_HOST)
    port = int(os.getenv("ENTERPRISE_SERVER_PORT", str(DEFAULT_PORT)).strip() or str(DEFAULT_PORT))
    heartbeat_path = Path(os.getenv("ENTERPRISE_SERVER_HEARTBEAT_PATH", str(script_dir / DEFAULT_HEARTBEAT_PATH)).strip() or str(script_dir / DEFAULT_HEARTBEAT_PATH))
    log_path = Path(os.getenv("ENTERPRISE_SERVER_LOG_PATH", str(script_dir / DEFAULT_LOG_PATH)).strip() or str(script_dir / DEFAULT_LOG_PATH))
    jobs_dir = Path(os.getenv("ENTERPRISE_SERVER_JOBS_DIR", str(script_dir / DEFAULT_JOBS_DIR)).strip() or str(script_dir / DEFAULT_JOBS_DIR))
    sessions_dir = Path(os.getenv("ENTERPRISE_SERVER_SESSIONS_DIR", str(script_dir / DEFAULT_SESSIONS_DIR)).strip() or str(script_dir / DEFAULT_SESSIONS_DIR))
    job_manager = EnterpriseJobManager(script_dir, script_dir / "enterprise_worker.py", log_path, jobs_dir, sessions_dir)
    runtime_control = RuntimeControl(script_dir, log_path)
    server = ThreadingHTTPServer((bind_host, port), build_handler(job_manager, runtime_control))
    threading.Thread(target=lambda: _heartbeat_loop(heartbeat_path, job_manager), daemon=True).start()
    server.serve_forever()
    return 0


def _heartbeat_loop(heartbeat_path: Path, job_manager: EnterpriseJobManager) -> None:
    while True:
        heartbeat_path.write_text(str(now_ts()), encoding="utf-8")
        job_manager.cleanup()
        time.sleep(5)


if __name__ == "__main__":
    raise SystemExit(main())
