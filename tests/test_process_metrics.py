"""Measurement plumbing fixtures, including Windows venv redirector identity."""
from pathlib import Path
import json
import os
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"tools"))
from process_metrics import measure_process


@unittest.skipUnless(os.name=="nt","Native process metrics require Windows")
class NativeProcessMetrics(unittest.TestCase):
    def test_allocation_peak_tracks_runtime_pid_and_venv(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            code = "import sys,os,json\nb=bytearray(64*1024*1024)\nfor i in range(0,len(b),4096): b[i]=1\nprint(json.dumps({'pid':os.getpid(),'prefix':sys.prefix}))"
            result = measure_process([sys.executable,"-c",code],folder,folder/"out.log",folder/"err.log",30,{**os.environ,"PYTHONIOENCODING":"utf-8"})
            child = json.loads((folder/"out.log").read_text(encoding="utf-8"))
            self.assertEqual(result["returncode"],0)
            self.assertEqual(result["pid"],child["pid"])
            self.assertEqual(Path(child["prefix"]),Path(sys.prefix))
            self.assertGreaterEqual(result["peak_working_set_bytes"],64*1024*1024)
            self.assertIsNone(result["memory_error"])

    def test_nonzero_exit_is_preserved(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            result = measure_process([sys.executable,"-c","import sys;sys.exit(7)"],folder,folder/"out.log",folder/"err.log",30)
            self.assertEqual(result["returncode"],7)
            self.assertGreater(result["wall_seconds"],0)
            self.assertGreater(result["peak_working_set_bytes"],0)
            self.assertFalse(result["timed_out"])
