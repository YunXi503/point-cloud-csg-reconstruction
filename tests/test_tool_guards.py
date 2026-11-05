"""Software guard fixtures only; these do not simulate or validate thesis results."""
from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class ReproductionGuards(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / "tools").mkdir()
        (self.root / "examples").mkdir()
        shutil.copyfile(ROOT / "tools/verify-reproduction.py", self.root / "tools/verify-reproduction.py")
        source = b"raise AssertionError('Guard failure: a research process must not run in this fixture')\n"
        (self.root / "shared.py").write_bytes(source)
        (self.root / "model.py").write_bytes(source)
        (self.root / "input.csv").write_bytes(b"software guard fixture\n")
        self.cases = [{"id": name, "entrypoint": file, "recorded_program_sha256": digest(source),
                       "input": "input.csv", "recorded_input_sha256": digest(b"software guard fixture\n"), "output_checks": []}
                      for name, file in [("stepped-cylinder", "shared.py"), ("model-a", "model.py")]]

    def run_guard(self):
        (self.root / "examples/cases.json").write_text(json.dumps(self.cases), encoding="utf-8")
        return subprocess.run([sys.executable, str(self.root / "tools/verify-reproduction.py"), "--case", "model-a", "--output-dir", str(self.root / "out")], capture_output=True, text=True)

    def test_input_drift_returns_nonzero_without_running_algorithm(self):
        self.cases[1]["recorded_input_sha256"] = "0" * 64
        self.assertEqual(self.run_guard().returncode, 2)
        report = json.loads((self.root / "out/reproduction-results.json").read_text(encoding="utf-8"))
        self.assertEqual(report["cases"][0]["status"], "blocked-input-version-mismatch")

    def test_helper_drift_is_blocked(self):
        self.cases[0]["recorded_program_sha256"] = "0" * 64
        self.assertEqual(self.run_guard().returncode, 2)
        report = json.loads((self.root / "out/reproduction-results.json").read_text(encoding="utf-8"))
        self.assertEqual(report["status"], "blocked-shared-program-version-mismatch")

    def test_main_program_drift_is_blocked(self):
        self.cases[1]["recorded_program_sha256"] = "0" * 64
        self.assertNotEqual(self.run_guard().returncode, 0)

    def test_existing_output_is_preserved(self):
        (self.root / "out").mkdir()
        sentinel = self.root / "out/sentinel.txt"
        sentinel.write_bytes(b"keep this existing work")
        self.assertNotEqual(self.run_guard().returncode, 0)
        self.assertEqual(sentinel.read_bytes(), b"keep this existing work")


@unittest.skipUnless(shutil.which("node"), "Node.js is required for package-integrity guard tests")
class PackageGuards(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        for folder in ["tools", "provenance", "examples"]:
            (self.root / folder).mkdir()
        shutil.copyfile(ROOT / "tools/verify-package.mjs", self.root / "tools/verify-package.mjs")
        (self.root / "payload.txt").write_bytes(b"reference bytes\n")
        (self.root / "examples/cases.json").write_text(json.dumps([{"entrypoint": "payload.txt", "input": "payload.txt", "reference_directory": "examples"}]), encoding="utf-8")
        self.manifest = {"packaging_version": "software-fixture", "copied_sources": [], "files": [
            {"path": name, "sha256": digest((self.root / name).read_bytes())}
            for name in ["payload.txt", "tools/verify-package.mjs", "examples/cases.json"]]}

    def verify(self):
        (self.root / "provenance/release-manifest.json").write_text(json.dumps(self.manifest), encoding="utf-8")
        return subprocess.run(["node", str(self.root / "tools/verify-package.mjs")], capture_output=True, text=True)

    def test_intact_package_passes(self):
        self.assertEqual(self.verify().returncode, 0)

    def test_changed_file_is_detected(self):
        (self.root / "payload.txt").write_bytes(b"changed bytes\n")
        self.assertNotEqual(self.verify().returncode, 0)

    def test_unlisted_file_is_detected(self):
        (self.root / "unexpected.txt").write_bytes(b"unreviewed file")
        self.assertNotEqual(self.verify().returncode, 0)

    def test_manifest_path_traversal_is_rejected(self):
        self.manifest["files"][0]["path"] = "../outside.txt"
        self.assertNotEqual(self.verify().returncode, 0)


class NumericComparisonGuards(unittest.TestCase):
    def test_overflow_is_not_mistaken_for_exact_numeric_equality(self):
        spec = importlib.util.spec_from_file_location("pipeline_driver", ROOT / "tools/run-from-point-cloud.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        self.assertFalse(module.token_equal("1e309", "2e309"))
        self.assertTrue(module.token_equal("1.0", "1"))
        self.assertFalse(module.token_equal("1.0000000000000002", "1"))


@unittest.skipUnless(shutil.which("node"), "Node.js is required for release-sealing guard tests")
class SealGuards(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        for folder in ["tools", "provenance", "examples"]:
            (self.root / folder).mkdir()
        shutil.copyfile(ROOT / "tools/seal-release.mjs", self.root / "tools/seal-release.mjs")
        (self.root / "payload.txt").write_bytes(b"protected software fixture\n")
        expected = digest((self.root / "payload.txt").read_bytes())
        (self.root / "provenance/copied-sources.json").write_text(json.dumps([{"path": "payload.txt", "sha256": expected}]), encoding="utf-8")
        (self.root / "provenance/source-versions.json").write_text(json.dumps({"packaging_version": "software-fixture", "date": "2026-11-05"}), encoding="utf-8")
        (self.root / "examples/cases.json").write_text(json.dumps([{"id": "fixture", "entrypoint": "payload.txt", "input": "payload.txt", "recorded_program_sha256": expected, "recorded_input_sha256": expected}]), encoding="utf-8")

    def test_intact_release_can_be_sealed(self):
        result = subprocess.run(["node", str(self.root / "tools/seal-release.mjs")], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_reseal_does_not_bless_changed_research_sources(self):
        target = self.root / "provenance/release-manifest.json"
        target.write_bytes(b"preserve previous release manifest")
        (self.root / "payload.txt").write_bytes(b"changed protected source")
        result = subprocess.run(["node", str(self.root / "tools/seal-release.mjs")], capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(target.read_bytes(), b"preserve previous release manifest")


if __name__ == "__main__":
    unittest.main()
