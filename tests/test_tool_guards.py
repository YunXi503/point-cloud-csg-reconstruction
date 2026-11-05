"""Software guard fixtures only; these do not simulate or validate thesis results."""
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class ReproductionGuards(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / "tools").mkdir()
        (self.root / "examples").mkdir()
        (self.root / "provenance").mkdir()
        shutil.copyfile(ROOT / "tools/verify-reproduction.py", self.root / "tools/verify-reproduction.py")
        shutil.copyfile(ROOT / "tools/inference_sources.py", self.root / "tools/inference_sources.py")
        source = b"raise AssertionError('Guard failure: a research process must not run in this fixture')\n"
        (self.root / "shared.py").write_bytes(source)
        (self.root / "model.py").write_bytes(source)
        (self.root / "input.csv").write_bytes(b"software guard fixture\n")
        self.cases = [{"id": name, "entrypoint": file, "recorded_program_sha256": digest(source),
                       "input": "input.csv", "recorded_input_sha256": digest(b"software guard fixture\n"), "output_checks": []}
                      for name, file in [("stepped-cylinder", "shared.py"), ("model-a", "model.py")]]
        (self.root / "provenance/inference-dependencies.json").write_text(
            json.dumps({"case_support_programs": {case["id"]: [] for case in self.cases}}), encoding="utf-8")

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


class InferenceDependencyGuards(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        for folder in ["tools", "examples", "provenance"]:
            (self.root / folder).mkdir()
        for name in ["verify-reproduction.py", "run-from-point-cloud.py", "inference_sources.py"]:
            shutil.copyfile(ROOT / "tools" / name, self.root / "tools" / name)
        source = b"raise AssertionError('No research process should run in a dependency failure fixture')\n"
        for name in ["shared.py", "model.py", "support.py"]:
            (self.root / name).write_bytes(source)
        (self.root / "input.csv").write_bytes(b"software fixture\n")
        self.cases = [{"id": name, "entrypoint": file, "recorded_program_sha256": digest(source),
                       "input": "input.csv", "recorded_input_sha256": digest(b"software fixture\n"), "output_checks": []}
                      for name, file in [("stepped-cylinder", "shared.py"), ("model-a", "model.py")]]
        self.bindings = {"case_support_programs": {"stepped-cylinder": [], "model-a": [
            {"path": "support.py", "sha256": digest(source)}]}}
        (self.root / "examples/cases.json").write_text(json.dumps(self.cases), encoding="utf-8")
        (self.root / "examples/segmentation.json").write_text(json.dumps([
            {"id": "model-a", "source": "model.py", "point_cloud": "input.csv", "runtime": "net48"}]), encoding="utf-8")
        self.save_bindings()

    def save_bindings(self):
        (self.root / "provenance/inference-dependencies.json").write_text(json.dumps(self.bindings), encoding="utf-8")

    def run_entry(self, script):
        command = [sys.executable, str(self.root / "tools" / script), "--case", "model-a", "--output-dir", str(self.root / "out")]
        if script == "run-from-point-cloud.py":
            command += ["--msbuild", str(self.root / "must-not-start.exe")]
        return subprocess.run(command, capture_output=True, text=True, encoding="utf-8",
                              env={**os.environ, "PYTHONIOENCODING": "utf-8"})

    def assert_blocked(self, script, report_name):
        result = self.run_entry(script)
        self.assertEqual(result.returncode, 2, result.stderr)
        report = json.loads((self.root / "out" / report_name).read_text(encoding="utf-8"))
        self.assertEqual(report["status"], "blocked-inference-source-version-mismatch")
        self.assertFalse((self.root / "out/runner").exists())
        self.assertFalse((self.root / "out/model-a.stdout.log").exists())

    def test_changed_support_program_blocks_csv_entry_before_execution(self):
        (self.root / "support.py").write_bytes(b"changed helper\n")
        self.assert_blocked("verify-reproduction.py", "reproduction-results.json")

    def test_missing_support_program_blocks_csv_entry_before_execution(self):
        (self.root / "support.py").unlink()
        self.assert_blocked("verify-reproduction.py", "reproduction-results.json")

    @unittest.skipUnless(sys.platform == "win32", "The C# pipeline is supported on Windows")
    def test_support_drift_blocks_point_cloud_entry_before_build(self):
        (self.root / "support.py").write_bytes(b"changed helper\n")
        self.assert_blocked("run-from-point-cloud.py", "pipeline-results.json")

    def test_intact_main_and_support_programs_pass_preflight(self):
        from inference_sources import check_inference_programs
        checks = check_inference_programs(self.root, self.cases)
        self.assertEqual(len(checks), 3)
        self.assertTrue(all(check["matches"] for check in checks))

    def test_unselected_support_program_does_not_block_preflight(self):
        from inference_sources import check_inference_programs
        (self.root / "support.py").write_bytes(b"unused changed helper\n")
        checks = check_inference_programs(self.root, [self.cases[0]])
        self.assertTrue(all(check["matches"] for check in checks))

    def test_dependency_path_cannot_escape_repository(self):
        from inference_sources import check_inference_programs
        self.bindings["case_support_programs"]["model-a"][0]["path"] = "../outside.py"
        self.save_bindings()
        with self.assertRaisesRegex(ValueError, "escaped"):
            check_inference_programs(self.root, self.cases)


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
