"""Analytic baseline contracts only; degeneracy diagnostics are reported separately."""
from __future__ import annotations

import hashlib
import importlib
import json
from pathlib import Path
import sys
import unittest

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from geometry_fixtures import plane_fixture, cylinder_fixture


class AnalyticGeometryBaselines(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        catalog = {p["path"]: p["sha256"] for p in json.loads((ROOT/"provenance/copied-sources.json").read_text(encoding="utf-8"))}
        sys.path.insert(0, str(ROOT/"research/tools"))
        cls.modules = {}
        for name in ["infer_stepped_cylinder_chapter3_method", "correct_stepped_cylinder_nls_v2"]:
            path = "research/tools/"+name+".py"
            if hashlib.sha256((ROOT/path).read_bytes()).hexdigest()!=catalog[path]:
                raise RuntimeError("The analytic contract must use the preserved source: "+path)
            cls.modules[name] = importlib.import_module(name)

    def check_plane(self, name):
        points, normals = plane_fixture()
        result = self.modules[name].fit_plane(points,normals)
        self.assertTrue(np.isfinite(result["normal"]).all())
        self.assertLessEqual(float(np.max(result["residual"])),1e-6)
        self.assertGreaterEqual(float(np.min(result["alignment"])),1-1e-8)
        self.assertAlmostEqual(float(result["center"][2]),3.0,places=6)

    def check_cylinder(self, name):
        points, normals = cylinder_fixture()
        result = self.modules[name].fit_cylinder(points,normals)
        self.assertTrue(np.isfinite(result["center"]).all())
        self.assertLessEqual(abs(float(result["radius"])-10.0),1e-6)
        self.assertLessEqual(float(np.max(result["residual"])),1e-6)
        self.assertGreaterEqual(float(np.min(result["alignment"])),1-1e-8)
        self.assertGreaterEqual(abs(float(result["axis"]@np.asarray([0.,0.,1.]))),1-1e-8)

    def test_stepped_plane(self):
        self.check_plane("infer_stepped_cylinder_chapter3_method")

    def test_lbracket_helper_plane(self):
        self.check_plane("correct_stepped_cylinder_nls_v2")

    def test_stepped_cylinder(self):
        self.check_cylinder("infer_stepped_cylinder_chapter3_method")

    def test_lbracket_helper_cylinder(self):
        self.check_cylinder("correct_stepped_cylinder_nls_v2")
