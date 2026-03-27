from __future__ import annotations

import json
import re
import subprocess
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, List, Optional


@dataclass(frozen=True)
class JSEnterpriseServiceDeps:
    build_codex_command_func: Callable[..., List[str]]
    build_subprocess_env_func: Callable[[], dict]
    heartbeat_guard_factory: Callable[[], object]
    normalize_whitespace_func: Callable[[str], str]
    postprocess_answer_func: Callable[[str, Optional[int]], str]
    build_codex_failure_answer_func: Callable[..., str]
    extract_usable_codex_stdout_func: Callable[[str], str]
    shorten_for_log_func: Callable[[str, int], str]
    log_func: Callable[[str], None]
    send_chat_action_func: Callable[[int, str], None]
    send_status_message_func: Callable[[int, str], Optional[int]]
    edit_status_message_func: Callable[[int, int, str], bool]
    update_progress_status_func: Callable[[int, Optional[int], str, int, int, str, str], None]
    finish_progress_status_func: Callable[[int, Optional[int], str, str, str, bool, str], None]
    codex_timeout: Optional[int]
    progress_update_seconds: float
    jarvis_offline_text: str
    upgrade_timeout_text: str


class JSEnterpriseService:
    """Thin Enterprise execution service used by the bridge."""

    def __init__(self, deps: JSEnterpriseServiceDeps) -> None:
        self.deps = deps

    @staticmethod
    def _resolve_timeout(timeout_seconds: Optional[int], fallback_timeout: Optional[int]) -> Optional[int]:
        if timeout_seconds is None:
            return fallback_timeout
        if timeout_seconds <= 0:
            return None
        return timeout_seconds

    def run(
        self,
        prompt: str,
        *,
        image_path: Optional[Path] = None,
        sandbox_mode: Optional[str] = None,
        approval_policy: Optional[str] = None,
        json_output: bool = False,
        postprocess: bool = True,
    ) -> str:
        command = self.deps.build_codex_command_func(
            image_path=image_path,
            sandbox_mode=sandbox_mode,
            approval_policy=approval_policy,
            json_output=json_output,
        )
        started_at = time.perf_counter()
        try:
            result = subprocess.run(
                command + ["-"],
                input=prompt,
                capture_output=True,
                text=True,
                timeout=self.deps.codex_timeout,
                env=self.deps.build_subprocess_env_func(),
            )
        except OSError as error:
            self.deps.log_func(f"failed to start codex: {error}")
            return self.deps.jarvis_offline_text
        except subprocess.TimeoutExpired:
            self.deps.log_func(f"codex timeout after {self.deps.codex_timeout}s")
            return "Слишком долгий ответ. Повтори короче или уточни запрос."

        stdout = self.deps.normalize_whitespace_func(result.stdout or "")
        stderr = self.deps.normalize_whitespace_func(result.stderr or "")
        if result.returncode != 0 and "No prompt provided" in stderr:
            self.deps.log_func("codex stdin prompt rejected, retrying with prompt argument")
            try:
                result = subprocess.run(
                    command + [prompt],
                    capture_output=True,
                    text=True,
                    timeout=self.deps.codex_timeout,
                    env=self.deps.build_subprocess_env_func(),
                )
            except (OSError, subprocess.TimeoutExpired) as error:
                self.deps.log_func(f"failed to restart codex with prompt argument: {error}")
                return self.deps.jarvis_offline_text
            stdout = self.deps.normalize_whitespace_func(result.stdout or "")
            stderr = self.deps.normalize_whitespace_func(result.stderr or "")

        return self._finalize_result(
            stdout=stdout,
            stderr=stderr,
            returncode=result.returncode,
            started_at=started_at,
            sandbox_mode=sandbox_mode,
            approval_policy=approval_policy,
            postprocess=postprocess,
        )

    def run_with_progress(
        self,
        *,
        chat_id: int,
        prompt: str,
        initial_status: str,
        status_message_id: Optional[int] = None,
        image_path: Optional[Path] = None,
        sandbox_mode: Optional[str] = None,
        approval_policy: Optional[str] = None,
        json_output: bool = False,
        postprocess: bool = True,
        timeout_seconds: Optional[int] = None,
        progress_style: str = "jarvis",
        replace_status_with_answer: bool = False,
        show_status_message: bool = True,
        target_label: str = "",
    ) -> str:
        if json_output:
            return self._run_with_json_progress(
                chat_id=chat_id,
                prompt=prompt,
                initial_status=initial_status,
                status_message_id=status_message_id,
                image_path=image_path,
                sandbox_mode=sandbox_mode,
                approval_policy=approval_policy,
                postprocess=postprocess,
                timeout_seconds=timeout_seconds,
                replace_status_with_answer=replace_status_with_answer,
            )
        if show_status_message and status_message_id is None:
            status_message_id = self.deps.send_status_message_func(chat_id, initial_status)
        command = self.deps.build_codex_command_func(
            image_path=image_path,
            sandbox_mode=sandbox_mode,
            approval_policy=approval_policy,
            json_output=json_output,
        )
        stdin_command = command + ["-"]
        started_at = time.perf_counter()
        effective_timeout = self._resolve_timeout(timeout_seconds, self.deps.codex_timeout)

        try:
            with self.deps.heartbeat_guard_factory():
                with tempfile.TemporaryFile(mode="w+t", encoding="utf-8") as stdout_handle, tempfile.TemporaryFile(mode="w+t", encoding="utf-8") as stderr_handle:
                    process = subprocess.Popen(
                        stdin_command,
                        stdin=subprocess.PIPE,
                        stdout=stdout_handle,
                        stderr=stderr_handle,
                        text=True,
                        env=self.deps.build_subprocess_env_func(),
                    )
                    assert process.stdin is not None
                    process.stdin.write(prompt)
                    process.stdin.close()

                    phase_index = 0
                    next_update_at = 0.0
                    while True:
                        return_code = process.poll()
                        elapsed = int(max(1, time.perf_counter() - started_at))
                        if return_code is not None:
                            break
                        now = time.perf_counter()
                        if now >= next_update_at:
                            self.deps.send_chat_action_func(chat_id, "typing")
                            self.deps.update_progress_status_func(
                                chat_id,
                                status_message_id,
                                initial_status,
                                elapsed,
                                phase_index,
                                progress_style,
                                target_label,
                            )
                            phase_index += 1
                            next_update_at = now + self.deps.progress_update_seconds
                        if effective_timeout is not None and elapsed >= effective_timeout:
                            process.kill()
                            process.wait(timeout=5)
                            self.deps.log_func(
                                "codex progress timeout "
                                f"chat={chat_id} timeout={effective_timeout} progress_style={progress_style}"
                            )
                            if status_message_id is not None:
                                self.deps.edit_status_message_func(
                                    chat_id,
                                    status_message_id,
                                    f"{initial_status}\n\nПревышено время ожидания: {effective_timeout} сек.",
                                )
                            if approval_policy == "never" and sandbox_mode == "workspace-write":
                                return self.deps.upgrade_timeout_text
                            return "Слишком долгий ответ. Повтори короче или уточни запрос."
                        time.sleep(0.5)

                    stdout_handle.seek(0)
                    stderr_handle.seek(0)
                    stdout = self.deps.normalize_whitespace_func(stdout_handle.read() or "")
                    stderr = self.deps.normalize_whitespace_func(stderr_handle.read() or "")
                    result_code = process.returncode or 0
        except OSError as error:
            self.deps.log_func(f"failed to start codex with progress: {error}")
            if status_message_id is not None:
                self.deps.edit_status_message_func(
                    chat_id,
                    status_message_id,
                    f"{initial_status}\n\nНе удалось запустить Enterprise Core.",
                )
            return self.deps.jarvis_offline_text

        if result_code != 0 and "No prompt provided" in stderr:
            self.deps.log_func("codex stdin prompt rejected during progress run, retrying with prompt argument")
            return self._retry_with_progress(
                chat_id=chat_id,
                status_message_id=status_message_id,
                initial_status=initial_status,
                command=command + [prompt],
                sandbox_mode=sandbox_mode,
                approval_policy=approval_policy,
                postprocess=postprocess,
                timeout_seconds=effective_timeout,
                progress_style=progress_style,
                replace_status_with_answer=replace_status_with_answer,
                target_label=target_label,
            )

        answer = self._finalize_result(
            stdout=stdout,
            stderr=stderr,
            returncode=result_code,
            started_at=started_at,
            sandbox_mode=sandbox_mode,
            approval_policy=approval_policy,
            postprocess=postprocess,
        )
        self.deps.finish_progress_status_func(
            chat_id,
            status_message_id,
            initial_status,
            answer,
            progress_style,
            replace_status_with_answer,
            target_label,
        )
        return answer

    def _render_live_event_text(self, initial_status: str, events: List[str]) -> str:
        if not events:
            return initial_status
        body = "\n".join(events[-24:])
        return f"{initial_status}\n\n{body}"

    def _render_live_completion_text(self, initial_status: str, events: List[str], answer: str) -> str:
        base = self._render_live_event_text(initial_status, events)
        if answer in {self.deps.jarvis_offline_text, self.deps.upgrade_timeout_text}:
            tail = "✖ Завершено с проблемой."
        elif answer.startswith("Слишком долгий ответ.") or answer.startswith("Ошибка Enterprise Core:"):
            tail = "⚠ Завершено с ошибкой."
        else:
            tail = "✔ Выполнение завершено."
        return f"{base}\n\n{tail}".strip()

    def _append_live_event(self, events: List[str], text: str) -> None:
        clean = self.deps.normalize_whitespace_func(text)
        if not clean:
            return
        if events and events[-1] == clean:
            return
        events.append(clean)

    def _classify_exec_title(self, title: str) -> str:
        lowered = title.lower()
        if any(token in lowered for token in ("apply_patch", "write", "update file", "add file", "edit", "patch")):
            return f"• Изменяю\n  └ {title}"
        if any(token in lowered for token in ("rg ", "rg --", "find ", "glob", "search", "grep ", "ls ", "tree", "fd ")):
            return f"• Ищу\n  └ {title}"
        if any(token in lowered for token in ("cat ", "sed ", "head ", "tail ", "read ", "open ")):
            return f"• Читаю\n  └ {title}"
        if any(token in lowered for token in ("python3 -m py_compile", "pytest", "test", "verify", "check")):
            return f"• Проверяю\n  └ {title}"
        return f"• Выполняю\n  └ {title}"

    def _format_json_event(self, payload: dict) -> Optional[str]:
        event_type = str(payload.get("type") or "")
        if event_type == "thread.started":
            return "• Старт\n  └ Сессия Enterprise Core запущена"
        if event_type == "turn.started":
            return "• Начинаю\n  └ Запрос принят в работу"
        if event_type == "turn.completed":
            return "• Завершаю\n  └ Ход выполнения завершён"
        item = payload.get("item") or {}
        item_type = str(item.get("type") or "")
        if event_type == "item.completed":
            if item_type == "exec_command":
                title = self.deps.normalize_whitespace_func(str(item.get("title") or item.get("command") or "команда"))
                return self._classify_exec_title(title)
            if item_type == "agent_message":
                text = self.deps.normalize_whitespace_func(str(item.get("text") or ""))
                if text:
                    short = re.sub(r"\s+", " ", text).strip()
                    return f"• Комментарий\n  └ {short[:220]}"
            title = self.deps.normalize_whitespace_func(str(item.get("title") or item.get("name") or ""))
            if title:
                return f"• Шаг завершён\n  └ {title}"
        return None

    def _run_with_json_progress(
        self,
        *,
        chat_id: int,
        prompt: str,
        initial_status: str,
        status_message_id: Optional[int],
        image_path: Optional[Path],
        sandbox_mode: Optional[str],
        approval_policy: Optional[str],
        postprocess: bool,
        timeout_seconds: Optional[int],
        replace_status_with_answer: bool,
    ) -> str:
        if status_message_id is None:
            status_message_id = self.deps.send_status_message_func(chat_id, initial_status)
        command = self.deps.build_codex_command_func(
            image_path=image_path,
            sandbox_mode=sandbox_mode,
            approval_policy=approval_policy,
            json_output=True,
        )
        started_at = time.perf_counter()
        effective_timeout = self._resolve_timeout(timeout_seconds, self.deps.codex_timeout)
        events: List[str] = []
        final_answer_text = ""
        stderr_parts: List[str] = []
        try:
            with self.deps.heartbeat_guard_factory():
                process = subprocess.Popen(
                    command + ["-"],
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    env=self.deps.build_subprocess_env_func(),
                    bufsize=1,
                )
                assert process.stdin is not None
                process.stdin.write(prompt)
                process.stdin.close()

                next_edit_at = 0.0
                while True:
                    elapsed = int(max(1, time.perf_counter() - started_at))
                    if effective_timeout is not None and elapsed >= effective_timeout:
                        process.kill()
                        process.wait(timeout=5)
                        if status_message_id is not None:
                            self.deps.edit_status_message_func(chat_id, status_message_id, f"{initial_status}\n\nПревышено время ожидания: {effective_timeout} сек.")
                        return "Слишком долгий ответ. Повтори короче или уточни запрос."
                    if process.stdout is None:
                        break
                    line = process.stdout.readline()
                    if not line:
                        if process.poll() is not None:
                            break
                        time.sleep(0.1)
                        continue
                    raw_line = (line or "").strip()
                    if not raw_line:
                        continue
                    try:
                        payload = json.loads(raw_line)
                    except json.JSONDecodeError:
                        continue
                    event_text = self._format_json_event(payload)
                    if event_text:
                        self._append_live_event(events, event_text)
                    item = payload.get("item") or {}
                    if str(payload.get("type") or "") == "item.completed" and str(item.get("type") or "") == "agent_message":
                        text = self.deps.normalize_whitespace_func(str(item.get("text") or ""))
                        if text:
                            final_answer_text = text
                    now = time.perf_counter()
                    if status_message_id is not None and now >= next_edit_at:
                        self.deps.edit_status_message_func(chat_id, status_message_id, self._render_live_event_text(initial_status, events))
                        next_edit_at = now + self.deps.progress_update_seconds

                stderr_text = ""
                if process.stderr is not None:
                    stderr_text = self.deps.normalize_whitespace_func(process.stderr.read() or "")
                    if stderr_text:
                        stderr_parts.append(stderr_text)
                process.wait()
                stdout = final_answer_text.strip()
                stderr = "\n".join(stderr_parts).strip()
                answer = self._finalize_result(
                    stdout=stdout,
                    stderr=stderr,
                    returncode=process.returncode or 0,
                    started_at=started_at,
                    sandbox_mode=sandbox_mode,
                    approval_policy=approval_policy,
                    postprocess=postprocess,
                )
        except OSError as error:
            self.deps.log_func(f"failed to start codex with json progress: {error}")
            if status_message_id is not None:
                self.deps.edit_status_message_func(chat_id, status_message_id, f"{initial_status}\n\nНе удалось запустить Enterprise Core.")
            return self.deps.jarvis_offline_text

        if status_message_id is not None and not replace_status_with_answer:
            self.deps.edit_status_message_func(
                chat_id,
                status_message_id,
                self._render_live_completion_text(initial_status, events, answer),
            )
        else:
            self.deps.finish_progress_status_func(
                chat_id,
                status_message_id,
                initial_status,
                answer,
                "enterprise",
                replace_status_with_answer,
                "",
            )
        return answer

    def _retry_with_progress(
        self,
        *,
        chat_id: int,
        status_message_id: Optional[int],
        initial_status: str,
        command: List[str],
        sandbox_mode: Optional[str],
        approval_policy: Optional[str],
        postprocess: bool,
        timeout_seconds: Optional[int],
        progress_style: str,
        replace_status_with_answer: bool,
        target_label: str,
    ) -> str:
        started_at = time.perf_counter()
        try:
            with self.deps.heartbeat_guard_factory():
                with tempfile.TemporaryFile(mode="w+t", encoding="utf-8") as stdout_handle, tempfile.TemporaryFile(mode="w+t", encoding="utf-8") as stderr_handle:
                    process = subprocess.Popen(
                        command,
                        stdout=stdout_handle,
                        stderr=stderr_handle,
                        text=True,
                        env=self.deps.build_subprocess_env_func(),
                    )
                    phase_index = 0
                    next_update_at = 0.0
                    while True:
                        return_code = process.poll()
                        elapsed = int(max(1, time.perf_counter() - started_at))
                        if return_code is not None:
                            break
                        now = time.perf_counter()
                        if now >= next_update_at:
                            self.deps.send_chat_action_func(chat_id, "typing")
                            self.deps.update_progress_status_func(
                                chat_id,
                                status_message_id,
                                initial_status,
                                elapsed,
                                phase_index,
                                progress_style,
                                target_label,
                            )
                            phase_index += 1
                            next_update_at = now + self.deps.progress_update_seconds
                        if timeout_seconds is not None and elapsed >= timeout_seconds:
                            process.kill()
                            process.wait(timeout=5)
                            self.deps.log_func(
                                "codex retry progress timeout "
                                f"chat={chat_id} timeout={timeout_seconds} progress_style={progress_style}"
                            )
                            if status_message_id is not None:
                                self.deps.edit_status_message_func(
                                    chat_id,
                                    status_message_id,
                                    f"{initial_status}\n\nПревышено время ожидания: {timeout_seconds} сек.",
                                )
                            if approval_policy == "never" and sandbox_mode == "workspace-write":
                                return self.deps.upgrade_timeout_text
                            return "Слишком долгий ответ. Повтори короче или уточни запрос."
                        time.sleep(0.5)

                    stdout_handle.seek(0)
                    stderr_handle.seek(0)
                    stdout = self.deps.normalize_whitespace_func(stdout_handle.read() or "")
                    stderr = self.deps.normalize_whitespace_func(stderr_handle.read() or "")
                    result_code = process.returncode or 0
        except OSError as error:
            self.deps.log_func(f"failed to restart codex with prompt argument during progress run: {error}")
            if status_message_id is not None:
                self.deps.edit_status_message_func(
                    chat_id,
                    status_message_id,
                    f"{initial_status}\n\nНе удалось повторно запустить Enterprise Core.",
                )
            return self.deps.jarvis_offline_text

        answer = self._finalize_result(
            stdout=stdout,
            stderr=stderr,
            returncode=result_code,
            started_at=started_at,
            sandbox_mode=sandbox_mode,
            approval_policy=approval_policy,
            postprocess=postprocess,
        )
        self.deps.finish_progress_status_func(
            chat_id,
            status_message_id,
            initial_status,
            answer,
            progress_style,
            replace_status_with_answer,
            target_label,
        )
        return answer

    def _finalize_result(
        self,
        *,
        stdout: str,
        stderr: str,
        returncode: int,
        started_at: float,
        sandbox_mode: Optional[str],
        approval_policy: Optional[str],
        postprocess: bool,
    ) -> str:
        if returncode != 0:
            details = stderr or stdout or "Движок Enterprise Core завершился с ошибкой без вывода."
            usable_stdout = self.deps.extract_usable_codex_stdout_func(stdout)
            if usable_stdout:
                self.deps.log_func(
                    f"codex degraded code={returncode} recovered_from_stdout=yes "
                    f"stderr={self.deps.shorten_for_log_func(stderr, 220)}"
                )
                latency_ms = max(1, int((time.perf_counter() - started_at) * 1000))
                return self.deps.postprocess_answer_func(usable_stdout, latency_ms) if postprocess else usable_stdout
            answer = self.deps.build_codex_failure_answer_func(
                details,
                sandbox_mode=sandbox_mode,
                approval_policy=approval_policy,
            )
            self.deps.log_func(
                f"codex degraded code={returncode} recovered_from_stdout=no "
                f"stderr={self.deps.shorten_for_log_func(stderr, 220)}"
            )
            return answer

        if not stdout:
            self.deps.log_func("codex returned empty stdout")
            return "Пустой ответ. Переформулируй запрос."

        latency_ms = max(1, int((time.perf_counter() - started_at) * 1000))
        return self.deps.postprocess_answer_func(stdout, latency_ms) if postprocess else stdout
