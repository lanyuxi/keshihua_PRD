#!/usr/bin/env python3
"""Validate a Visual PRD UI profile."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from ui_profile import load_ui_profile


def main() -> None:
    parser = argparse.ArgumentParser(description="校验可视化 PRD 界面规范")
    parser.add_argument("profile", type=Path)
    args = parser.parse_args()
    try:
        profile = load_ui_profile(args.profile)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        parser.error(str(error))
    print(f"PASS: 界面规范 {profile['id']} 有效")


if __name__ == "__main__":
    main()
