import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional


DEFAULT_WORKER_PROTECTED_PATHS = (
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
    cleaned = (text or "").strip()
    if len(cleaned) <= limit:
        return cleaned
    if limit <= 3:
        return cleaned[:limit]
    return cleaned[: limit - 3].rstrip() + "..."


def _looks_like_internal_worklog(text: str) -> bool:
    cleaned = normalize_whitespace(text)
    if not cleaned:
        return False
    markers = (
        "• ran ",
        "• explored",
        "• waited for background terminal",
        "command: /bin/",
        "process exited with code",
        "wall time:",
        "chunk id:",
        "original token count:",
        "command: /bin/bash -lc",
    )
    lowered = cleaned.lower()
    hits = sum(1 for marker in markers if marker in lowered)
    if hits >= 2:
        return True
    lines = [line.strip().lower() for line in cleaned.splitlines() if line.strip()]
    bullet_hits = sum(
        1
        for line in lines
        if line.startswith("• ran ")
        or line.startswith("• explored")
        or line.startswith("• waited")
        or line.startswith("└ command:")
    )
    return bullet_hits >= 2


def strip_internal_worklog(text: str) -> str:
    cleaned = normalize_whitespace(text)
    if not cleaned:
        return ""
    if not _looks_like_internal_worklog(cleaned):
        return cleaned
    parts = re.split(r"\n[─-]{10,}\n", cleaned)
    for part in reversed(parts):
        candidate = normalize_whitespace(part)
        if candidate and not _looks_like_internal_worklog(candidate):
            return candidate
    return ""


def extract_json_answer(stdout: str) -> str:
    latest_text = ""
    for raw_line in (stdout or "").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if str(payload.get("type") or "") != "item.completed":
            continue
        item = payload.get("item") or {}
        if str(item.get("type") or "") != "agent_message":
            continue
        text = strip_internal_worklog(str(item.get("text") or ""))
        if text:
            latest_text = text
    return latest_text


def append_progress_event(progress_path: Optional[Path], text: str) -> None:
    if progress_path is None:
        return
    clean = normalize_whitespace(text)
    if not clean:
        return
    try:
        with progress_path.open("a", encoding="utf-8") as handle:
            handle.write(clean + "\n")
    except OSError:
        return


def append_stream_event(stream_path: Optional[Path], payload: Dict[str, object]) -> None:
    if stream_path is None:
        return
    try:
        with stream_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False) + "\n")
    except OSError:
        return


def format_json_progress_event(payload: dict) -> str:
    event_type = str(payload.get("type") or "")
    if event_type == "thread.started":
        return "• Старт\n└ Сессия Enterprise Core запущена"
    if event_type == "turn.started":
        return "• Начинаю\n└ Запрос принят в работу"
    if event_type == "turn.completed":
        return "• Завершаю\n└ Ход выполнения завершён"
    item = payload.get("item") or {}
    item_type = str(item.get("type") or "")
    if event_type == "item.completed" and item_type == "agent_message":
        text = normalize_whitespace(str(item.get("text") or ""))
        return f"• Комментарий\n└ {text[:240]}" if text else ""
    if event_type == "item.completed" and item_type == "command_execution":
        command = normalize_whitespace(str(item.get("command") or ""))
        if command:
            return f"• Действие\n└ {truncate_text(command, 180)}"
    return ""


def extract_stream_text_events(payload: dict) -> List[Dict[str, object]]:
    event_type = str(payload.get("type") or "")
    item = payload.get("item") or {}
    item_type = str(item.get("type") or "")
    events: List[Dict[str, object]] = []
    if item_type != "agent_message":
        return events

    text = normalize_whitespace(str(item.get("text") or ""))
    if event_type == "item.completed" and text:
        events.append({"kind": "assistant_text", "state": "completed", "text": text})
        return events

    for key in ("delta", "text_delta", "partial_text", "content", "text"):
        value = normalize_whitespace(str(item.get(key) or payload.get(key) or ""))
        if value:
            events.append({"kind": "assistant_text", "state": "delta", "text": value})
            break
    return events


