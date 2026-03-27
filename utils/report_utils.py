import os
import re
import shutil
import subprocess
import time
import warnings
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple
from zoneinfo import ZoneInfo


def render_event_rows(
    rows: List[Tuple[int, Optional[int], str, str, str, str, str, str]],
    title: str,
    build_actor_name_func: Callable[[Optional[int], str, str, str, str], str],
    truncate_text_func: Callable[[str, int], str],
) -> str:
    lines = [title]
    for created_at, user_id, username, first_name, last_name, role, message_type, content in rows:
        stamp = datetime.fromtimestamp(created_at).strftime("%Y-%m-%d %H:%M:%S") if created_at else ""
        actor = build_actor_name_func(user_id, username, first_name, last_name, role)
        lines.append(f"[{stamp}] {actor} ({message_type}): {truncate_text_func(content, 280)}")
    return "\n".join(lines)


def render_timeline_rows(
    label: str,
    rows: List[Tuple[int, Optional[int], str, str, str, str, str]],
    truncate_text_func: Callable[[str, int], str],
) -> str:
    lines = [f"Timeline: {label}"]
    for created_at, user_id, username, first_name, last_name, message_type, content in rows:
        stamp = datetime.fromtimestamp(created_at).strftime("%Y-%m-%d %H:%M:%S") if created_at else ""
        lines.append(f"[{stamp}] ({message_type}) {truncate_text_func(content, 280)}")
    return "\n".join(lines)


def render_route_diagnostics_rows(rows: List[Any], truncate_text_func: Callable[[str, int], str]) -> str:
    if not rows:
        return "Route diagnostics пока пусты."
    lines = ["Route diagnostics"]
    for row in rows:
        stamp = datetime.fromtimestamp(int(row["created_at"] or 0)).strftime("%m-%d %H:%M") if row["created_at"] else "--:--"
        layers: List[str] = []
        if int(row["used_live"] or 0):
            layers.append("live")
        if int(row["used_web"] or 0):
            layers.append("web")
        if int(row["used_events"] or 0):
            layers.append("events")
        if int(row["used_database"] or 0):
            layers.append("db")
        if int(row["used_reply"] or 0):
            layers.append("reply")
        if int(row["used_workspace"] or 0):
            layers.append("workspace")
        layers_text = ",".join(layers) if layers else "base"
        lines.append(
            f"- [{stamp}] chat={int(row['chat_id'])} persona={row['persona'] or '-'} "
            f"intent={row['intent'] or '-'} route={row['route_kind'] or '-'} "
            f"source={row['source_label'] or '-'} outcome={row['outcome'] or '-'} "
            f"latency={int(row['latency_ms'] or 0)}ms layers={layers_text}"
        )
        if row["query_text"]:
            lines.append(f"  {truncate_text_func(row['query_text'], 180)}")
    return "\n".join(lines)


