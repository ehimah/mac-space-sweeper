#!/usr/bin/env python3
"""Scan and optionally clean common macOS junk-file categories.

The tool is intentionally conservative:
- Scanning is read-only.
- Cleanup is opt-in and asks for confirmation.
- Deletion is permanent, so use interactive mode or --dry-run first.

It is aimed at the same broad categories shown by consumer cleaner apps:
user caches, browser caches, Xcode junk, logs, downloads, DMGs, screenshots,
mail downloads, and trash contents.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable, Sequence


HOME = Path.home()


@dataclass(frozen=True)
class ScanItem:
    name: str
    path: Path
    size_bytes: int


@dataclass(frozen=True)
class CategorySpec:
    key: str
    label: str
    description: str
    recommended: bool
    scanner: Callable[[], list[ScanItem]]


def human_bytes(size: int) -> str:
    units = ["B", "KB", "MB", "GB", "TB", "PB"]
    value = float(size)
    for unit in units:
        if value < 1024 or unit == units[-1]:
            if unit == "B":
                return f"{int(value)} {unit}"
            if value >= 100:
                return f"{value:.0f} {unit}"
            if value >= 10:
                return f"{value:.1f} {unit}"
            return f"{value:.2f} {unit}"
        value /= 1024
    return f"{size} B"


def path_exists(path: Path) -> bool:
    try:
        return path.exists()
    except OSError:
        return False


def safe_is_dir(path: Path) -> bool:
    try:
        return path.is_dir()
    except OSError:
        return False


def safe_is_file(path: Path) -> bool:
    try:
        return path.is_file()
    except OSError:
        return False


def du_size(path: Path) -> int:
    if not path_exists(path):
        return 0
    try:
        proc = subprocess.run(
            ["du", "-sk", str(path)],
            check=False,
            capture_output=True,
            text=True,
        )
    except OSError:
        return 0
    if proc.returncode != 0 or not proc.stdout.strip():
        return 0
    first_field = proc.stdout.split()[0]
    try:
        return int(first_field) * 1024
    except ValueError:
        return 0


def scan_top_level(
    root: Path,
    *,
    exclude_names: Iterable[str] = (),
    include_files: bool = True,
    include_dirs: bool = True,
) -> list[ScanItem]:
    if not path_exists(root) or not safe_is_dir(root):
        return []

    excluded = {name.lower() for name in exclude_names}
    items: list[ScanItem] = []
    try:
        children = list(root.iterdir())
    except OSError:
        return []

    for child in children:
        child_name = child.name.lower()
        if child_name in excluded:
            continue
        is_dir = safe_is_dir(child)
        is_file = safe_is_file(child)
        if is_dir and not include_dirs:
            continue
        if is_file and not include_files:
            continue
        if not is_dir and not is_file:
            continue
        size = du_size(child)
        if size > 0:
            items.append(ScanItem(name=child.name, path=child, size_bytes=size))
    return sorted(items, key=lambda item: item.size_bytes, reverse=True)


def scan_specific_paths(named_paths: Sequence[tuple[str, Path]]) -> list[ScanItem]:
    items: list[ScanItem] = []
    for name, path in named_paths:
        size = du_size(path)
        if size > 0:
            items.append(ScanItem(name=name, path=path, size_bytes=size))
    return sorted(items, key=lambda item: item.size_bytes, reverse=True)


def find_files(
    roots: Sequence[Path],
    *,
    suffixes: Sequence[str] = (),
    name_contains: Sequence[str] = (),
    max_depth: int = 3,
) -> list[ScanItem]:
    results: list[ScanItem] = []
    suffixes_lower = tuple(s.lower() for s in suffixes)
    contains_lower = tuple(s.lower() for s in name_contains)

    for root in roots:
        if not path_exists(root) or not safe_is_dir(root):
            continue
        start_depth = len(root.parts)
        try:
            walker = os.walk(root)
        except OSError:
            continue
        for current_root, dirnames, filenames in walker:
            current_path = Path(current_root)
            depth = len(current_path.parts) - start_depth
            if depth >= max_depth:
                dirnames[:] = []
            for filename in filenames:
                name_lower = filename.lower()
                if suffixes_lower and not name_lower.endswith(suffixes_lower):
                    continue
                if contains_lower and not any(token in name_lower for token in contains_lower):
                    continue
                file_path = current_path / filename
                try:
                    size = file_path.stat().st_size
                except OSError:
                    continue
                if size > 0:
                    results.append(
                        ScanItem(name=str(file_path.relative_to(root)), path=file_path, size_bytes=size)
                    )
    return sorted(results, key=lambda item: item.size_bytes, reverse=True)


def delete_path(path: Path) -> None:
    if not path_exists(path):
        return
    if path.is_symlink() or path.is_file():
        path.unlink()
        return
    shutil.rmtree(path)


def format_table(headers: Sequence[str], rows: Sequence[Sequence[str]]) -> str:
    widths = [len(header) for header in headers]
    for row in rows:
        for index, value in enumerate(row):
            widths[index] = max(widths[index], len(value))

    def render(values: Sequence[str]) -> str:
        return "  ".join(value.ljust(widths[index]) for index, value in enumerate(values))

    lines = [render(headers), render(["-" * width for width in widths])]
    lines.extend(render(row) for row in rows)
    return "\n".join(lines)


def browser_cache_paths() -> list[tuple[str, Path]]:
    return [
        ("Google Chrome", HOME / "Library/Caches/Google/Chrome"),
        ("Chromium", HOME / "Library/Caches/Chromium"),
        ("Brave Browser", HOME / "Library/Caches/BraveSoftware/Brave-Browser"),
        ("Arc", HOME / "Library/Caches/company.thebrowser.Browser"),
        ("Firefox", HOME / "Library/Caches/Firefox"),
        ("Safari", HOME / "Library/Caches/com.apple.Safari"),
    ]


def scan_user_cache() -> list[ScanItem]:
    excluded = {
        "google",
        "chromium",
        "bravesoftware",
        "firefox",
        "com.apple.safari",
        "company.thebrowser.browser",
    }
    return scan_top_level(HOME / "Library/Caches", exclude_names=excluded)


def scan_xcode_junk() -> list[ScanItem]:
    named = [
        ("DerivedData", HOME / "Library/Developer/Xcode/DerivedData"),
        ("Archives", HOME / "Library/Developer/Xcode/Archives"),
        ("iOS DeviceSupport", HOME / "Library/Developer/Xcode/iOS DeviceSupport"),
        ("watchOS DeviceSupport", HOME / "Library/Developer/Xcode/watchOS DeviceSupport"),
        ("tvOS DeviceSupport", HOME / "Library/Developer/Xcode/tvOS DeviceSupport"),
        ("DocumentationCache", HOME / "Library/Developer/Shared/Documentation/DocSets"),
    ]
    items = scan_specific_paths(named)

    simulator_root = HOME / "Library/Developer/CoreSimulator/Devices"
    for simulator in scan_top_level(simulator_root, include_files=False):
        items.append(
            ScanItem(
                name=f"Simulators/{simulator.name}",
                path=simulator.path,
                size_bytes=simulator.size_bytes,
            )
        )

    return sorted(items, key=lambda item: item.size_bytes, reverse=True)


def scan_browser_cache() -> list[ScanItem]:
    return scan_specific_paths(browser_cache_paths())


def scan_system_cache() -> list[ScanItem]:
    return scan_top_level(Path("/Library/Caches"))


def scan_system_logs() -> list[ScanItem]:
    items = scan_top_level(Path("/Library/Logs"))
    items.extend(
        ScanItem(name=f"var/log/{item.name}", path=item.path, size_bytes=item.size_bytes)
        for item in scan_top_level(Path("/private/var/log"))
    )
    return sorted(items, key=lambda item: item.size_bytes, reverse=True)


def scan_user_logs() -> list[ScanItem]:
    return scan_top_level(HOME / "Library/Logs")


def scan_downloads() -> list[ScanItem]:
    return scan_top_level(HOME / "Downloads")


def scan_unused_dmgs() -> list[ScanItem]:
    roots = [HOME / "Downloads", HOME / "Desktop", HOME / "Documents"]
    return find_files(roots, suffixes=[".dmg"], max_depth=3)


def scan_screenshots() -> list[ScanItem]:
    roots = [HOME / "Desktop", HOME / "Downloads"]
    return find_files(
        roots,
        suffixes=[".png", ".jpg", ".jpeg", ".mov", ".mp4"],
        name_contains=["screen shot", "screenshot", "screen recording"],
        max_depth=2,
    )


def scan_mail_attachments() -> list[ScanItem]:
    paths = [
        ("Mail Downloads", HOME / "Library/Containers/com.apple.mail/Data/Library/Mail Downloads"),
        ("Mail Attachments", HOME / "Library/Mail"),
    ]
    return scan_specific_paths(paths)


def scan_trash() -> list[ScanItem]:
    return scan_top_level(HOME / ".Trash")


CATEGORIES: list[CategorySpec] = [
    CategorySpec(
        key="user-cache",
        label="User Cache Files",
        description="Per-app cache directories under ~/Library/Caches, excluding known browser caches.",
        recommended=True,
        scanner=scan_user_cache,
    ),
    CategorySpec(
        key="xcode-junk",
        label="Xcode Junk",
        description="Derived data, simulator devices, archives, and device support files.",
        recommended=False,
        scanner=scan_xcode_junk,
    ),
    CategorySpec(
        key="browser-cache",
        label="Browser Cache",
        description="Browser cache directories for Chrome, Firefox, Safari, Brave, Arc, and Chromium.",
        recommended=False,
        scanner=scan_browser_cache,
    ),
    CategorySpec(
        key="system-cache",
        label="System Cache Files",
        description="Shared cache directories under /Library/Caches.",
        recommended=True,
        scanner=scan_system_cache,
    ),
    CategorySpec(
        key="system-logs",
        label="System Log Files",
        description="Shared logs in /Library/Logs and /private/var/log.",
        recommended=True,
        scanner=scan_system_logs,
    ),
    CategorySpec(
        key="user-logs",
        label="User Log Files",
        description="Per-user logs under ~/Library/Logs.",
        recommended=True,
        scanner=scan_user_logs,
    ),
    CategorySpec(
        key="downloads",
        label="Downloads",
        description="Top-level items in ~/Downloads.",
        recommended=False,
        scanner=scan_downloads,
    ),
    CategorySpec(
        key="unused-dmgs",
        label="Unused DMG Files",
        description="DMG files in Downloads, Desktop, and Documents.",
        recommended=False,
        scanner=scan_unused_dmgs,
    ),
    CategorySpec(
        key="screenshots",
        label="Screen Capture Files",
        description="Screenshots and screen recordings in common user folders.",
        recommended=False,
        scanner=scan_screenshots,
    ),
    CategorySpec(
        key="mail-attachments",
        label="Mail Attachments",
        description="Apple Mail downloads and attachment storage.",
        recommended=False,
        scanner=scan_mail_attachments,
    ),
    CategorySpec(
        key="trash",
        label="Trash Can",
        description="Contents of ~/.Trash.",
        recommended=False,
        scanner=scan_trash,
    ),
]


def category_map() -> dict[str, CategorySpec]:
    return {category.key: category for category in CATEGORIES}


def scan_categories(selected_keys: Sequence[str]) -> dict[str, list[ScanItem]]:
    selected = category_map()
    result: dict[str, list[ScanItem]] = {}
    for key in selected_keys:
        category = selected[key]
        result[key] = category.scanner()
    return result


def total_size(items: Sequence[ScanItem]) -> int:
    return sum(item.size_bytes for item in items)


def unique_items(groups: Iterable[Sequence[ScanItem]]) -> list[ScanItem]:
    deduped: dict[Path, ScanItem] = {}
    for group in groups:
        for item in group:
            deduped.setdefault(item.path, item)
    return sorted(deduped.values(), key=lambda item: item.size_bytes, reverse=True)


def unique_total(groups: Iterable[Sequence[ScanItem]]) -> int:
    return total_size(unique_items(groups))


def item_to_json(item: ScanItem) -> dict[str, str | int]:
    return {
        "name": item.name,
        "path": str(item.path),
        "sizeBytes": item.size_bytes,
        "sizeHuman": human_bytes(item.size_bytes),
    }


def scan_result_to_json(selected_keys: Sequence[str], scanned: dict[str, list[ScanItem]]) -> dict[str, object]:
    mapping = category_map()
    categories: list[dict[str, object]] = []
    for key in selected_keys:
        category = mapping[key]
        items = scanned[key]
        categories.append(
            {
                "key": category.key,
                "label": category.label,
                "description": category.description,
                "recommended": category.recommended,
                "totalBytes": total_size(items),
                "totalHuman": human_bytes(total_size(items)),
                "items": [item_to_json(item) for item in items],
            }
        )

    unique_targets = unique_items(scanned[key] for key in selected_keys)
    return {
        "categories": categories,
        "uniqueTotalBytes": total_size(unique_targets),
        "uniqueTotalHuman": human_bytes(total_size(unique_targets)),
        "uniqueTargets": [item_to_json(item) for item in unique_targets],
    }


def print_summary(scanned: dict[str, list[ScanItem]]) -> None:
    rows = []
    for index, category in enumerate(CATEGORIES, start=1):
        if category.key not in scanned:
            continue
        size = total_size(scanned[category.key])
        rows.append(
            [
                str(index),
                category.key,
                category.label,
                human_bytes(size),
                "yes" if category.recommended else "no",
            ]
        )
    print(format_table(["#", "Key", "Category", "Total", "Recommended"], rows))
    print()
    total = unique_total(scanned.values())
    print(f"Unique grand total: {human_bytes(total)}")
    print("Note: overlapping categories are de-duplicated in cleanup totals.")


def print_items(category: CategorySpec, items: Sequence[ScanItem], limit: int | None) -> None:
    print()
    print(f"{category.label} [{category.key}]")
    print(category.description)
    print(f"Total: {human_bytes(total_size(items))}")
    print()

    if not items:
        print("No matching files found.")
        return

    sliced = list(items if limit is None else items[:limit])
    rows = []
    for index, item in enumerate(sliced, start=1):
        rows.append([str(index), human_bytes(item.size_bytes), str(item.path)])
    print(format_table(["#", "Size", "Path"], rows))

    if limit is not None and len(items) > limit:
        print()
        print(f"Showing {limit} of {len(items)} items.")


def confirm(prompt: str) -> bool:
    answer = input(f"{prompt} [y/N]: ").strip().lower()
    return answer in {"y", "yes"}


def select_categories_interactive(scanned: dict[str, list[ScanItem]]) -> list[str]:
    recommended = [category.key for category in CATEGORIES if category.recommended and category.key in scanned]
    print()
    print("Choose categories to clean.")
    print("Examples: 1,4,5 or user-cache,system-cache. Press Enter for recommended set.")
    raw = input("Selection: ").strip()
    if not raw:
        return recommended

    selected_keys: list[str] = []
    index_by_number = {str(index): category.key for index, category in enumerate(CATEGORIES, start=1)}
    available = set(scanned)
    for token in [part.strip() for part in raw.split(",") if part.strip()]:
        key = index_by_number.get(token, token)
        if key not in available:
            print(f"Skipping unknown category: {token}")
            continue
        if key not in selected_keys:
            selected_keys.append(key)
    return selected_keys


def clean_items(items: Sequence[ScanItem], *, dry_run: bool) -> tuple[int, list[str]]:
    freed = 0
    errors: list[str] = []
    for item in items:
        freed += item.size_bytes
        if dry_run:
            continue
        try:
            delete_path(item.path)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{item.path}: {exc}")
    return freed, errors


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "command",
        nargs="?",
        default="interactive",
        choices=["interactive", "scan", "scan-json", "clean"],
        help="Run interactive mode, scan only, or clean selected categories.",
    )
    parser.add_argument(
        "--category",
        action="append",
        choices=[category.key for category in CATEGORIES],
        help="Category key to include. May be repeated.",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Include every category instead of the recommended subset.",
    )
    parser.add_argument(
        "--show-items",
        action="store_true",
        help="Print item-level details after the summary.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=15,
        help="Maximum number of items to show per category. Use 0 for all.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be removed without deleting anything.",
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Skip confirmation prompts for non-interactive clean runs.",
    )
    return parser.parse_args()


def resolve_category_keys(args: argparse.Namespace) -> list[str]:
    if args.category:
        return args.category
    if args.all:
        return [category.key for category in CATEGORIES]
    return [category.key for category in CATEGORIES if category.recommended]


def print_selected_categories(keys: Sequence[str]) -> None:
    selected = category_map()
    print("Selected categories:")
    for key in keys:
        category = selected[key]
        print(f"- {category.label} [{key}]")


def run_scan(args: argparse.Namespace) -> int:
    keys = resolve_category_keys(args)
    scanned = scan_categories(keys)
    print_summary(scanned)
    if args.show_items:
        limit = None if args.limit == 0 else args.limit
        mapping = category_map()
        for key in keys:
            print_items(mapping[key], scanned[key], limit)
    return 0


def run_clean(args: argparse.Namespace) -> int:
    keys = resolve_category_keys(args)
    scanned = scan_categories(keys)
    print_summary(scanned)
    print_selected_categories(keys)

    total = unique_total(scanned.values())
    if total == 0:
        print("Nothing to remove.")
        return 0

    if args.show_items:
        limit = None if args.limit == 0 else args.limit
        mapping = category_map()
        for key in keys:
            print_items(mapping[key], scanned[key], limit)

    dry_run = args.dry_run
    action_label = "would remove" if dry_run else "will permanently delete"
    print()
    print(f"This {action_label} about {human_bytes(total)}.")
    if not args.yes and not confirm("Continue"):
        print("Aborted.")
        return 1

    targets = unique_items(scanned[key] for key in keys)
    freed = 0
    errors: list[str] = []
    freed, errors = clean_items(targets, dry_run=dry_run)

    if dry_run:
        print(f"Dry run complete. Would remove about {human_bytes(freed)}.")
    else:
        print(f"Cleanup complete. Attempted to remove about {human_bytes(freed)}.")
    if errors:
        print()
        print("Some paths could not be removed:")
        for error in errors:
            print(f"- {error}")
        return 2
    return 0


def run_scan_json(args: argparse.Namespace) -> int:
    keys = resolve_category_keys(args)
    scanned = scan_categories(keys)
    print(json.dumps(scan_result_to_json(keys, scanned), indent=2))
    return 0


def run_interactive(args: argparse.Namespace) -> int:
    keys = [category.key for category in CATEGORIES]
    scanned = scan_categories(keys)
    print_summary(scanned)

    for category in CATEGORIES:
        items = scanned.get(category.key, [])
        if items:
            print_items(category, items, limit=10)

    selected_keys = select_categories_interactive(scanned)
    if not selected_keys:
        print("No categories selected.")
        return 0

    print()
    print_selected_categories(selected_keys)

    to_remove = {key: scanned[key] for key in selected_keys}
    targets = unique_items(to_remove.values())
    total = total_size(targets)
    print(f"Selected total: {human_bytes(total)}")
    print("Cleanup in interactive mode is permanent.")
    if not confirm("Delete these items"):
        print("Aborted.")
        return 1

    freed, errors = clean_items(targets, dry_run=False)

    print(f"Cleanup complete. Attempted to remove about {human_bytes(freed)}.")
    if errors:
        print()
        print("Some paths could not be removed:")
        for error in errors:
            print(f"- {error}")
        return 2
    return 0


def main() -> int:
    args = parse_args()
    if args.command == "scan":
        return run_scan(args)
    if args.command == "scan-json":
        return run_scan_json(args)
    if args.command == "clean":
        return run_clean(args)
    return run_interactive(args)


if __name__ == "__main__":
    raise SystemExit(main())
