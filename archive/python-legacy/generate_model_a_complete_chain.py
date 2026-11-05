from pathlib import Path
import csv
import math

import numpy as np
import pandas as pd
from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parents[1]
PART_DIR = ROOT / "零件"
RESULT_PATH = PART_DIR / "Result_Model A.csv"
FACE_PATH = PART_DIR / "FaceSummary_Model A.csv"
TOPOLOGY_PATH = PART_DIR / "TopologyEdges_Model A.csv"
PRIMITIVE_PATH = PART_DIR / "PrimitiveCandidates_Model A.csv"
TOPOLOGY_PNG = ROOT / "Model A Topology.png"
CSG_PNG = ROOT / "Model A CSG.png"

ADJACENCY_EPS = 2.5
SMALL_FACE_POINTS = 30
MIN_PLANE_PLANE_CONTACT = 15
MIN_PLANE_CYL_CONTACT = 15
MIN_CYL_CYL_CONTACT = 18
MIN_ENDCAP_CONTACT = 20


def fmt(value, digits=6):
    if value == "":
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, int):
        return str(value)
    return f"{float(value):.{digits}f}"


def unit(v):
    arr = np.asarray(v, dtype=float)
    n = np.linalg.norm(arr)
    if n < 1e-12:
        return arr
    return arr / n


def circle_fit(a, b):
    a = np.asarray(a, dtype=float)
    b = np.asarray(b, dtype=float)
    mat = np.column_stack([a, b, np.ones_like(a)])
    rhs = -(a * a + b * b)
    sol, *_ = np.linalg.lstsq(mat, rhs, rcond=None)
    aa, bb, cc = sol
    c1 = -aa / 2.0
    c2 = -bb / 2.0
    r2 = c1 * c1 + c2 * c2 - cc
    radius = math.sqrt(max(float(r2), 0.0))
    radial = np.sqrt((a - c1) ** 2 + (b - c2) ** 2)
    residual = np.abs(radial - radius)
    return c1, c2, radius, float(np.median(residual)), float(np.std(residual))


def cylinder_geometry(group, feature_type):
    if feature_type == "Cylinder_axisX":
        axis = (1.0, 0.0, 0.0)
        a = group["Y"].to_numpy(dtype=float)
        b = group["Z"].to_numpy(dtype=float)
        na = group["NY"].to_numpy(dtype=float)
        nb = group["NZ"].to_numpy(dtype=float)
        axis_min = group["X"].min()
        axis_max = group["X"].max()
    else:
        axis = (0.0, 1.0, 0.0)
        a = group["X"].to_numpy(dtype=float)
        b = group["Z"].to_numpy(dtype=float)
        na = group["NX"].to_numpy(dtype=float)
        nb = group["NZ"].to_numpy(dtype=float)
        axis_min = group["Y"].min()
        axis_max = group["Y"].max()

    c1, c2, radius, med_res, std_res = circle_fit(a, b)
    rr = np.sqrt((a - c1) ** 2 + (b - c2) ** 2)
    radial_alignment = ((a - c1) * na + (b - c2) * nb) / np.maximum(rr, 1e-9)
    radial_mean = float(radial_alignment.mean())
    return {
        "AxisX": axis[0],
        "AxisY": axis[1],
        "AxisZ": axis[2],
        "CircleC1": c1,
        "CircleC2": c2,
        "Radius": radius,
        "RadiusResidualMedian": med_res,
        "RadiusResidualStd": std_res,
        "RadialNormalMean": radial_mean,
        "AxisMin": axis_min,
        "AxisMax": axis_max,
        "BooleanRole": "DifferenceFace" if radial_mean < -0.50 else "UnionFace",
    }


def boundary_count(group):
    xyz = group[["X", "Y", "Z"]].to_numpy(dtype=float)
    center = xyz.mean(axis=0)
    dist = np.linalg.norm(xyz - center, axis=1)
    if len(dist) == 0:
        return 0
    hi = np.quantile(dist, 0.92)
    return int((dist >= hi).sum())


