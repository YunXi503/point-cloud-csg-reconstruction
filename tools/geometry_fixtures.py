"""Analytic software fixtures; these are not thesis datasets or scan evidence."""
from __future__ import annotations

import numpy as np


def plane_fixture():
    x, y = np.meshgrid(np.linspace(-2, 2, 5), np.linspace(-2, 2, 5))
    points = np.column_stack((x.ravel(), y.ravel(), np.full(x.size, 3.0)))
    return points, np.tile([0.0, 0.0, 1.0], (len(points), 1))


def cylinder_fixture():
    angle, z = np.meshgrid(np.linspace(0, 2 * np.pi, 32, endpoint=False), np.linspace(-5, 5, 5))
    angle, z = angle.ravel(), z.ravel()
    normals = np.column_stack((np.cos(angle), np.sin(angle), np.zeros(len(angle))))
    return np.column_stack((2 + 10 * np.cos(angle), -3 + 10 * np.sin(angle), z)), normals


SURFACE_FIXTURES = ("plane", "cylinder", "empty", "single", "two", "collinear", "coincident", "zero_normals", "nan", "inf")
CIRCLE_FIXTURES = ("arc_360", "arc_10", "arc_0.001", "arc_0.00001", "collinear", "coincident")


def surface_fixture(name):
    if name == "plane":
        return plane_fixture()
    if name in {"empty", "single", "two"}:
        points, normals = plane_fixture()
        size = {"empty": 0, "single": 1, "two": 2}[name]
        return points[:size], normals[:size]
    if name in {"collinear", "coincident"}:
        x = np.linspace(-2, 2, 25) if name == "collinear" else np.zeros(25)
        return np.column_stack((x, np.zeros(25), np.full(25, 3.0))), np.tile([0., 0., 1.], (25, 1))
    points, normals = cylinder_fixture()
    if name == "zero_normals":
        normals[:] = 0
    elif name in {"nan", "inf"}:
        points[0, 0] = np.nan if name == "nan" else np.inf
    elif name != "cylinder":
        raise ValueError(name)
    return points, normals


def circle_fixture(name):
    if name.startswith("arc_"):
        degrees = float(name.removeprefix("arc_"))
        radians = np.deg2rad(degrees)
        angle = np.linspace(-radians / 2, radians / 2, 64, endpoint=degrees != 360)
        return np.column_stack((2 + 10 * np.cos(angle), -3 + 10 * np.sin(angle))), {"center": [2., -3.], "radius": 10.}
    if name == "collinear":
        return np.column_stack((np.linspace(-2, 2, 64), np.zeros(64))), None
    if name == "coincident":
        return np.tile([2., -3.], (64, 1)), None
    raise ValueError(name)