def render_resource_summary(
    *,
    psutil_module: Any,
    format_bytes_func: Callable[[int], str],
    format_swap_line_func: Callable[[], str],
    extract_meminfo_value_func: Callable[[str, str], Optional[int]],
    display_timezone: ZoneInfo,
) -> str:
    lines = ["Ресурсы системы"]
    lines.append(f"Время: {datetime.now(display_timezone).strftime('%Y-%m-%d %H:%M:%S %Z')}")
    try:
        with open("/proc/loadavg", "r", encoding="utf-8") as handle:
            lines.append(f"Средняя нагрузка: {handle.read().strip()}")
    except OSError:
        pass
    if psutil_module is not None:
        vm = psutil_module.virtual_memory()
        cpu_percent = psutil_module.cpu_percent(interval=0.5)
        boot_time = datetime.fromtimestamp(psutil_module.boot_time(), tz=display_timezone).strftime("%Y-%m-%d %H:%M:%S %Z")
        lines.append(f"CPU: {cpu_percent:.1f}%")
        lines.append(f"RAM: {vm.percent:.1f}% ({format_bytes_func(vm.used)} / {format_bytes_func(vm.total)})")
        lines.append(f"Swap: {format_swap_line_func()}")
        lines.append(
            f"Ядра CPU: logical={psutil_module.cpu_count()} physical={psutil_module.cpu_count(logical=False) or 'n/a'}"
        )
        lines.append(f"Время запуска системы: {boot_time}")
    else:
        lines.append("psutil не установлен, показываю только базовые данные из /proc.")
        try:
            with open("/proc/meminfo", "r", encoding="utf-8") as handle:
                meminfo = handle.read()
            total = extract_meminfo_value_func(meminfo, "MemTotal")
            available = extract_meminfo_value_func(meminfo, "MemAvailable")
            if total and available is not None:
                used = max(0, total - available)
                percent = (used / total) * 100 if total else 0
                lines.append(f"RAM: {percent:.1f}% ({format_bytes_func(used * 1024)} / {format_bytes_func(total * 1024)})")
        except OSError:
            pass
    return "\n".join(lines)


def render_top_processes(
    *,
    psutil_module: Any,
    format_bytes_func: Callable[[int], str],
    truncate_text_func: Callable[[str, int], str],
    limit: int = 8,
) -> str:
    lines = ["Топ процессов"]
    if psutil_module is None:
        lines.append("psutil не установлен.")
        return "\n".join(lines)
    samples: List[Tuple[float, int, str, int, int]] = []
    for process in psutil_module.process_iter(["pid", "name", "memory_info"]):
        try:
            cpu = process.cpu_percent(interval=None)
            memory = process.info["memory_info"].rss if process.info.get("memory_info") else 0
            samples.append((cpu, process.info["pid"], process.info.get("name") or "unknown", memory, memory))
        except (psutil_module.NoSuchProcess, psutil_module.AccessDenied):
            continue
    time.sleep(0.3)
    samples = []
    for process in psutil_module.process_iter(["pid", "name", "memory_info"]):
        try:
            cpu = process.cpu_percent(interval=None)
            memory = process.info["memory_info"].rss if process.info.get("memory_info") else 0
            samples.append((cpu, process.info["pid"], process.info.get("name") or "unknown", memory, memory))
        except (psutil_module.NoSuchProcess, psutil_module.AccessDenied):
            continue
    samples.sort(key=lambda item: (-item[0], -item[3], item[1]))
    if not samples:
        lines.append("Процессы не найдены.")
        return "\n".join(lines)
    for cpu, pid, name, memory, _ in samples[:limit]:
        lines.append(f"- pid={pid} cpu={cpu:.1f}% ram={format_bytes_func(memory)} name={truncate_text_func(name, 60)}")
    return "\n".join(lines)


def render_disk_summary(format_bytes_func: Callable[[int], str]) -> str:
    lines = ["Диски"]
    for mount in ("/", "/sdcard", "/home/userland"):
        try:
            usage = shutil.disk_usage(mount)
        except OSError:
            continue
        used = usage.total - usage.free
        percent = (used / usage.total) * 100 if usage.total else 0
        lines.append(
            f"- {mount}: {percent:.1f}% ({format_bytes_func(used)} / {format_bytes_func(usage.total)}), свободно {format_bytes_func(usage.free)}"
        )
    return "\n".join(lines)