def build_face_summary(df):
    faces = []
    for cid, group in df[df["ClusterID"] >= 0].groupby("ClusterID"):
        feature_type = group["FeatureType"].mode().iat[0]
        normal = unit(group[["NX", "NY", "NZ"]].mean().to_numpy(dtype=float))
        row = {
            "ClusterID": int(cid),
            "FeatureType": feature_type,
            "PointCount": len(group),
            "QualityFlag": "SmallOutputFace" if len(group) < SMALL_FACE_POINTS else "MajorFace",
            "CenterX": group["X"].mean(),
            "CenterY": group["Y"].mean(),
            "CenterZ": group["Z"].mean(),
            "NX": normal[0],
            "NY": normal[1],
            "NZ": normal[2],
            "AxisX": 0.0,
            "AxisY": 0.0,
            "AxisZ": 0.0,
            "MinX": group["X"].min(),
            "MaxX": group["X"].max(),
            "MinY": group["Y"].min(),
            "MaxY": group["Y"].max(),
            "MinZ": group["Z"].min(),
            "MaxZ": group["Z"].max(),
            "CircleC1": "",
            "CircleC2": "",
            "Radius": "",
            "RadiusResidualMedian": "",
            "RadiusResidualStd": "",
            "RadialNormalMean": "",
            "AxisMin": "",
            "AxisMax": "",
            "BooleanRole": "UnionFace",
            "BoundaryPointCount": boundary_count(group),
        }
        if feature_type.startswith("Cylinder"):
            row.update(cylinder_geometry(group, feature_type))
        faces.append(row)
    faces.sort(key=lambda r: r["ClusterID"])
    return faces


def write_face_summary(faces):
    fields = [
        "ClusterID",
        "FeatureType",
        "PointCount",
        "QualityFlag",
        "CenterX",
        "CenterY",
        "CenterZ",
        "NX",
        "NY",
        "NZ",
        "AxisX",
        "AxisY",
        "AxisZ",
        "MinX",
        "MaxX",
        "MinY",
        "MaxY",
        "MinZ",
        "MaxZ",
        "CircleC1",
        "CircleC2",
        "Radius",
        "RadiusResidualMedian",
        "RadiusResidualStd",
        "RadialNormalMean",
        "AxisMin",
        "AxisMax",
        "BooleanRole",
        "BoundaryPointCount",
    ]
    with FACE_PATH.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for face in faces:
            writer.writerow({k: fmt(face[k]) for k in fields})


def contact_metrics(a, b, eps=ADJACENCY_EPS, chunk=256):
    if len(a) > len(b):
        swapped = True
        a, b = b, a
    else:
        swapped = False
    best = float("inf")
    contact_a = 0
    contact_b_mask = np.zeros(len(b), dtype=bool)
    for i in range(0, len(a), chunk):
        c = a[i : i + chunk]
        diff = c[:, None, :] - b[None, :, :]
        d2 = np.einsum("ijk,ijk->ij", diff, diff)
        best = min(best, float(d2.min()))
        near = d2 <= eps * eps
        contact_a += int(near.any(axis=1).sum())
        contact_b_mask |= near.any(axis=0)
    contact_b = int(contact_b_mask.sum())
    if swapped:
        contact_a, contact_b = contact_b, contact_a
    return math.sqrt(best), contact_a, contact_b


def axis_vector(face):
    return np.array([face["AxisX"], face["AxisY"], face["AxisZ"]], dtype=float)


def normal_vector(face):
    return np.array([face["NX"], face["NY"], face["NZ"]], dtype=float)


def classify_edge(a, b):
    fa = a["FeatureType"]
    fb = b["FeatureType"]
    a_cyl = fa.startswith("Cylinder")
    b_cyl = fb.startswith("Cylinder")

    if not a_cyl and not b_cyl:
        dot = abs(float(np.dot(normal_vector(a), normal_vector(b))))
        if dot < 0.20:
            return "OrthogonalAdjacency"
        if dot < 0.85:
            return "ObliqueAdjacency"
        return "ParallelAdjacency"

    if a_cyl and b_cyl:
        dot = abs(float(np.dot(axis_vector(a), axis_vector(b))))
        if dot > 0.95:
            return "CoaxialCylinderRelation"
        return "OrthogonalCylinderIntersection"

    cyl = a if a_cyl else b
    plane = b if a_cyl else a
    axis_dot = abs(float(np.dot(axis_vector(cyl), normal_vector(plane))))
    if axis_dot > 0.85:
        return "EndCap"
    return "SideBoundary"


