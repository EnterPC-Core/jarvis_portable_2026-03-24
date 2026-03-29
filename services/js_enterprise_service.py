from __future__ import annotations

import json
import re
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


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
    enterprise_worker_path: Optional[Path] = None
    enterprise_server_base_url: str = "http://127.0.0.1:8766"
    register_pending_job_func: Optional[Callable[[dict], None]] = None
    update_pending_job_func: Optional[Callable[..., None]] = None
    clear_pending_job_func: Optional[Callable[[str], None]] = None


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

    def _build_payload(
        self,
        *,
        chat_id: int = 0,
        prompt: str,
        image_path: Optional[Path],
        sandbox_mode: Optional[str],
        approval_policy: Optional[str],
        json_output: bool,
        timeout_seconds: Optional[int],
    ) -> Dict[str, object]:
        return {
            "chat_id": int(chat_id or 0),
            "prompt": prompt,
            "image_path": str(image_path) if image_path is not None else "",
            "sandbox_mode": sandbox_mode,
            "approval_policy": approval_policy,
            "json_output": json_output,
            "codex_timeout": timeout_seconds if timeout_seconds is not None else self.deps.codex_timeout,
        }

    def _post_json(self, path: str, payload: Dict[str, object], timeout: Optional[int]) -> dict:
        base_url = self.deps.enterprise_server_base_url.rstrip("/")
        raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        request = Request(
            f"{base_url}{path}",
            data=raw,
            headers={"Content-Type": "application/json; charset=utf-8"},
            method="POST",
        )
        with urlopen(request, timeout=timeout or self.deps.codex_timeout or 180) as response:
            return json.loads(response.read().decode("utf-8"))

    def _get_json(self, path: str, timeout: Optional[int]) -> dict:
        base_url = self.deps.enterprise_server_base_url.rstrip("/")
        with urlopen(f"{base_url}{path}", timeout=timeout or self.deps.codex_timeout or 180) as response:
            return json.loads(response.read().decode("utf-8"))

    def get_runtime_status(self) -> Optional[Dict[str, object]]:
        try:
            payload = self._get_json("/api/runtime/status", 15)
        except Exception as error:
            self.deps.log_func(f"не удалось получить runtime status Enterprise: {error}")
            return None
        return dict(payload)

    def restart_bridge_runtime(self) -> Optional[Dict[str, object]]:
        try:
            payload = self._post_json("/api/runtime/restart_bridge", {}, 60)
        except Exception as error:
            self.deps.log_func(f"не удалось перезапустить bridge через Enterprise: {error}")
            return None
        return dict(payload)

    def start_remote_job(self, *, chat_id: int, prompt: str, timeout_seconds: Optional[int]) -> str:
        payload = self._build_payload(
            chat_id=chat_id,
            prompt=prompt,
            image_path=None,
            sandbox_mode="danger-full-access",
            approval_policy="never",
            json_output=True,
            timeout_seconds=timeout_seconds,
        )
        response = self._post_json("/api/jobs", payload, 15)
        return str(response.get("job_id") or "")

    def get_remote_job_snapshot(self, job_id: str) -> Optional[Dict[str, object]]:
        try:
            payload = self._get_json(f"/api/jobs/{job_id}", 15)
        except HTTPError as error:
            if error.code == 404:
                return None
            self.deps.log_func(f"не удалось получить snapshot Enterprise job={job_id}: {error}")
            return None
        except Exception as error:
            self.deps.log_func(f"не удалось получить snapshot Enterprise job={job_id}: {error}")
            return None
        return dict(payload)

    def _read_remote_result(self, payload: dict) -> Tuple[bool, str]:
        answer = self.deps.normalize_whitespace_func(str(payload.get("answer") or ""))
        ok = bool(payload.get("ok"))
        if ok:
            return True, answer or "Пустой ответ. Переформулируй запрос."
        return False, answer or self.deps.jarvis_offline_text

    def _render_remote_events_text(self, initial_status: str, snapshot: Dict[str, object]) -> str:
        events = snapshot.get("events") or []
        if not isinstance(events, list) or not events:
            return initial_status
        lines = [self.deps.normalize_whitespace_func(str(item)) for item in events[-24:]]
        lines = [line for line in lines if line]
        if not lines:
            return initial_status
        return f"{initial_status}\n\n" + "\n".join(lines)

    def _render_remote_completion_text(self, initial_status: str, snapshot: Dict[str, object], answer: str) -> str:
        base = self._render_remote_events_text(initial_status, snapshot)
        if answer in {self.deps.jarvis_offline_text}:
            tail = "✖ Завершение\n└ Enterprise сейчас недоступен"
        elif answer == self.deps.upgrade_timeout_text or answer.startswith("Слишком долгий ответ."):
            tail = "⌛ Завершение\n└ Время ожидания вышло"
        elif answer.startswith("Ошибка Enterprise Core:"):
            tail = "⚠ Завершение\n└ Выполнение завершилось с ошибкой"
        else:
            tail = "✔ Завершение\n└ Выполнение завершено"
        return f"{base}\n{tail}".strip()

    def _stepwise_events_snapshot(
        self,
        snapshot: Dict[str, object],
        displayed_events: List[str],
    ) -> Dict[str, object]:
        raw_events = snapshot.get("events") or []
        if not isinstance(raw_events, list):
            return snapshot
        normalized_events = [self.deps.normalize_whitespace_func(str(item)) for item in raw_events]
        normalized_events = [item for item in normalized_events if item]
        if len(displayed_events) < len(normalized_events):
            next_event = normalized_events[len(displayed_events)]
            displayed_events.append(next_event)
        limited_snapshot = dict(snapshot)
        limited_snapshot["events"] = displayed_events[-24:]
        return limited_snapshot

    def _wrap_rerouted_answer(self, *, source_chat_id: int, delivery_chat_id: Optional[int], answer: str) -> str:
        if delivery_chat_id in {None, 0, source_chat_id}:
            return answer
        return f"Отчёт из чата {source_chat_id}:\n\n{answer}"

    def wait_for_job(
        self,
        *,
        job_id: str,
        chat_id: int,
        progress_chat_id: int,
        initial_status: str,
        status_message_id: Optional[int],
        effective_timeout: Optional[int],
        progress_style: str,
        replace_status_with_answer: bool,
        target_label: str,
        delivery_chat_id: Optional[int],
        postprocess: bool,
        approval_policy: Optional[str],
        sandbox_mode: Optional[str],
        clear_pending_on_finish: bool = False,
    ) -> str:
        phase_index = 0
        next_update_at = 0.0
        started_at = time.perf_counter()
        snapshot: Dict[str, object] = {}
        displayed_events: List[str] = []
        while True:
            elapsed = int(max(1, time.perf_counter() - started_at))
            try:
                snapshot = self._get_json(f"/api/jobs/{job_id}", 15)
            except HTTPError as error:
                if error.code == 404:
                    lost_answer = (
                        "Задача оборвалась во время рестарта: Enterprise больше не видит этот job_id. "
                        "Нужен повторный запуск."
                    )
                    lost_answer = self._wrap_rerouted_answer(
                        source_chat_id=chat_id,
                        delivery_chat_id=delivery_chat_id,
                        answer=lost_answer,
                    )
                    if status_message_id is not None:
                        self.deps.edit_status_message_func(
                            progress_chat_id,
                            status_message_id,
                            f"{initial_status}\n\n⚠ Завершение\n└ Задача потеряна после рестарта",
                        )
                    if self.deps.update_pending_job_func is not None:
                        self.deps.update_pending_job_func(
                            job_id,
                            status="lost",
                            verification_state="failed",
                            outcome="error",
                            error_text="enterprise job snapshot not found after restart",
                            phase="job_wait",
                            detail="enterprise job snapshot missing after restart",
                        )
                    if clear_pending_on_finish and self.deps.clear_pending_job_func is not None:
                        self.deps.clear_pending_job_func(job_id)
                    return lost_answer
                raise
            if bool(snapshot.get("done")):
                break
            now = time.perf_counter()
            if now >= next_update_at:
                self.deps.send_chat_action_func(progress_chat_id, "typing")
                if status_message_id is not None:
                    render_snapshot = self._stepwise_events_snapshot(snapshot, displayed_events)
                    self.deps.edit_status_message_func(
                        progress_chat_id,
                        status_message_id,
                        self._render_remote_events_text(initial_status, render_snapshot),
                    )
                phase_index += 1
                next_update_at = now + self.deps.progress_update_seconds
            if effective_timeout is not None and elapsed >= effective_timeout:
                self.deps.log_func(
                    "таймаут ожидания Enterprise "
                    f"chat={chat_id} progress_chat={progress_chat_id} timeout={effective_timeout} style={progress_style}"
                )
                if status_message_id is not None:
                    self.deps.edit_status_message_func(
                        progress_chat_id,
                        status_message_id,
                        f"{initial_status}\n\nПревышено время ожидания: {effective_timeout} сек.",
                    )
                if self.deps.update_pending_job_func is not None:
                    self.deps.update_pending_job_func(
                        job_id,
                        status="timed_out",
                        verification_state="failed",
                        outcome="timeout",
                        error_text=f"enterprise wait timeout after {effective_timeout} seconds",
                        phase="job_wait",
                        detail="enterprise wait timed out",
                    )
                if approval_policy == "never" and sandbox_mode == "workspace-write":
                    return self.deps.upgrade_timeout_text
                return "Слишком долгий ответ. Повтори короче или уточни запрос."
            time.sleep(0.5)
        result_code = int(snapshot.get("exit_code") or 0)
        stderr = self.deps.normalize_whitespace_func(str(snapshot.get("error") or ""))
        ok, answer = self._read_remote_result(snapshot)
        if result_code != 0 and not ok:
                self.deps.log_func(
                    self.deps.shorten_for_log_func(
                    f"ошибка Enterprise chat={chat_id} rc={result_code} stderr={stderr}",
                    600,
                )
            )
        if ok:
            answer = answer if not postprocess else self.deps.postprocess_answer_func(answer, None)
        if self.deps.update_pending_job_func is not None:
            self.deps.update_pending_job_func(
                job_id,
                status="completed" if ok else "failed",
                verification_state="tool_observed" if ok else "failed",
                outcome="ok" if ok else "error",
                evidence_text=answer if ok else "",
                error_text=stderr if not ok else "",
                phase="job_finished",
                detail="enterprise worker finished with usable answer" if ok else "enterprise worker failed",
            )
        if progress_style == "enterprise" and status_message_id is not None and not replace_status_with_answer:
            final_snapshot = dict(snapshot)
            raw_events = final_snapshot.get("events") or []
            if isinstance(raw_events, list):
                final_snapshot["events"] = [
                    self.deps.normalize_whitespace_func(str(item))
                    for item in raw_events
                    if self.deps.normalize_whitespace_func(str(item))
                ][-24:]
            self.deps.edit_status_message_func(
                progress_chat_id,
                status_message_id,
                self._render_remote_completion_text(initial_status, final_snapshot, answer),
            )
        else:
            self.deps.finish_progress_status_func(
                progress_chat_id,
                status_message_id,
                initial_status,
                answer,
                progress_style,
                replace_status_with_answer,
                target_label,
            )
        if clear_pending_on_finish and self.deps.clear_pending_job_func is not None:
            self.deps.clear_pending_job_func(job_id)
        return answer

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
        effective_timeout = self._resolve_timeout(None, self.deps.codex_timeout)
        try:
            result = self._post_json(
                "/api/run_sync",
                self._build_payload(
                    chat_id=0,
                    prompt=prompt,
                    image_path=image_path,
                    sandbox_mode=sandbox_mode,
                    approval_policy=approval_policy,
                    json_output=json_output,
                    timeout_seconds=effective_timeout,
                ),
                effective_timeout,
            )
            ok, answer = self._read_remote_result(result)
        except (OSError, URLError, subprocess.TimeoutExpired) as error:
            self.deps.log_func(f"не удалось связаться с Enterprise: {error}")
            return self.deps.jarvis_offline_text
        except TimeoutError:
            self.deps.log_func(f"таймаут Enterprise после {effective_timeout}s")
            return "Слишком долгий ответ. Повтори короче или уточни запрос."
        if not ok:
            self.deps.log_func(self.deps.shorten_for_log_func(f"Enterprise вернул ошибку: {answer}", 600))
        if ok:
            if not postprocess:
                return answer
            return self.deps.postprocess_answer_func(answer, None)
        return answer

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
        delivery_chat_id: Optional[int] = None,
        request_trace_id: str = "",
        task_kind: str = "",
        route_kind: str = "",
        persona: str = "",
        request_kind: str = "",
        user_id: Optional[int] = None,
        message_id: Optional[int] = None,
        summary: str = "",
    ) -> str:
        progress_chat_id = int(delivery_chat_id or chat_id or 0)
        if progress_chat_id == 0:
            progress_chat_id = chat_id
        if show_status_message and status_message_id is None:
            status_message_id = self.deps.send_status_message_func(progress_chat_id, initial_status)
        effective_timeout = self._resolve_timeout(timeout_seconds, self.deps.codex_timeout)

        try:
            with self.deps.heartbeat_guard_factory():
                create_response = self._post_json(
                    "/api/jobs",
                    self._build_payload(
                        chat_id=chat_id,
                        prompt=prompt,
                        image_path=image_path,
                        sandbox_mode=sandbox_mode,
                        approval_policy=approval_policy,
                        json_output=json_output,
                        timeout_seconds=effective_timeout,
                    ),
                    15,
                )
                job_id = str(create_response.get("job_id") or "")
                if not job_id:
                    raise OSError("Enterprise не вернул идентификатор задачи")
                if self.deps.register_pending_job_func is not None:
                    self.deps.register_pending_job_func(
                        {
                            "job_id": job_id,
                            "chat_id": chat_id,
                            "user_id": int(user_id or 0),
                            "message_id": int(message_id or 0),
                            "progress_chat_id": progress_chat_id,
                            "status_message_id": status_message_id,
                            "initial_status": initial_status,
                            "progress_style": progress_style,
                            "replace_status_with_answer": replace_status_with_answer,
                            "target_label": target_label,
                            "delivery_chat_id": int(delivery_chat_id or 0),
                            "postprocess": postprocess,
                            "approval_policy": approval_policy or "",
                            "sandbox_mode": sandbox_mode or "",
                            "timeout_seconds": effective_timeout or 0,
                            "request_trace_id": request_trace_id,
                            "task_kind": task_kind or "enterprise_job",
                            "route_kind": route_kind,
                            "persona": persona,
                            "request_kind": request_kind,
                            "summary": summary or self.deps.shorten_for_log_func(prompt, 280),
                        }
                    )
                return self.wait_for_job(
                    job_id=job_id,
                    chat_id=chat_id,
                    progress_chat_id=progress_chat_id,
                    initial_status=initial_status,
                    status_message_id=status_message_id,
                    effective_timeout=effective_timeout,
                    progress_style=progress_style,
                    replace_status_with_answer=replace_status_with_answer,
                    target_label=target_label,
                    delivery_chat_id=delivery_chat_id,
                    postprocess=postprocess,
                    approval_policy=approval_policy,
                    sandbox_mode=sandbox_mode,
                )
        except (OSError, URLError) as error:
            self.deps.log_func(f"не удалось связаться с Enterprise во время выполнения: {error}")
            if status_message_id is not None:
                self.deps.edit_status_message_func(
                    progress_chat_id,
                    status_message_id,
                    f"{initial_status}\n\nНе удалось запустить Enterprise Core.",
                )
            return self.deps.jarvis_offline_text
        return self.deps.jarvis_offline_text

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