def render_network_summary(*, psutil_module: Any, format_bytes_func: Callable[[int], str]) -> str:
    lines = ["Сеть"]
    if psutil_module is not None:
        counters = psutil_module.net_io_counters(pernic=True)
        for name, stats in sorted(counters.items()):
            if name == "lo":
                continue
            lines.append(
                f"- {name}: recv={format_bytes_func(stats.bytes_recv)} sent={format_bytes_func(stats.bytes_sent)}"
            )
        if len(lines) == 1:
            lines.append("Нет активных сетевых интерфейсов.")
        return "\n".join(lines)
    try:
        with open("/proc/net/dev", "r", encoding="utf-8") as handle:
            rows = handle.read().splitlines()[2:]
        for row in rows:
            name, payload = row.split(":", 1)
            iface = name.strip()
            if iface == "lo":
                continue
            parts = payload.split()
            recv = int(parts[0])
            sent = int(parts[8])
            lines.append(f"- {iface}: recv={format_bytes_func(recv)} sent={format_bytes_func(sent)}")
    except OSError:
        lines.append("Не удалось прочитать /proc/net/dev")
    return "\n".join(lines)


def run_runtime_command(
    command: Sequence[str],
    *,
    build_subprocess_env_func: Callable[[], dict],
    timeout_seconds: int = 15,
    max_lines: int = 12,
) -> str:
    try:
        result = subprocess.run(
            list(command),
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            env=build_subprocess_env_func(),
        )
    except (subprocess.TimeoutExpired, OSError) as error:
        return f"unavailable: {error}"
    output = (result.stdout or result.stderr or "").strip()
    if result.returncode != 0:
        details = output or f"exit={result.returncode}"
        return f"unavailable: {details}"
    if not output:
        return "no output"
    lines = output.splitlines()
    return "\n".join(lines[:max_lines]).strip()


def render_enterprise_runtime_report(
    *,
    psutil_module: Any,
    format_bytes_func: Callable[[int], str],
    format_swap_line_func: Callable[[], str],
    truncate_text_func: Callable[[str, int], str],
    build_subprocess_env_func: Callable[[], dict],
    render_bridge_runtime_watch_func: Callable[[], str],
    display_timezone: ZoneInfo,
) -> str:
    lines = ["Проверка enterprise runtime"]
    lines.append(f"Время: {datetime.now(display_timezone).strftime('%Y-%m-%d %H:%M:%S %Z')}")

    visible_tools = []
    for tool_name in ("htop", "sar", "iostat", "mpstat", "pidstat", "free", "df", "ps", "ip", "ss", "apt-cache"):
        tool_path = shutil.which(tool_name)
        visible_tools.append(f"{tool_name}={'MISSING' if not tool_path else tool_path}")
    lines.extend(["", "Инструменты, доступные в этом рантайме:", *[f"- {item}" for item in visible_tools]])

    proc_bits = []
    for proc_path in ("/proc/loadavg", "/proc/meminfo", "/proc/vmstat", "/proc/net/dev"):
        proc_bits.append(f"{proc_path}={'readable' if os.access(proc_path, os.R_OK) else 'unreadable'}")
    lines.extend(["", "Доступ к /proc:", *[f"- {item}" for item in proc_bits]])

    resource_lines = render_resource_summary(
        psutil_module=psutil_module,
        format_bytes_func=format_bytes_func,
        format_swap_line_func=format_swap_line_func,
        extract_meminfo_value_func=extract_meminfo_value,
        display_timezone=display_timezone,
    ).splitlines()
    lines.extend(["", *resource_lines])
    lines.extend(["", render_bridge_runtime_watch_func()])

    command_sections = [
        ("uptime", ["uptime"], 4),
        ("free -h", ["free", "-h"], 8),
        ("df -h / /home/userland", ["df", "-h", "/", "/home/userland"], 8),
        ("ps top", ["ps", "-eo", "pid,pcpu,pmem,comm", "--sort=-pcpu"], 10),
        ("ip -brief addr", ["ip", "-brief", "addr"], 8),
        ("ss -tunlp", ["ss", "-tunlp"], 10),
        ("apt-cache policy htop sysstat", ["apt-cache", "policy", "htop", "sysstat"], 12),
    ]
    for title, command, max_lines in command_sections:
        lines.append("")
        lines.append(f"$ {' '.join(command)}")
        lines.append(truncate_text_func(
            run_runtime_command(
                command,
                build_subprocess_env_func=build_subprocess_env_func,
                timeout_seconds=20,
                max_lines=max_lines,
            ),
            1800,
        ))

    return "\n".join(lines)