def edge_rule_pass(a, b, edge_type, min_distance_value, contact_a, contact_b):
    if min_distance_value > ADJACENCY_EPS:
        return False, "Rejected: beyond adjacency distance."

    if a["QualityFlag"] == "SmallOutputFace" or b["QualityFlag"] == "SmallOutputFace":
        return False, "Rejected: small output face retained in FaceSummary but excluded from formal topology."

    support = min(contact_a, contact_b)
    if edge_type in {"OrthogonalAdjacency", "ObliqueAdjacency"}:
        if support >= MIN_PLANE_PLANE_CONTACT:
            return True, "Accepted: major plane-plane contact with sufficient boundary support."
        return False, "Rejected: insufficient plane-plane contact support."

    if edge_type == "ParallelAdjacency":
        return False, "Rejected: parallel faces are treated as merge/fragment candidates, not formal adjacency."

    if edge_type == "EndCap":
        if support >= MIN_ENDCAP_CONTACT:
            return True, "Accepted: cylinder axis aligns with plane normal and contact support is sufficient."
        return False, "Rejected: insufficient end-cap support."

    if edge_type == "SideBoundary":
        if support >= MIN_PLANE_CYL_CONTACT:
            return True, "Accepted: cylinder side boundary contact with sufficient support."
        return False, "Rejected: insufficient side-boundary support."

    if edge_type == "OrthogonalCylinderIntersection":
        if support >= MIN_CYL_CYL_CONTACT:
            return True, "Accepted: major cylinder-cylinder intersection with sufficient support."
        return False, "Rejected: insufficient cylinder-cylinder contact support."

    if edge_type == "CoaxialCylinderRelation":
        return False, "Rejected: coaxial cylinders are treated as concentric/boolean candidates, not direct topology edges."

    return False, "Rejected: unsupported edge type."


def build_topology(df, faces):
    face_by_id = {f["ClusterID"]: f for f in faces}
    xyz_by_id = {
        int(cid): group[["X", "Y", "Z"]].to_numpy(dtype=float)
        for cid, group in df[df["ClusterID"] >= 0].groupby("ClusterID")
    }
    edges = []
    ids = sorted(xyz_by_id)
    for i, a in enumerate(ids):
        for b in ids[i + 1 :]:
            d, contact_a, contact_b = contact_metrics(xyz_by_id[a], xyz_by_id[b])
            edge_type = classify_edge(face_by_id[a], face_by_id[b])
            accepted, note = edge_rule_pass(face_by_id[a], face_by_id[b], edge_type, d, contact_a, contact_b)
            if accepted:
                edges.append(
                    {
                        "FromClusterID": a,
                        "ToClusterID": b,
                        "EdgeType": edge_type,
                        "MinDistance": d,
                        "ContactA": contact_a,
                        "ContactB": contact_b,
                        "Confidence": "High" if min(contact_a, contact_b) >= 30 else "Medium",
                        "RuleNote": note,
                    }
                )
    return edges


def write_topology(edges):
    fields = ["FromClusterID", "ToClusterID", "EdgeType", "MinDistance", "ContactA", "ContactB", "Confidence", "RuleNote"]
    with TOPOLOGY_PATH.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for edge in edges:
            writer.writerow({k: fmt(edge[k]) for k in fields})