def build_subprocess_env() -> dict:
    env = os.environ.copy()
    env.setdefault("PYTHONUNBUFFERED", "1")
    if (env.get("STT_BACKEND", "").strip().lower() or "disabled") == "disabled":
        env.pop("OPENAI_API_KEY", None)
        env.pop("OPENAI_BASE_URL", None)
        env.pop("AUDIO_TRANSCRIBE_MODEL", None)
    return env


def build_command(payload: dict) -> list:
    command = ["codex"]
    command.append("exec")
    sandbox_mode = payload.get("sandbox_mode")
    if sandbox_mode == "danger-full-access":
        command.append("--dangerously-bypass-approvals-and-sandbox")
    elif sandbox_mode == "workspace-write":
        command.append("--full-auto")
    if payload.get("json_output"):
        command.append("--json")
    command.append("--skip-git-repo-check")
    if sandbox_mode:
        command.extend(["--sandbox", sandbox_mode])
    model = str(payload.get("model") or "").strip()
    if model:
        command.extend(["-m", model])
    image_path = payload.get("image_path")
    if image_path:
        command.extend(["-i", str(image_path)])
    return command


def get_worker_protected_paths(payload: Optional[dict] = None) -> tuple[str, ...]:
    raw_paths = (payload or {}).get("protected_paths")
    if isinstance(raw_paths, (list, tuple)):
        cleaned = tuple(str(path).strip() for path in raw_paths if str(path).strip())
        if cleaned:
            return cleaned
    return DEFAULT_WORKER_PROTECTED_PATHS


def protect_prompt(prompt: str, payload: Optional[dict] = None) -> str:
    protected_paths = get_worker_protected_paths(payload)
    protected = "\n".join(f"- {path}" for path in protected_paths)
    runtime_prompt = normalize_whitespace(str((payload or {}).get("runtime_prompt") or ""))
    runtime_prefix = (
        "Отдельные инструкции Enterprise Runtime:\n"
        f"{runtime_prompt}\n\n"
        if runtime_prompt
        else ""
    )
    return (
        "ВАЖНО: этот worker работает почти по всему проекту, но не имеет права менять server-core.\n"
        "Через задачу можно свободно работать с кодом проекта, тестами, docs, обычными scripts, диагностикой, git-операциями по репо и файлами workspace.\n"
        "Запрещено изменять только защищённые управляющие пути server-core.\n"
        "Если задача просит трогать именно их, откажись и объясни, что это server-core и он меняется только через специальные server-side endpoints.\n\n"
        "Защищённые server-core пути:\n"
        f"{protected}\n\n"
        "Всё остальное в repo/workspace разрешено в рамках задачи.\n\n"
        f"{runtime_prefix}"
        f"{prompt}"
    )