def read_log_tail(log_path: Path, limit: int = 8) -> List[str]:
    if not log_path.exists():
        return []
    try:
        lines = log_path.read_text(encoding="utf-8", errors="ignore").splitlines()
    except OSError:
        return []
    return lines[-max(1, limit):]


def _find_matching_processes(psutil_module: Any, patterns: Sequence[str], limit: int = 4) -> List[Dict[str, Any]]:
    if psutil_module is None:
        return []
    lowered_patterns = tuple(pattern.lower() for pattern in patterns if pattern)
    matches: List[Dict[str, Any]] = []
    for process in psutil_module.process_iter(["pid", "name", "cmdline", "memory_info", "create_time"]):
        try:
            cmdline_parts = process.info.get("cmdline") or []
            haystack = " ".join(cmdline_parts).lower()
            if not haystack:
                haystack = (process.info.get("name") or "").lower()
            if not any(pattern in haystack for pattern in lowered_patterns):
                continue
            memory_info = process.info.get("memory_info")
            matches.append(
                {
                    "pid": process.info["pid"],
                    "name": process.info.get("name") or "unknown",
                    "cmdline": " ".join(cmdline_parts).strip(),
                    "rss": getattr(memory_info, "rss", 0) if memory_info else 0,
                    "uptime_seconds": max(0, int(time.time() - float(process.info.get("create_time") or time.time()))),
                }
            )
        except (psutil_module.NoSuchProcess, psutil_module.AccessDenied):
            continue
    matches.sort(key=lambda item: item["pid"])
    return matches[:limit]