def write_primitives(faces):
    union_faces = [f for f in faces if f["BooleanRole"] == "UnionFace"]
    difference_faces = [f for f in faces if f["BooleanRole"] == "DifferenceFace"]

    primitives = []
    if union_faces:
        xs = [v for f in union_faces for v in (f["MinX"], f["MaxX"])]
        ys = [v for f in union_faces for v in (f["MinY"], f["MaxY"])]
        zs = [v for f in union_faces for v in (f["MinZ"], f["MaxZ"])]
        primitives.append(
            {
                "PrimitiveType": "ModelA_AdditiveShell",
                "RelatedClusters": ";".join(str(f["ClusterID"]) for f in union_faces),
                "Length": max(xs) - min(xs),
                "Width": max(ys) - min(ys),
                "Height": max(zs) - min(zs),
                "Radius": "",
                "Depth": "",
                "BooleanType": "Union",
                "Confidence": "Medium",
                "EvidenceNote": "Union faces are planes and cylinders with outward radial normals.",
            }
        )

    for face in difference_faces:
        cid = face["ClusterID"]
        axis = "X" if face["AxisX"] > 0.5 else "Y"
        if cid == 13:
            name = "MainAxisYThroughHole"
            confidence = "High"
        elif cid == 19:
            name = "RightAxisXThroughHole"
            confidence = "High"
        elif cid == 21:
            name = "LeftAxisXConcaveCylinder"
            confidence = "Medium"
        elif cid == 15:
            name = "SmallAxisYConcaveCylinder"
            confidence = "Low"
        else:
            name = f"Axis{axis}ConcaveCylinder_{cid}"
            confidence = "Low"
        primitives.append(
            {
                "PrimitiveType": name,
                "RelatedClusters": str(cid),
                "Length": "",
                "Width": "",
                "Height": "",
                "Radius": face["Radius"],
                "Depth": face["AxisMax"] - face["AxisMin"],
                "BooleanType": "Difference",
                "Confidence": confidence,
                "EvidenceNote": "Difference candidate inferred from inward radial normal alignment.",
            }
        )

    fields = [
        "PrimitiveType",
        "RelatedClusters",
        "Length",
        "Width",
        "Height",
        "Radius",
        "Depth",
        "BooleanType",
        "Confidence",
        "EvidenceNote",
    ]
    with PRIMITIVE_PATH.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for primitive in primitives:
            writer.writerow({k: fmt(primitive[k]) for k in fields})
    return primitives


def font(size=22):
    for path in ["C:/Windows/Fonts/msjh.ttc", "C:/Windows/Fonts/arial.ttf"]:
        if Path(path).exists():
            return ImageFont.truetype(path, size=size)
    return ImageFont.load_default()


def draw_node(draw, box, text, fill):
    x, y, w, h = box
    draw.rounded_rectangle([x, y, x + w, y + h], radius=8, fill=fill, outline=(55, 55, 55), width=2)
    lines = text.split("\n")
    f = font(15)
    yy = y + (h - len(lines) * 18) / 2
    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=f)
        draw.text((x + (w - (bbox[2] - bbox[0])) / 2, yy), line, fill=(20, 20, 20), font=f)
        yy += 18


def center(box):
    x, y, w, h = box
    return (x + w / 2, y + h / 2)


