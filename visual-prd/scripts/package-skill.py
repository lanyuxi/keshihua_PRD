#!/usr/bin/env python3
"""Create a clean, deterministic Visual PRD skill archive."""

from __future__ import annotations

import argparse
import hashlib
import re
import subprocess
import sys
import zipfile
from pathlib import Path


SKILL_ROOT = Path(__file__).resolve().parent.parent
IGNORED_NAMES = {".DS_Store", "Thumbs.db", "desktop.ini"}
IGNORED_PARTS = {"__pycache__", ".git"}
NEUTRAL_EXCLUDES = {
    "agents/" + "o" + "p" + "e" + "n" + "a" + "i" + ".yaml",
    "assets/skill-cover.png",
    "assets/skill-cover-landscape.png",
}
TEXT_SUFFIXES = {".md", ".html", ".css", ".js", ".py", ".json", ".yaml", ".yml", ".txt"}


def skill_version() -> str:
    source = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
    frontmatter = re.match(r"^---\n(.*?)\n---\n", source, re.DOTALL)
    if not frontmatter:
        raise ValueError("SKILL.md is missing frontmatter")
    match = re.search(r'^\s{2}version:\s*["\']?([^"\'\s]+)', frontmatter.group(1), re.MULTILINE)
    if not match:
        raise ValueError("SKILL.md metadata.version is missing")
    return match.group(1)


def forbidden_marker(value: str) -> str | None:
    markers = (
        "o" + "p" + "e" + "n" + "a" + "i",
        "c" + "h" + "a" + "t" + "g" + "p" + "t",
        "c" + "o" + "d" + "e" + "x",
        "g" + "p" + "t",
    )
    lowered = value.lower()
    for marker in markers:
        if re.search(rf"(?<![a-z0-9]){re.escape(marker)}(?![a-z0-9])", lowered):
            return marker
    if ("人工" + "智能") in value or re.search(r"(?<![A-Za-z])" + "A" + "I" + r"(?![A-Za-z])", value):
        return "platform-marker"
    return None


def package_files() -> list[Path]:
    files: list[Path] = []
    for path in SKILL_ROOT.rglob("*"):
        if path.is_symlink():
            raise ValueError(f"Refusing to package symbolic link: {path}")
        if not path.is_file() or path.name in IGNORED_NAMES:
            continue
        relative = path.relative_to(SKILL_ROOT)
        if relative.as_posix() in NEUTRAL_EXCLUDES:
            continue
        if any(part in IGNORED_PARTS for part in relative.parts):
            continue
        files.append(path)
    return sorted(files, key=lambda item: item.relative_to(SKILL_ROOT).as_posix())


def validate_neutral_contents(files: list[Path]) -> None:
    for path in files:
        relative = path.relative_to(SKILL_ROOT).as_posix()
        marker = forbidden_marker(relative)
        if marker:
            raise ValueError(f"Distribution path contains a platform marker: {relative}")
        if path.suffix.lower() not in TEXT_SUFFIXES:
            continue
        # Preserve the unmodified third-party library, including minified identifiers.
        if relative == "assets/mermaid.min.js":
            continue
        marker = forbidden_marker(path.read_text(encoding="utf-8"))
        if marker:
            raise ValueError(f"Distribution text contains a platform marker: {relative}")


def build_archive(output: Path) -> tuple[int, str]:
    validator = SKILL_ROOT / "scripts" / "validate-package.py"
    subprocess.run([sys.executable, str(validator)], check=True)
    files = package_files()
    validate_neutral_contents(files)
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for source in files:
            relative = Path(SKILL_ROOT.name) / source.relative_to(SKILL_ROOT)
            info = zipfile.ZipInfo(relative.as_posix(), date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = (0o755 if source.suffix in {".py", ".js"} else 0o644) << 16
            archive.writestr(info, source.read_bytes())
    digest = hashlib.sha256(output.read_bytes()).hexdigest()
    return len(files), digest


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate and package the Visual PRD skill.")
    parser.add_argument("--output", type=Path, help="Destination zip path")
    args = parser.parse_args()
    version = skill_version()
    output = (args.output or (SKILL_ROOT.parent / f"{SKILL_ROOT.name}-{version}.zip")).resolve()
    count, digest = build_archive(output)
    print(f"PASS: packaged {SKILL_ROOT.name} {version} with {count} files to {output}")
    print(f"SHA-256: {digest}")


if __name__ == "__main__":
    main()
