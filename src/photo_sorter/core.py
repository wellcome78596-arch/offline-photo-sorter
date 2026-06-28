from __future__ import annotations

import json
import os
import re
import sys
import ctypes
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable, Literal

try:
    from PIL import Image, ExifTags
except Exception:  # pragma: no cover - GUI can still explain missing optional dependency.
    Image = None
    ExifTags = None


DateRule = Literal["modified", "created", "latest", "exif"]
Operation = Literal["copy", "move"]
IssueCode = Literal[
    "ready",
    "source_invalid",
    "network_path",
    "target_inside_source",
    "exif_missing",
    "target_exists",
    "target_collision",
]

IMAGE_EXTENSIONS = {
    ".jpg",
    ".jpeg",
    ".png",
    ".gif",
    ".heic",
    ".webp",
    ".bmp",
    ".tif",
    ".tiff",
}

DATE_RULE_LABELS: dict[DateRule, str] = {
    "modified": "修改日期",
    "created": "建立日期",
    "latest": "較晚日期",
    "exif": "EXIF 拍攝日期",
}

OPERATION_LABELS: dict[Operation, str] = {
    "copy": "複製",
    "move": "搬移",
}

WEEKDAY_LABELS = ["一", "二", "三", "四", "五", "六", "日"]

FORBIDDEN_COMMANDS = (
    "Remove-Item",
    "del",
    "erase",
    "rm",
    "rd",
    "rmdir",
    "Invoke-WebRequest",
    "iwr",
    "Invoke-RestMethod",
    "irm",
    "Start-BitsTransfer",
    "bitsadmin",
    "curl",
    "wget",
    "ftp",
    "sftp",
    "scp",
    "ssh",
    "net",
    "netsh",
    "certutil",
    "Start-Process",
    "Invoke-Expression",
    "iex",
    "powershell",
    "pwsh",
)

FORBIDDEN_PATTERN = re.compile(
    r"(?im)(?<![A-Za-z0-9_.-])("
    + "|".join(re.escape(command) for command in sorted(FORBIDDEN_COMMANDS, key=len, reverse=True))
    + r")(?:\.(?:exe|cmd|bat|ps1))?(?=$|[\s;|&])"
)
FORBIDDEN_CALL_OPERATOR_PATTERN = re.compile(r"(?m)(^|[\s;|])&\s*(['\"]|\S)")

ISSUE_LABELS: dict[IssueCode, str] = {
    "ready": "可執行",
    "source_invalid": "來源資料夾無效",
    "network_path": "網路路徑已阻止",
    "target_inside_source": "輸出位置不安全",
    "exif_missing": "EXIF 日期不存在",
    "target_exists": "目標檔案已存在",
    "target_collision": "目標路徑衝突",
}

ISSUE_ICONS: dict[IssueCode, str] = {
    "ready": "✓",
    "source_invalid": "✕",
    "network_path": "✕",
    "target_inside_source": "✕",
    "exif_missing": "!",
    "target_exists": "✕",
    "target_collision": "✕",
}


@dataclass(frozen=True)
class PhotoDate:
    value: datetime
    source_label: str


@dataclass
class PreviewItem:
    source_path: Path
    target_path: Path | None
    date_folder: str | None
    date_source: str
    operation: Operation
    status: Literal["ready", "skipped", "error"]
    issue_code: IssueCode = "ready"
    reason: str = ""

    @property
    def operation_label(self) -> str:
        return OPERATION_LABELS[self.operation]

    @property
    def issue_label(self) -> str:
        return ISSUE_LABELS[self.issue_code]

    @property
    def issue_icon(self) -> str:
        return ISSUE_ICONS[self.issue_code]


@dataclass
class ExecutionSummary:
    success: list[str]
    skipped: list[str]
    errors: list[str]


@dataclass(frozen=True)
class SafetyReport:
    lines: list[str]
    has_blocking_issue: bool

    def to_text(self) -> str:
        return "\n".join(self.lines)


def format_date_folder(value: datetime) -> str:
    weekday = WEEKDAY_LABELS[value.date().weekday()]
    return f"{value:%Y-%m-%d} ({weekday})"


def is_image_file(path: Path) -> bool:
    return path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS


def iter_image_files(source_root: Path) -> Iterable[Path]:
    for path in sorted(source_root.rglob("*"), key=lambda item: str(item).lower()):
        if is_image_file(path):
            yield path


def _datetime_from_timestamp(timestamp: float) -> datetime:
    return datetime.fromtimestamp(timestamp)