def draw_topology(faces, edges):
    img = Image.new("RGB", (1700, 1100), "white")
    d = ImageDraw.Draw(img)
    d.text((50, 32), "Model A Semantic Topology", fill=(0, 0, 0), font=font(34))

    groups = [
        ("Plane faces", [f for f in faces if not f["FeatureType"].startswith("Cylinder")]),
        ("Axis-Y cylinders", [f for f in faces if f["FeatureType"].startswith("Cylinder_axisY")]),
        ("Axis-X cylinders", [f for f in faces if f["FeatureType"].startswith("Cylinder_axisX")]),
    ]
    boxes = {}
    x_positions = [70, 690, 1190]
    for col, (title, members) in enumerate(groups):
        x = x_positions[col]
        d.text((x, 100), title, fill=(40, 40, 40), font=font(22))
        for idx, face in enumerate(members):
            row = idx % 11
            xx = x + (idx // 11) * 245
            yy = 145 + row * 78
            boxes[face["ClusterID"]] = (xx, yy, 220, 58)

    for edge in edges:
        a = edge["FromClusterID"]
        b = edge["ToClusterID"]
        if a not in boxes or b not in boxes:
            continue
        ca = center(boxes[a])
        cb = center(boxes[b])
        color = (175, 175, 175)
        if edge["EdgeType"] == "EndCap":
            color = (215, 80, 80)
        elif edge["EdgeType"] == "OrthogonalAdjacency":
            color = (65, 130, 210)
        elif edge["EdgeType"] == "SideBoundary":
            color = (60, 150, 95)
        d.line([ca, cb], fill=color, width=2)

    for face in faces:
        ft = face["FeatureType"]
        cid = face["ClusterID"]
        if ft.startswith("Cylinder"):
            fill = (255, 234, 234) if face["BooleanRole"] == "DifferenceFace" else (232, 246, 255)
        else:
            fill = (238, 248, 235)
        label = f"ID {cid}\n{ft}\nN={face['PointCount']}"
        draw_node(d, boxes[cid], label, fill)

    edge_counts = {}
    for edge in edges:
        edge_counts[edge["EdgeType"]] = edge_counts.get(edge["EdgeType"], 0) + 1
    y = 1010
    d.text((50, y), "Edges: " + ", ".join(f"{k}={v}" for k, v in sorted(edge_counts.items())), fill=(40, 40, 40), font=font(20))
    d.text((50, y + 34), f"Adjacency threshold: {ADJACENCY_EPS} mm; small output faces are retained in FaceSummary.", fill=(70, 70, 70), font=font(18))
    img.save(TOPOLOGY_PNG)


def draw_csg(primitives):
    img = Image.new("RGB", (1500, 850), "white")
    d = ImageDraw.Draw(img)
    d.text((50, 32), "Model A Hierarchical CSG Reasoning", fill=(0, 0, 0), font=font(34))
    boxes = {
        "solid": (600, 105, 300, 75),
        "diff": (600, 240, 300, 75),
        "shell": (170, 420, 330, 82),
        "h13": (550, 420, 250, 82),
        "h19": (850, 420, 250, 82),
        "h21": (1150, 420, 250, 82),
        "h15": (550, 605, 250, 82),
    }

    def line(a, b):
        d.line([center(boxes[a]), center(boxes[b])], fill=(85, 85, 85), width=3)

    for a, b in [("solid", "diff"), ("diff", "shell"), ("diff", "h13"), ("diff", "h19"), ("diff", "h21"), ("diff", "h15")]:
        line(a, b)

    draw_node(d, boxes["solid"], "Model A\nSolid", (235, 244, 255))
    draw_node(d, boxes["diff"], "Difference", (255, 245, 225))
    draw_node(d, boxes["shell"], "ModelA_AdditiveShell\nUnion", (232, 248, 232))
    draw_node(d, boxes["h13"], "MainAxisYThroughHole\nDifference", (255, 232, 232))
    draw_node(d, boxes["h19"], "RightAxisXThroughHole\nDifference", (255, 232, 232))
    draw_node(d, boxes["h21"], "LeftAxisXConcaveCylinder\nDifference", (255, 240, 240))
    draw_node(d, boxes["h15"], "SmallAxisYConcaveCylinder\nDifference / low confidence", (255, 246, 246))
    d.text(
        (50, 760),
        "CSG: Difference(ModelA_AdditiveShell, MainAxisYThroughHole, RightAxisXThroughHole, LeftAxisXConcaveCylinder, SmallAxisYConcaveCylinder)",
        fill=(50, 50, 50),
        font=font(20),
    )
    img.save(CSG_PNG)


def main():
    df = pd.read_csv(RESULT_PATH)
    faces = build_face_summary(df)
    write_face_summary(faces)
    edges = build_topology(df, faces)
    write_topology(edges)
    primitives = write_primitives(faces)
    draw_topology(faces, edges)
    draw_csg(primitives)

    unclassified = int((df["ClusterID"] < 0).sum())
    small_faces = [f["ClusterID"] for f in faces if f["QualityFlag"] == "SmallOutputFace"]
    print(f"FaceSummary: {FACE_PATH} ({len(faces)} faces)")
    print(f"TopologyEdges: {TOPOLOGY_PATH} ({len(edges)} edges)")
    print(f"PrimitiveCandidates: {PRIMITIVE_PATH} ({len(primitives)} primitives)")
    print(f"Topology PNG: {TOPOLOGY_PNG}")
    print(f"CSG PNG: {CSG_PNG}")
    print(f"Unclassified points: {unclassified}")
    print(f"Small output faces retained: {small_faces}")


if __name__ == "__main__":
    main()
