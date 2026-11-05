from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description="Compare two complete method-inference reruns by filename and SHA-256.")
    parser.add_argument("--case", required=True)
    parser.add_argument("--run-1", required=True, type=Path)
    parser.add_argument("--run-2", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    arguments = parser.parse_args()

    run_1 = arguments.run_1.resolve()
    run_2 = arguments.run_2.resolve()
    files_1 = {path.name: path for path in run_1.iterdir() if path.is_file()}
    files_2 = {path.name: path for path in run_2.iterdir() if path.is_file()}
    filenames_match = sorted(files_1) == sorted(files_2)
    names = sorted(set(files_1) | set(files_2))
    comparisons = []
    for name in names:
        first = files_1.get(name)
        second = files_2.get(name)
        hash_1 = sha256(first) if first is not None else None
        hash_2 = sha256(second) if second is not None else None
        comparisons.append(
            {
                "filename": name,
                "run_1_sha256": hash_1,
                "run_2_sha256": hash_2,
                "match": hash_1 is not None and hash_1 == hash_2,
            }
        )
    all_match = filenames_match and all(value["match"] for value in comparisons)
    payload = {
        "schema_version": "1.0",
        "case": arguments.case,
        "criterion": "two complete inference reruns must have identical filenames and SHA-256 hashes",
        "run_1": run_1.name,
        "run_2": run_2.name,
        "filenames_match": filenames_match,
        "files": comparisons,
        "overall": "PASS" if all_match else "FAIL",
    }
    arguments.output.resolve().write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    if not all_match:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
