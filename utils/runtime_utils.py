import os
import shutil
from pathlib import Path
from typing import Callable, List, Optional, Set


def should_include_code_backup_file(path: Path) -> bool:
    include_suffixes = {".py", ".sh", ".md", ".txt", ".env", ".example", ".json", ".yaml", ".yml", ".toml", ".ini"}
    include_names = {"Dockerfile", "Makefile"}
    return path.suffix.lower() in include_suffixes or path.name in include_names


def split_file_parts(file_path: Path, part_size_bytes: int) -> List[Path]:
    if file_path.stat().st_size <= part_size_bytes:
        return [file_path]
    parts: List[Path] = []
    with file_path.open("rb") as source:
        index = 1
        while True:
            chunk = source.read(part_size_bytes)
            if not chunk:
                break
            part_path = file_path.with_name(f"{file_path.name}.part{index:02d}")
            part_path.write_bytes(chunk)
            parts.append(part_path)
            index += 1
    return parts


def read_int_env(name: str, default: int, minimum: int, maximum: int) -> int:
    raw_value = os.getenv(name, "").strip()
    if not raw_value:
        return default
    try:
        value = int(raw_value)
    except ValueError:
        return default
    return max(minimum, min(value, maximum))


def read_bool_env(name: str, default: bool) -> bool:
    raw_value = os.getenv(name, "").strip().lower()
    if not raw_value:
        return default
    return raw_value in {"1", "true", "yes", "on"}


def parse_allowed_user_ids(raw_value: str, invalid_logger: Optional[Callable[[str], None]] = None) -> Set[int]:
    result: Set[int] = set()
    for part in raw_value.split(","):
        cleaned = part.strip()
        if not cleaned:
            continue
        try:
            result.add(int(cleaned))
        except ValueError:
            if invalid_logger is not None:
                invalid_logger(cleaned)
    return result


def prepare_tmp_dir(raw_path: str) -> Optional[Path]:
    if not raw_path:
        return None
    path = Path(raw_path).expanduser()
    path.mkdir(parents=True, exist_ok=True)
    return path


def cleanup_temp_file(path: Path) -> None:
    if path.is_dir():
        shutil.rmtree(path, ignore_errors=True)
        return
    if path.exists():
        path.unlink(missing_ok=True)