def extract_exif_datetime(path: Path) -> datetime | None:
    if Image is None:
        return None

    try:
        with Image.open(path) as image:
            exif = image.getexif()
            if not exif:
                return None

            tags = ExifTags.TAGS if ExifTags is not None else {}
            candidates = []
            for tag_id, raw_value in exif.items():
                tag_name = tags.get(tag_id, str(tag_id))
                if tag_name in {"DateTimeOriginal", "DateTimeDigitized", "DateTime"}:
                    candidates.append(str(raw_value))

            for raw_value in candidates:
                parsed = parse_exif_datetime(raw_value)
                if parsed is not None:
                    return parsed
    except Exception:
        return None

    return None


def parse_exif_datetime(raw_value: str) -> datetime | None:
    raw_value = raw_value.strip()
    for fmt in ("%Y:%m:%d %H:%M:%S", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(raw_value, fmt)
        except ValueError:
            continue
    return None


def choose_photo_date(path: Path, date_rule: DateRule) -> PhotoDate | None:
    stat = path.stat()
    modified = _datetime_from_timestamp(stat.st_mtime)
    created = _datetime_from_timestamp(stat.st_ctime)

    if date_rule == "modified":
        return PhotoDate(modified, DATE_RULE_LABELS[date_rule])
    if date_rule == "created":
        return PhotoDate(created, DATE_RULE_LABELS[date_rule])
    if date_rule == "latest":
        return PhotoDate(max(modified, created), DATE_RULE_LABELS[date_rule])
    if date_rule == "exif":
        exif_date = extract_exif_datetime(path)
        if exif_date is None:
            return None
        return PhotoDate(exif_date, DATE_RULE_LABELS[date_rule])
    raise ValueError(f"Unsupported date rule: {date_rule}")


def build_preview(
    source_root: Path,
    target_root: Path,
    date_rule: DateRule = "modified",
    operation: Operation = "copy",
) -> list[PreviewItem]:
    items: list[PreviewItem] = []
    grouped: dict[tuple[str, str], list[PreviewItem]] = {}

    if is_network_path(source_root) or is_network_path(target_root):
        return [
            PreviewItem(
                source_path=source_root,
                target_path=None,
                date_folder=None,
                date_source=DATE_RULE_LABELS[date_rule],
                operation=operation,
                status="error",
                issue_code="network_path",
                reason="來源資料夾與輸出資料夾必須是本機路徑，不可使用網路位置或網路磁碟。",
            )
        ]

    source_root = source_root.resolve()
    target_root = target_root.resolve()

    if not source_root.exists() or not source_root.is_dir():
        return [
            PreviewItem(
                source_path=source_root,
                target_path=None,
                date_folder=None,
                date_source=DATE_RULE_LABELS[date_rule],
                operation=operation,
                status="error",
                issue_code="source_invalid",
                reason="來源資料夾不存在或不是資料夾。",
            )
        ]

    if is_same_or_nested_path(target_root, source_root):
        return [
            PreviewItem(
                source_path=source_root,
                target_path=None,
                date_folder=None,
                date_source=DATE_RULE_LABELS[date_rule],
                operation=operation,
                status="error",
                issue_code="target_inside_source",
                reason="輸出資料夾不可與來源資料夾相同，也不可放在來源資料夾內。",
            )
        ]

    for source_path in iter_image_files(source_root):
        photo_date = choose_photo_date(source_path, date_rule)
        if photo_date is None:
            items.append(
                PreviewItem(
                    source_path=source_path,
                    target_path=None,
                    date_folder=None,
                    date_source=DATE_RULE_LABELS[date_rule],
                    operation=operation,
                    status="skipped",
                    issue_code="exif_missing",
                    reason="找不到可用的 EXIF 拍攝日期。",
                )
            )
            continue

        date_folder = format_date_folder(photo_date.value)
        target_path = target_root / date_folder / source_path.name
        item = PreviewItem(
            source_path=source_path,
            target_path=target_path,
            date_folder=date_folder,
            date_source=photo_date.source_label,
            operation=operation,
            status="ready",
        )
        items.append(item)
        grouped.setdefault((date_folder, source_path.name.casefold()), []).append(item)

    for collision_items in grouped.values():
        if len(collision_items) <= 1:
            continue
        for item in collision_items:
            relative_parent = item.source_path.parent.relative_to(source_root)
            item.target_path = target_root / item.date_folder / relative_parent / item.source_path.name

    seen_targets: set[str] = set()
    for item in items:
        if item.status != "ready" or item.target_path is None:
            continue
        target_key = os.path.normcase(str(item.target_path))
        if target_key in seen_targets:
            item.status = "error"
            item.issue_code = "target_collision"
            item.reason = "完整相對路徑下仍有同名衝突，已阻止覆蓋。"
            continue
        seen_targets.add(target_key)
        if item.target_path.exists():
            item.status = "error"
            item.issue_code = "target_exists"
            item.reason = "目標檔案已存在，已阻止覆蓋。"

    return items


def build_safety_report(items: Iterable[PreviewItem], operation: Operation) -> SafetyReport:
    items = list(items)
    ready = sum(1 for item in items if item.status == "ready")
    skipped = sum(1 for item in items if item.status == "skipped")
    errors = sum(1 for item in items if item.status == "error")
    has_network_issue = any(item.issue_code == "network_path" for item in items)
    has_overwrite_issue = any(item.issue_code in {"target_exists", "target_collision"} for item in items)

    lines = [
        f"✓ 可執行項目：{ready}",
        f"! 略過項目：{skipped}",
        f"✕ 錯誤項目：{errors}",
        "✓ 刪除功能：未提供",
        "✓ 網路路徑：未偵測到" if not has_network_issue else "✕ 網路路徑：已阻止",
        "✓ 覆蓋風險：未偵測到" if not has_overwrite_issue else "✕ 覆蓋風險：已阻止",
        "✓ 檔案動作：複製保留原檔" if operation == "copy" else "! 檔案動作：搬移原檔，請再次確認",
    ]
    return SafetyReport(lines=lines, has_blocking_issue=errors > 0)


def is_same_or_nested_path(candidate: Path, root: Path) -> bool:
    try:
        candidate.relative_to(root)
        return True
    except ValueError:
        return False


def is_network_path(path: Path) -> bool:
    text = str(path)
    normalized = text.replace("/", "\\")
    if normalized.startswith("\\\\"):
        return True
    if re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*://", text):
        return True
    if sys.platform != "win32":
        return False

    drive, _tail = os.path.splitdrive(text)
    if not drive:
        return False
    try:
        return ctypes.windll.kernel32.GetDriveTypeW(drive + "\\") == 4
    except Exception:
        return False


def powershell_quote(path: Path) -> str:
    return "'" + str(path).replace("'", "''") + "'"


def generate_powershell(items: Iterable[PreviewItem]) -> str:
    lines = [
        "$ErrorActionPreference = 'Stop'",
        "$ProgressPreference = 'SilentlyContinue'",
    ]
    directories: set[str] = set()

    for item in items:
        if item.status != "ready" or item.target_path is None:
            continue
        parent = item.target_path.parent
        parent_key = os.path.normcase(str(parent))
        if parent_key not in directories:
            directories.add(parent_key)
            lines.append(
                f"if (-not (Test-Path -LiteralPath {powershell_quote(parent)})) "
                f"{{ New-Item -ItemType Directory -Path {powershell_quote(parent)} | Out-Null }}"
            )

        command = "Copy-Item" if item.operation == "copy" else "Move-Item"
        lines.append(
            f"{command} -LiteralPath {powershell_quote(item.source_path)} "
            f"-Destination {powershell_quote(item.target_path)}"
        )

    script = "\n".join(lines)
    problems = scan_forbidden_powershell(script)
    if problems:
        raise ValueError("PowerShell safety scan failed: " + ", ".join(problems))
    return script


def scan_forbidden_powershell(script: str) -> list[str]:
    script = strip_powershell_quoted_strings(script)
    found = []
    if FORBIDDEN_CALL_OPERATOR_PATTERN.search(script):
        found.append("&")
    for match in FORBIDDEN_PATTERN.finditer(script):
        command = match.group(1)
        if command not in found:
            found.append(command)
    return found


def strip_powershell_quoted_strings(script: str) -> str:
    result: list[str] = []
    i = 0
    in_single = False
    in_double = False
    while i < len(script):
        char = script[i]
        if in_single:
            result.append(" ")
            if char == "'" and i + 1 < len(script) and script[i + 1] == "'":
                result.append(" ")
                i += 2
                continue
            if char == "'":
                in_single = False
            i += 1
            continue
        if in_double:
            result.append(" ")
            if char == "`" and i + 1 < len(script):
                result.append(" ")
                i += 2
                continue
            if char == '"':
                in_double = False
            i += 1
            continue
        if char == "'":
            in_single = True
            result.append(" ")
            i += 1
            continue
        if char == '"':
            in_double = True
            result.append(" ")
            i += 1
            continue
        result.append(char)
        i += 1
    return "".join(result)


def summarize_items(items: Iterable[PreviewItem]) -> ExecutionSummary:
    summary = ExecutionSummary(success=[], skipped=[], errors=[])
    for item in items:
        label = str(item.source_path)
        if item.status == "ready":
            summary.success.append(label)
        elif item.status == "skipped":
            summary.skipped.append(f"{label} - {item.reason}")
        else:
            summary.errors.append(f"{label} - {item.reason}")
    return summary


def load_json(path: Path, default: dict) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default.copy()


def save_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
