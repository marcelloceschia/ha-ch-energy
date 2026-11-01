#!/usr/bin/env python3
"""Validate an explicitly selected release; emit machine-readable metadata."""
import argparse
import json
from pathlib import Path
import re


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", required=True)
    parser.add_argument("--tag", required=True)
    parser.add_argument("--sha", required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    args = parser.parse_args()
    number = r"(?:0|[1-9][0-9]*)"
    if not re.fullmatch(rf"{number}\.{number}\.{number}(?:-beta\.[1-9][0-9]*)?", args.version):
        parser.error("Version must be X.Y.Z or X.Y.Z-beta.N (N >= 1; no leading zeros)")
    if args.tag != "v" + args.version:
        parser.error("Tag must equal v + version")
    if not re.fullmatch(r"[0-9a-f]{40}", args.sha):
        parser.error("Commit must be a full lowercase 40-character SHA")
    if json.loads(args.manifest.read_text())["version"] != args.version:
        parser.error("Manifest version does not match the requested version")
    print(json.dumps({"version": args.version, "tag": args.tag, "sha": args.sha,
                      "prerelease": "-beta." in args.version}))


if __name__ == "__main__":
    main()
