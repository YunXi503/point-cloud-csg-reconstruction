"""Check recorded main and local-support Python sources without importing them."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path


def check_inference_programs(root: Path, cases: list[dict]) -> list[dict]:
    root = root.resolve()
    bindings = json.loads((root / "provenance/inference-dependencies.json").read_text(encoding="utf-8"))
    expected = {}
    for case in cases:
        programs = [{"path": case["entrypoint"], "sha256": case["recorded_program_sha256"]}]
        programs += bindings["case_support_programs"][case["id"]]
        for program in programs:
            relative, digest = program["path"], program["sha256"]
            if relative in expected and expected[relative] != digest:
                raise ValueError("Conflicting recorded source hashes: " + relative)
            expected[relative] = digest
    checks = []
    for relative, digest in sorted(expected.items()):
        target = (root / relative).resolve()
        if Path(relative).is_absolute() or not target.is_relative_to(root):
            raise ValueError("Inference source path escaped the repository: " + relative)
        actual = hashlib.sha256(target.read_bytes()).hexdigest() if target.is_file() else None
        checks.append({"path": relative, "expected_sha256": digest, "actual_sha256": actual,
                       "matches": actual == digest})
    return checks
