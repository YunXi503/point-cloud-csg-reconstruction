"""Derive reproducible density descriptors for the four controlled STL samples."""
from __future__ import annotations

import csv
import json
import math
import struct
from pathlib import Path

import numpy as np
from scipy.spatial import cKDTree

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "碩士論文" / "審查報告" / "敏感度分析_260731"
CASES = {
    "階梯狀圓柱": ("零件/Stepped Cylinder.stl", "零件/Stepped Cylinder點雲.csv"),
    "L型板": ("零件/L-Bracket.stl", "零件/L-Bracket點雲.csv"),
    "模型A": ("零件/Model A.stl", "零件/Model A點雲.csv"),
    "盲孔六角座": ("零件/Hex Base with Hole A.stl", "零件/Blind-Hole Hex Base點雲.csv"),
}


def stl_triangles(path: Path) -> np.ndarray:
    raw = path.read_bytes()
    if len(raw) >= 84:
        count = struct.unpack_from("<I", raw, 80)[0]
        if 84 + count * 50 == len(raw):
            values = np.frombuffer(raw, dtype=np.dtype([("n", "<f4", 3), ("v", "<f4", (3, 3)), ("a", "<u2")]), offset=84, count=count)
            return values["v"].astype(float)
    text = raw.decode("utf-8", errors="strict")
    vertices = []
    for line in text.splitlines():
        pieces = line.split()
        if len(pieces) == 4 and pieces[0] == "vertex":
            vertices.append([float(x) for x in pieces[1:]])
    return np.asarray(vertices, dtype=float).reshape(-1, 3, 3)


def load_points(path: Path) -> np.ndarray:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    return np.asarray([[float(row[key]) for key in ("X", "Y", "Z")] for row in rows], dtype=float)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    result = []
    for name, (stl_rel, points_rel) in CASES.items():
        tri = stl_triangles(ROOT / stl_rel)
        cross = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
        area = float(np.linalg.norm(cross, axis=1).sum() / 2.0)
        points = load_points(ROOT / points_rel)
        nearest = cKDTree(points).query(points, k=2)[0][:, 1]
        extent = points.max(axis=0) - points.min(axis=0)
        result.append({
            "case": name,
            "stl": stl_rel,
            "point_csv": points_rel,
            "sample_count": int(len(points)),
            "surface_area_mm2": area,
            "area_per_point_mm2": area / len(points),
            "characteristic_spacing_sqrt_area_per_point_mm": math.sqrt(area / len(points)),
            "nearest_neighbor_mean_mm": float(nearest.mean()),
            "nearest_neighbor_median_mm": float(np.median(nearest)),
            "nearest_neighbor_p95_mm": float(np.quantile(nearest, 0.95)),
            "bounding_box_diagonal_mm": float(np.linalg.norm(extent)),
        })
    payload = {
        "method": "STL triangle areas are summed; point density is A/N; characteristic spacing is sqrt(A/N); nearest-neighbor statistics are computed over the fixed sampled point cloud.",
        "normal_thresholds": [
            {"dot_threshold": t, "angle_tolerance_degrees": math.degrees(math.acos(t))}
            for t in (0.90, 0.93, 0.96)
        ],
        "cases": result,
    }
    (OUT / "sampling_density_evidence.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = [
        "# 點雲密度與門檻設定依據（2026-07-31）",
        "",
        "本表以 STL 三角網格總面積 $A$、固定取樣點數 $N=10,000$ 與實際點雲最近鄰距離計算。$A/N$ 表示平均每點對應面積，$\\sqrt{A/N}$ 作為面積均勻取樣下的特徵點間距尺度；最近鄰統計則直接量測既有取樣結果。這些量僅用於說明目前資料尺度下距離門檻的相對位置，不構成跨模型通用常數。",
        "",
        "| 實作範例 | 網格面積 (mm²) | $A/N$ (mm²/點) | $\\sqrt{A/N}$ (mm) | 最近鄰中位數 (mm) | 最近鄰 P95 (mm) | 模型包圍盒對角線 (mm) |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for row in result:
        lines.append(
            f"| {row['case']} | {row['surface_area_mm2']:.3f} | {row['area_per_point_mm2']:.5f} | "
            f"{row['characteristic_spacing_sqrt_area_per_point_mm']:.3f} | {row['nearest_neighbor_median_mm']:.3f} | "
            f"{row['nearest_neighbor_p95_mm']:.3f} | {row['bounding_box_diagonal_mm']:.3f} |"
        )
    lines.extend([
        "",
        "法向量內積門檻 $t$ 對應的角度容差為 $\\arccos(t)$：0.90 對應 25.842°、0.93 對應 21.565°、0.96 對應 16.260°。因此 0.93 是目前用於區分曲面方向差異的實作設定值；它容許同一連續表面上有限的法向量差異，但不應被描述為真實掃描雜訊下已驗證的最佳門檻。",
    ])
    (OUT / "點雲密度與門檻依據_260731.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