def run_task(task_path: Path, result_path: Path) -> int:
    payload = json.loads(task_path.read_text(encoding="utf-8"))
    prompt = protect_prompt(payload.get("prompt") or "", payload)
    timeout = int(payload.get("codex_timeout") or 180)
    progress_path_raw = str(payload.get("progress_path") or "").strip()
    progress_path = Path(progress_path_raw) if progress_path_raw else None
    stream_path_raw = str(payload.get("stream_path") or "").strip()
    stream_path = Path(stream_path_raw) if stream_path_raw else None
    command = build_command(payload)
    stdin_command = command + ["-"]
    started_at = time.perf_counter()

    try:
        if payload.get("json_output"):
            process = subprocess.Popen(
                stdin_command,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=build_subprocess_env(),
                bufsize=1,
            )
            assert process.stdin is not None
            process.stdin.write(prompt)
            process.stdin.close()

            stdout_lines = []
            structured_answer = ""
            deadline = time.perf_counter() + timeout
            while True:
                if time.perf_counter() >= deadline:
                    process.kill()
                    process.wait(timeout=5)
                    raise subprocess.TimeoutExpired(stdin_command, timeout)
                if process.stdout is None:
                    break
                line = process.stdout.readline()
                if not line:
                    if process.poll() is not None:
                        break
                    time.sleep(0.1)
                    continue
                stdout_lines.append(line)
                raw_line = line.strip()
                if not raw_line:
                    continue
                try:
                    json_payload = json.loads(raw_line)
                except json.JSONDecodeError:
                    continue
                append_stream_event(
                    stream_path,
                    {
                        "kind": "codex_json",
                        "payload": json_payload,
                        "ts": int(time.time() * 1000),
                    },
                )
                progress_text = format_json_progress_event(json_payload)
                append_progress_event(progress_path, progress_text)
                for stream_event in extract_stream_text_events(json_payload):
                    stream_event["ts"] = int(time.time() * 1000)
                    append_stream_event(stream_path, stream_event)
                item = json_payload.get("item") or {}
                if str(json_payload.get("type") or "") == "item.completed" and str(item.get("type") or "") == "agent_message":
                    text = strip_internal_worklog(str(item.get("text") or ""))
                    if text:
                        structured_answer = text
            stderr_text = process.stderr.read() if process.stderr is not None else ""
            process.wait()
            result = subprocess.CompletedProcess(
                stdin_command,
                process.returncode,
                stdout="".join(stdout_lines),
                stderr=stderr_text,
            )
        else:
            structured_answer = None
            result = subprocess.run(
                stdin_command,
                capture_output=True,
                text=True,
                input=prompt,
                timeout=timeout,
                env=build_subprocess_env(),
            )
    except subprocess.TimeoutExpired:
        result_path.write_text(
            json.dumps(
                {
                    "ok": False,
                    "answer": "Задача не завершилась вовремя.",
                    "error": "timeout",
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        return 1
    except OSError as error:
        result_path.write_text(
            json.dumps(
                {
                    "ok": False,
                    "answer": "Не удалось запустить Enterprise worker.",
                    "error": str(error),
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        return 1

    stdout = normalize_whitespace(result.stdout or "")
    stderr = normalize_whitespace(result.stderr or "")
    if not payload.get("json_output"):
        structured_answer = None
    elif not structured_answer:
        structured_answer = extract_json_answer(result.stdout or "")
    if result.returncode != 0 and "No prompt provided" in stderr:
        try:
            result = subprocess.run(
                command + [prompt],
                capture_output=True,
                text=True,
                timeout=timeout,
                env=build_subprocess_env(),
            )
            stdout = normalize_whitespace(result.stdout or "")
            stderr = normalize_whitespace(result.stderr or "")
            structured_answer = extract_json_answer(result.stdout or "") if payload.get("json_output") else None
        except Exception as error:
            result_path.write_text(
                json.dumps(
                    {
                        "ok": False,
                        "answer": "Не удалось повторно запустить Enterprise worker.",
                        "error": str(error),
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            return 1

    elapsed_ms = max(1, int((time.perf_counter() - started_at) * 1000))
    if result.returncode != 0:
        details = stderr or stdout or "Worker завершился с ошибкой без вывода."
        result_path.write_text(
            json.dumps(
                {
                    "ok": False,
                    "answer": f"Ошибка Enterprise:\n{truncate_text(details, 2000)}",
                    "error": details,
                    "latency_ms": elapsed_ms,
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        return result.returncode

    answer = structured_answer or strip_internal_worklog(stdout) or "Пустой ответ. Переформулируй запрос."
    result_path.write_text(
        json.dumps(
            {
                "ok": True,
                "answer": truncate_text(answer, 12000),
                "latency_ms": elapsed_ms,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return 0


def main() -> int:
    if len(sys.argv) != 3:
        print("usage: enterprise_worker.py <task.json> <result.json>", file=sys.stderr)
        return 2
    task_path = Path(sys.argv[1]).resolve()
    result_path = Path(sys.argv[2]).resolve()
    return run_task(task_path, result_path)


if __name__ == "__main__":
    raise SystemExit(main())
