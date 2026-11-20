#!/usr/bin/env python3
"""Verify local research artifact bytes without loading their contents as data."""

import argparse
import hashlib
import json
import os
import re
import sys
from pathlib import Path, PurePosixPath


def valid_entry(entry):
    if not isinstance(entry, dict):
        return False
    path = entry.get("path")
    size = entry.get("size_bytes")
    digest = entry.get("sha256")
    if not isinstance(path, str) or not path:
        return False
    parts = PurePosixPath(path)
    return (
        not parts.is_absolute()
        and ".." not in parts.parts
        and parts.as_posix() == path
        and path != "."
        and type(size) is int
        and size >= 0
        and isinstance(digest, str)
        and re.fullmatch(r"[0-9a-f]{64}", digest) is not None
    )


def signature(stat):
    return (stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns)


def verify(root, entry):
    path = root / entry["path"]
    try:
        if not path.resolve().is_relative_to(root):
            return "invalid"
        if not path.exists():
            return "missing"
        if not path.is_file():
            return "unreadable"
        with path.open("rb") as artifact:
            initial = signature(os.fstat(artifact.fileno()))
            if initial[2] != entry["size_bytes"]:
                return "mismatched"
            digest = hashlib.sha256()
            while block := artifact.read(8 * 1024 * 1024):
                digest.update(block)
            final = signature(os.fstat(artifact.fileno()))
        if initial != final or digest.hexdigest() != entry["sha256"]:
            return "mismatched"
        return "verified"
    except FileNotFoundError:
        return "missing"
    except (OSError, RuntimeError, ValueError):
        return "unreadable"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="repository root (default: the parent of this script's directory)",
    )
    parser.add_argument(
        "--inventory",
        type=Path,
        default=Path("experiments/artifact-inventory.json"),
        help="inventory path; relative paths are resolved under --root",
    )
    args = parser.parse_args()
    counts = dict(
        listed=0, verified=0, missing=0, mismatched=0, unreadable=0, invalid=0, inventory_errors=0
    )
    try:
        root = args.root.resolve()
        inventory = args.inventory if args.inventory.is_absolute() else root / args.inventory
        with inventory.open("r", encoding="utf-8") as handle:
            document = json.load(handle)
        if (
            not isinstance(document, dict)
            or document.get("schema_version") != 1
            or not isinstance(document.get("artifacts"), list)
            or not document["artifacts"]
        ):
            raise ValueError("invalid inventory")
        entries = document["artifacts"]
        counts["listed"] = len(entries)
        seen = set()
        for entry in entries:
            if not valid_entry(entry) or entry["path"] in seen:
                counts["invalid"] += 1
                continue
            seen.add(entry["path"])
            counts[verify(root, entry)] += 1
    except (OSError, RuntimeError, ValueError):
        counts["inventory_errors"] += 1
    print(" ".join(f"{name}={count}" for name, count in counts.items()))
    return int(counts["verified"] != counts["listed"] or counts["inventory_errors"] != 0)


if __name__ == "__main__":
    sys.exit(main())
