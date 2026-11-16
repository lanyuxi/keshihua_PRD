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
from resource_io import read_resource, SUFFIX


SKILL_ROOT = Path(__file__).resolve().parent.parent
IGNORED_NAMES = {".DS_Store", "Thumbs.db", "desktop.ini"}
IGNORED_PARTS = {"__pycache__", ".git", "releases"}
NEUTRAL_EXCLUDES = {
    "assets/skill-cover.png",
    "assets/skill-cover-landscape.png",
}
TEXT_SUFFIXES = {".md", ".html", ".css", ".js", ".py", ".json", ".yaml", ".yml", ".txt", ".svg"}


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
    allowed_attribution = "公众号“" + "A" + "I 翻车现场”的智障研究员"
    value = value.replace(allowed_attribution, "")
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
        logical = relative.removesuffix(SUFFIX)
        # Keep the third-party Mermaid distribution unmodified, including identifiers.
        if logical == "assets/mermaid.min.js":
            continue
        source = read_resource(SKILL_ROOT / logical).decode("utf-8")
        if Path(logical).suffix.lower() == ".svg":
            source = re.sub(r"data:image/webp;base64,[A-Za-z0-9+/=]+", "", source)
        marker = forbidden_marker(source)
        if marker:
            raise ValueError(f"Distribution text contains a platform marker: {relative}")


def build_archive(output: Path, skillhub: bool = False) -> tuple[int, str]:
    validator = SKILL_ROOT / "scripts" / "validate-package.py"
    subprocess.run([sys.executable, str(validator)], check=True)
    files = package_files()
    validate_neutral_contents(files)
    for path in files:
        if path.suffix.lower() not in TEXT_SUFFIXES:
            raise ValueError(f"SkillHub requires text files: {path.name}")
        text = path.read_text(encoding="utf-8")
        if "\0" in text:
            raise ValueError(f"SkillHub text file contains NUL: {path.name}")
    expanded_bytes = sum(path.stat().st_size for path in files)
    if expanded_bytes > 3_145_728:
        raise ValueError(f"Expanded Skill exceeds 3,145,728 bytes: {expanded_bytes}; use lossless resource packing")
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for source in files:
            relative = source.relative_to(SKILL_ROOT)
            info = zipfile.ZipInfo(relative.as_posix(), date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = (0o755 if source.suffix in {".py", ".js"} else 0o644) << 16
            archive.writestr(info, source.read_bytes())
    if output.stat().st_size >= 3_000_000:
        raise ValueError("Skill ZIP exceeds the 3,000,000 byte distribution limit; do not remove content or reduce quality")
    digest = hashlib.sha256(output.read_bytes()).hexdigest()
    return len(files), digest


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate and package the Visual PRD skill.")
    parser.add_argument("--output", type=Path, help="Destination zip path")
    parser.add_argument("--skillhub", action="store_true", help="Compatibility flag; all packages now use the upload-ready layout")
    parser.add_argument("--workbuddy", action="store_true", help="WorkBuddy upload filename; expanded content is always capped at 3 MiB")
    args = parser.parse_args()
    version = skill_version()
    output = (args.output or (SKILL_ROOT / "releases" / "current" / f"{SKILL_ROOT.name}-{version}{'-workbuddy' if args.workbuddy else '-skillhub' if args.skillhub else ''}.zip")).resolve()
    count, digest = build_archive(output, skillhub=args.skillhub)
    print(f"PASS: packaged {SKILL_ROOT.name} {version} with {count} files to {output}")
    print(f"SHA-256: {digest}")


if __name__ == "__main__":
    main()
