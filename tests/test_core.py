from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path

from PIL import Image

from photo_sorter.core import (
    build_safety_report,
    build_preview,
    extract_exif_datetime,
    format_date_folder,
    generate_powershell,
    is_network_path,
    parse_exif_datetime,
    scan_forbidden_powershell,
)


def touch(path: Path, when: datetime) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"sample")
    timestamp = when.timestamp()
    os.utime(path, (timestamp, timestamp))


def test_weekday_folder_names_are_calculated() -> None:
    assert format_date_folder(datetime(2026, 6, 20, 8, 0, 0)) == "2026-06-20 (六)"
    assert format_date_folder(datetime(2026, 6, 21, 8, 0, 0)) == "2026-06-21 (日)"


def test_same_name_same_date_uses_full_relative_source_path(tmp_path: Path) -> None:
    source = tmp_path / "source"
    target = tmp_path / "target"
    when = datetime(2026, 6, 20, 9, 30, 0)
    first = source / "A" / "IMG_001.jpg"
    second = source / "B" / "IMG_001.jpg"
    touch(first, when)
    touch(second, when)

    items = build_preview(source, target, "modified", "copy")
    destinations = sorted(str(item.target_path.relative_to(target)) for item in items)

    assert destinations == [
        "2026-06-20 (六)\\A\\IMG_001.jpg",
        "2026-06-20 (六)\\B\\IMG_001.jpg",
    ]


def test_same_name_different_date_does_not_use_relative_source_path(tmp_path: Path) -> None:
    source = tmp_path / "source"
    target = tmp_path / "target"
    touch(source / "A" / "IMG_001.jpg", datetime(2026, 6, 20, 9, 30, 0))
    touch(source / "B" / "IMG_001.jpg", datetime(2026, 6, 21, 9, 30, 0))

    items = build_preview(source, target, "modified", "copy")
    destinations = sorted(str(item.target_path.relative_to(target)) for item in items)

    assert destinations == [
        "2026-06-20 (六)\\IMG_001.jpg",
        "2026-06-21 (日)\\IMG_001.jpg",
    ]


def test_existing_target_file_is_error_instead_of_overwrite(tmp_path: Path) -> None:
    source = tmp_path / "source"
    target = tmp_path / "target"
    touch(source / "IMG_001.jpg", datetime(2026, 6, 20, 9, 30, 0))
    existing = target / "2026-06-20 (六)" / "IMG_001.jpg"
    touch(existing, datetime(2026, 6, 20, 10, 0, 0))

    items = build_preview(source, target, "modified", "copy")

    assert items[0].status == "error"
    assert items[0].issue_code == "target_exists"
    assert "阻止覆蓋" in items[0].reason


def test_target_folder_cannot_be_inside_source_folder(tmp_path: Path) -> None:
    source = tmp_path / "source"
    touch(source / "IMG_001.jpg", datetime(2026, 6, 20, 9, 30, 0))

    items = build_preview(source, source / "sorted", "modified", "copy")

    assert items[0].status == "error"
    assert items[0].issue_code == "target_inside_source"
    assert "來源資料夾內" in items[0].reason


def test_network_paths_are_blocked_for_source_and_target(tmp_path: Path) -> None:
    source = tmp_path / "source"
    touch(source / "IMG_001.jpg", datetime(2026, 6, 20, 9, 30, 0))

    items = build_preview(source, Path("//server/share/photos"), "modified", "copy")

    assert items[0].status == "error"
    assert items[0].issue_code == "network_path"
    assert "網路" in items[0].reason
    assert is_network_path(Path("//server/share/photos"))


def test_powershell_generation_uses_allowed_commands(tmp_path: Path) -> None:
    source = tmp_path / "source"
    target = tmp_path / "target"
    touch(source / "IMG_001.jpg", datetime(2026, 6, 20, 9, 30, 0))

    script = generate_powershell(build_preview(source, target, "modified", "copy"))

    assert "Copy-Item" in script
    assert scan_forbidden_powershell(script) == []


def test_safety_report_uses_icons_and_counts(tmp_path: Path) -> None:
    source = tmp_path / "source"
    target = tmp_path / "target"
    touch(source / "IMG_001.jpg", datetime(2026, 6, 20, 9, 30, 0))

    report = build_safety_report(build_preview(source, target, "modified", "copy"), "copy")

    text = report.to_text()
    assert "✓ 可執行項目：1" in text
    assert "✓ 刪除功能：未提供" in text
    assert "✓ 檔案動作：複製保留原檔" in text
    assert not report.has_blocking_issue


def test_powershell_scan_ignores_forbidden_words_inside_quoted_paths(tmp_path: Path) -> None:
    source = tmp_path / "source"
    target = tmp_path / "target"
    touch(source / "curl photo.jpg", datetime(2026, 6, 20, 9, 30, 0))
    touch(source / "A & B.jpg", datetime(2026, 6, 20, 9, 31, 0))

    script = generate_powershell(build_preview(source, target, "modified", "copy"))

    assert "curl photo.jpg" in script
    assert "A & B.jpg" in script
    assert scan_forbidden_powershell(script) == []


def test_safety_scan_blocks_forbidden_commands() -> None:
    assert scan_forbidden_powershell("Remove-Item -LiteralPath 'x'") == ["Remove-Item"]
    assert scan_forbidden_powershell("Write-Host ok\nrm x") == ["rm"]
    assert scan_forbidden_powershell("Invoke-WebRequest https://example.test") == ["Invoke-WebRequest"]
    assert scan_forbidden_powershell("curl https://example.test") == ["curl"]
    assert scan_forbidden_powershell("Write-Host ok;curl.exe https://example.test") == ["curl"]
    assert scan_forbidden_powershell("& 'curl' https://example.test") == ["&"]


def test_exif_parser_and_missing_exif_skip(tmp_path: Path) -> None:
    assert parse_exif_datetime("2026:06:20 11:22:33") == datetime(2026, 6, 20, 11, 22, 33)

    image_path = tmp_path / "source" / "plain.jpg"
    image_path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (4, 4), "white").save(image_path)

    assert extract_exif_datetime(image_path) is None
    items = build_preview(tmp_path / "source", tmp_path / "target", "exif", "copy")
    assert items[0].status == "skipped"
    assert items[0].issue_code == "exif_missing"
    assert "EXIF" in items[0].reason
