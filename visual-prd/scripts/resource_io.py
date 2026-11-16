#!/usr/bin/env python3
"""Read and losslessly pack large offline assets using only the standard library."""
import argparse
import base64
import hashlib
import json
import lzma
import sys
from pathlib import Path

SUFFIX = ".packed.txt"


def packed_path(path):
    return path.with_name(path.name + SUFFIX)


def read_resource(path):
    path = Path(path)
    if path.is_file():
        return path.read_bytes()
    record = json.loads(packed_path(path).read_text(encoding="utf-8"))
    if record["codec"] != "xz-base85-v1":
        raise ValueError("Unsupported resource encoding")
    data = lzma.decompress(base64.b85decode(record["data"]))
    if len(data) != record["bytes"] or hashlib.sha256(data).hexdigest() != record["sha256"]:
        raise ValueError(f"Resource integrity check failed: {path.name}")
    return data


def pack_resource(data):
    options = [{"id": lzma.FILTER_LZMA2, "preset": 9 | lzma.PRESET_EXTREME, "lc": 3, "lp": 0, "pb": pb} for pb in (0, 2)]
    compressed = min((lzma.compress(data, filters=[option]) for option in options), key=len)
    record = {"codec": "xz-base85-v1", "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest(), "data": base64.b85encode(compressed).decode("ascii")}
    return (json.dumps(record, separators=(",", ":")) + "\n").encode("utf-8")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", type=Path, help="Logical resource path, relative to the skill directory")
    parser.add_argument("--pack", action="store_true", help="Pack input bytes without changing the input file")
    parser.add_argument("--output", type=Path, help="Write to this path instead of standard output")
    args = parser.parse_args()
    path = args.path if args.path.is_absolute() else Path(__file__).resolve().parent.parent / args.path
    data = pack_resource(path.read_bytes()) if args.pack else read_resource(path)
    if args.output:
        args.output.write_bytes(data)
    else:
        sys.stdout.buffer.write(data)
