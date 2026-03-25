import json
import os
import subprocess
import sys
import time
from pathlib import Path


WORKER_PROTECTED_PATHS = (
    "tg_codex_bridge.py",
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


def build_subprocess_env() -> dict:
    env = os.environ.copy()
    env.setdefault("PYTHONUNBUFFERED", "1")
    return env


def build_command(payload: dict) -> list:
    command = ["codex"]
    approval_policy = payload.get("approval_policy")
    if approval_policy:
        command.extend(["-a", approval_policy])
    command.append("exec")
    if payload.get("json_output"):
        command.append("--json")
    command.append("--skip-git-repo-check")
    sandbox_mode = payload.get("sandbox_mode")
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
    command = build_command(payload)
    stdin_command = command + ["-"]
    started_at = time.perf_counter()

    try:
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

    answer = stdout or "Пустой ответ. Переформулируй запрос."
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
