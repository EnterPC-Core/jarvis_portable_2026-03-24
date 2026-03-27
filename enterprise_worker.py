import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional


WORKER_PROTECTED_PATHS = (
    "run_jarvis_supervisor.sh",
    "enterprise_worker.py",
    ".env",
    "/home/userland/.profile",
    "/home/userland/bin/autostart_jarvis_bot.sh",
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
        text = normalize_whitespace(str(item.get("text") or ""))
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
    approval_policy = payload.get("approval_policy")
    command.append("exec")
    sandbox_mode = payload.get("sandbox_mode")
    if approval_policy == "never" and sandbox_mode == "danger-full-access":
        command.append("--dangerously-bypass-approvals-and-sandbox")
    elif approval_policy in {"never", "on-request"} and sandbox_mode == "workspace-write":
        command.append("--full-auto")
    if payload.get("json_output"):
        command.append("--json")
    command.append("--skip-git-repo-check")
    if sandbox_mode:
        command.extend(["--sandbox", sandbox_mode])
    image_path = payload.get("image_path")
    if image_path:
        command.extend(["-i", str(image_path)])
    return command


def protect_prompt(prompt: str) -> str:
    protected = "\n".join(f"- {path}" for path in WORKER_PROTECTED_PATHS)
    return (
        "ВАЖНО: этот worker изолирован от управляющего Telegram bridge.\n"
        "Запрещено изменять или ломать защищённые файлы управляющего слоя.\n"
        "Если задача просит трогать их, откажись и объясни, что это защищённый слой.\n\n"
        "Защищённые пути:\n"
        f"{protected}\n\n"
        "Можно работать по остальному workspace в рамках задачи.\n\n"
        f"{prompt}"
    )


def run_task(task_path: Path, result_path: Path) -> int:
    payload = json.loads(task_path.read_text(encoding="utf-8"))
    prompt = protect_prompt(payload.get("prompt") or "")
    timeout = int(payload.get("codex_timeout") or 180)
    progress_path_raw = str(payload.get("progress_path") or "").strip()
    progress_path = Path(progress_path_raw) if progress_path_raw else None
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
                progress_text = format_json_progress_event(json_payload)
                append_progress_event(progress_path, progress_text)
                item = json_payload.get("item") or {}
                if str(json_payload.get("type") or "") == "item.completed" and str(item.get("type") or "") == "agent_message":
                    text = normalize_whitespace(str(item.get("text") or ""))
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

    answer = structured_answer or stdout or "Пустой ответ. Переформулируй запрос."
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