def render_bridge_runtime_watch(
    *,
    psutil_module: Any,
    format_bytes_func: Callable[[int], str],
    truncate_text_func: Callable[[str, int], str],
    heartbeat_path: Path,
    bridge_log_path: Path,
    supervisor_log_path: Path,
    runtime_log_snapshot: Dict[str, object],
    telegram_ping_text: str = "",
) -> str:
    lines = ["Наблюдение за рантаймом bridge"]
    heartbeat_age_text = "отсутствует"
    if heartbeat_path.exists():
        try:
            heartbeat_age = max(0, int(time.time() - heartbeat_path.stat().st_mtime))
            heartbeat_age_text = f"{heartbeat_age}s"
        except OSError:
            heartbeat_age_text = "недоступно"
    lines.append(f"Heartbeat-файл: {heartbeat_path} (возраст={heartbeat_age_text})")

    bridge_processes = _find_matching_processes(psutil_module, ("tg_codex_bridge.py",), limit=3)
    supervisor_processes = _find_matching_processes(psutil_module, ("run_jarvis_supervisor.sh",), limit=3)
    lines.append(f"Процесс bridge: {'запущен' if bridge_processes else 'не найден'}")
    for process in bridge_processes:
        uptime_text = f"{process['uptime_seconds']}s" if 0 <= int(process["uptime_seconds"]) <= 86400 * 30 else "n/a"
        lines.append(
            f"- pid={process['pid']} uptime={uptime_text} ram={format_bytes_func(int(process['rss']))} cmd={truncate_text_func(process['cmdline'] or process['name'], 140)}"
        )
    lines.append(f"Процесс supervisor: {'запущен' if supervisor_processes else 'не найден'}")
    for process in supervisor_processes:
        uptime_text = f"{process['uptime_seconds']}s" if 0 <= int(process["uptime_seconds"]) <= 86400 * 30 else "n/a"
        lines.append(
            f"- pid={process['pid']} uptime={uptime_text} ram={format_bytes_func(int(process['rss']))} cmd={truncate_text_func(process['cmdline'] or process['name'], 140)}"
        )
    if telegram_ping_text:
        lines.append(f"Пинг Telegram API: {telegram_ping_text}")

    lines.extend(
        [
            f"Перезапуски за 24ч: {int(runtime_log_snapshot.get('restart_count', 0))}",
            f"Перезапуски после запуска: {int(runtime_log_snapshot.get('session_restart_count', 0))}",
            f"Принудительные heartbeat-kill за 24ч: {int(runtime_log_snapshot.get('heartbeat_kill_count', 0))}",
            f"Сигналы завершения за 24ч: {int(runtime_log_snapshot.get('termination_signal_count', 0))}",
            f"Серьёзные ошибки за 24ч: {int(runtime_log_snapshot.get('severe_error_count', 0))}",
            f"Серьёзные ошибки после запуска: {int(runtime_log_snapshot.get('session_severe_error_count', 0))}",
            f"Восстанавливаемые предупреждения за 24ч: {int(runtime_log_snapshot.get('warning_count', 0))}",
            f"Восстанавливаемые предупреждения после запуска: {int(runtime_log_snapshot.get('session_warning_count', 0))}",
            f"Деградации Enterprise Core за 24ч: {int(runtime_log_snapshot.get('codex_degraded_count', 0))}",
            f"Жёсткие ошибки Enterprise Core за 24ч: {int(runtime_log_snapshot.get('codex_error_count', 0))}",
            f"Ошибки сетевого цикла за 24ч: {int(runtime_log_snapshot.get('network_error_count', 0))}",
        ]
    )
    last_restart_line = str(runtime_log_snapshot.get("last_restart_line") or "").strip()
    if last_restart_line:
        lines.append(f"Последний перезапуск: {truncate_text_func(last_restart_line, 220)}")

    recent_errors = [truncate_text_func(str(item), 220) for item in runtime_log_snapshot.get("recent_session_error_lines", [])]
    if not recent_errors:
        recent_errors = [truncate_text_func(str(item), 220) for item in runtime_log_snapshot.get("recent_error_lines", [])]
    if recent_errors:
        lines.append("")
        lines.append("Последние серьёзные строки в логах:")
        lines.extend(f"- {item}" for item in recent_errors[-5:])

    recent_warnings = [truncate_text_func(str(item), 220) for item in runtime_log_snapshot.get("recent_session_warning_lines", [])]
    if not recent_warnings:
        recent_warnings = [truncate_text_func(str(item), 220) for item in runtime_log_snapshot.get("recent_warning_lines", [])]
    if recent_warnings:
        lines.append("")
        lines.append("Последние восстанавливаемые предупреждения:")
        lines.extend(f"- {item}" for item in recent_warnings[-5:])

    bridge_tail = read_log_tail(bridge_log_path, limit=6)
    lines.append("")
    lines.append(f"Хвост tg_codex_bridge.log ({bridge_log_path}):")
    if bridge_tail:
        lines.extend(f"- {truncate_text_func(line, 220)}" for line in bridge_tail)
    else:
        lines.append("- лог пуст")

    supervisor_tail = read_log_tail(supervisor_log_path, limit=6)
    lines.append("")
    lines.append(f"Хвост supervisor_boot.log ({supervisor_log_path}):")
    if supervisor_tail:
        lines.extend(f"- {truncate_text_func(line, 220)}" for line in supervisor_tail)
    else:
        lines.append("- лог пуст")

    return "\n".join(lines)


def format_swap_line(*, psutil_module: Any, format_bytes_func: Callable[[int], str]) -> str:
    if psutil_module is None:
        return "n/a"
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        swap = psutil_module.swap_memory()
    return f"{swap.percent:.1f}% ({format_bytes_func(swap.used)} / {format_bytes_func(swap.total)})"


def extract_meminfo_value(text: str, key: str) -> Optional[int]:
    match = re.search(rf"^{re.escape(key)}:\s+(\d+)\s+kB$", text, flags=re.MULTILINE)
    if not match:
        return None
    return int(match.group(1))
