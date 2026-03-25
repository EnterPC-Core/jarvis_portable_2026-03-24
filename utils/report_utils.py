import re
import shutil
import time
from datetime import datetime
from typing import Any, Callable, List, Optional, Tuple


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
) -> str:
    lines = ["Ресурсы системы"]
    lines.append(f"Время: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC")
    try:
        with open("/proc/loadavg", "r", encoding="utf-8") as handle:
            lines.append(f"Load average: {handle.read().strip()}")
    except OSError:
        pass
    if psutil_module is not None:
        vm = psutil_module.virtual_memory()
        cpu_percent = psutil_module.cpu_percent(interval=0.5)
        boot_time = datetime.utcfromtimestamp(psutil_module.boot_time()).strftime("%Y-%m-%d %H:%M:%S")
        lines.append(f"CPU: {cpu_percent:.1f}%")
        lines.append(f"RAM: {vm.percent:.1f}% ({format_bytes_func(vm.used)} / {format_bytes_func(vm.total)})")
        lines.append(f"Swap: {format_swap_line_func()}")
        lines.append(
            f"CPU cores: logical={psutil_module.cpu_count()} physical={psutil_module.cpu_count(logical=False) or 'n/a'}"
        )
        lines.append(f"Boot time UTC: {boot_time}")
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


def format_swap_line(*, psutil_module: Any, format_bytes_func: Callable[[int], str]) -> str:
    if psutil_module is None:
        return "n/a"
    swap = psutil_module.swap_memory()
    return f"{swap.percent:.1f}% ({format_bytes_func(swap.used)} / {format_bytes_func(swap.total)})"


def extract_meminfo_value(text: str, key: str) -> Optional[int]:
    match = re.search(rf"^{re.escape(key)}:\s+(\d+)\s+kB$", text, flags=re.MULTILINE)
    if not match:
        return None
    return int(match.group(1))
