from pathlib import Path
import csv
import math

import pandas as pd
from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parents[1]
PART_DIR = ROOT / "零件"
RESULT_PATH = PART_DIR / "Result_Stepped Cylinder.csv"
FACE_PATH = PART_DIR / "FaceSummary_Stepped Cylinder.csv"
TOPOLOGY_PATH = PART_DIR / "TopologyEdges_Stepped Cylinder.csv"
PRIMITIVE_PATH = PART_DIR / "PrimitiveCandidates_Stepped Cylinder.csv"
TOPOLOGY_PNG = ROOT / "Stepped Cylinder Topology.png"
CSG_PNG = ROOT / "Stepped Cylinder CSG.png"

MIN_FACE_POINTS = 60


def fmt(value, digits=6):
    if value == "":
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, int):
        return str(value)
    return f"{float(value):.{digits}f}"


def radius_xy(df):
    return ((df["X"] ** 2) + (df["Y"] ** 2)) ** 0.5


def signed_radial_alignment(df):
    r = radius_xy(df).clip(lower=1e-9)
    return ((df["X"] * df["NX"]) + (df["Y"] * df["NY"])) / r


def classify_cluster(cid, group):
    n = len(group)
    avg_abs_nz = group["NZ"].abs().mean()
    r = radius_xy(group)
    z_min, z_max = group["Z"].min(), group["Z"].max()
    z_mean = group["Z"].mean()
    r_median = r.median()

    if n < MIN_FACE_POINTS:
        return None

    if avg_abs_nz > 0.98:
        if z_mean < 1.0:
            label = "Plane_Horizontal (底面環)"
            normal = (0.0, 0.0, -1.0)
        elif z_mean > 90.0:
            label = "Plane_Horizontal (頂面環)"
            normal = (0.0, 0.0, 1.0)
        else:
            label = "Plane_Horizontal (階梯肩面)"
            normal = (0.0, 0.0, 1.0)
        return {
            "ClusterID": cid,
            "FeatureType": label,
            "PointCount": n,
            "CenterX": group["X"].mean(),
            "CenterY": group["Y"].mean(),
            "CenterZ": z_mean,
            "NX": normal[0],
            "NY": normal[1],
            "NZ": normal[2],
            "AxisX": 0.0,
            "AxisY": 0.0,
            "AxisZ": 1.0,
            "MinX": group["X"].min(),
            "MaxX": group["X"].max(),
            "MinY": group["Y"].min(),
            "MaxY": group["Y"].max(),
            "MinZ": z_min,
            "MaxZ": z_max,
            "Radius": 0.0,
            "BoundaryPointCount": boundary_count_for_plane(group),
        }

    if avg_abs_nz < 0.05:
        dot = signed_radial_alignment(group).mean()
        if dot < 0:
            label = "Cylinder_axisZ_inner (貫穿孔)"
        elif r_median > 32.0:
            label = "Cylinder_axisZ_outer (下階外圓柱)"
        else:
            label = "Cylinder_axisZ_outer (上階外圓柱)"
        return {
            "ClusterID": cid,
            "FeatureType": label,
            "PointCount": n,
            "CenterX": group["X"].mean(),
            "CenterY": group["Y"].mean(),
            "CenterZ": group["Z"].mean(),
            "NX": group["NX"].mean(),
            "NY": group["NY"].mean(),
            "NZ": 0.0,
            "AxisX": 0.0,
            "AxisY": 0.0,
            "AxisZ": 1.0,
            "MinX": group["X"].min(),
            "MaxX": group["X"].max(),
            "MinY": group["Y"].min(),
            "MaxY": group["Y"].max(),
            "MinZ": z_min,
            "MaxZ": z_max,
            "Radius": r_median,
            "BoundaryPointCount": n,
        }

    return None


def boundary_count_for_plane(group):
    r = radius_xy(group)
    low = r.quantile(0.08)
    high = r.quantile(0.92)
    return int(((r <= low) | (r >= high)).sum())


def write_face_summary(faces):
    fields = [
        "ClusterID",
        "FeatureType",
        "PointCount",
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
        "Radius",
        "BoundaryPointCount",
    ]
    with FACE_PATH.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for face in faces:
            writer.writerow({k: fmt(face[k]) for k in fields})


def topology_edges(faces):
    by_id = {f["ClusterID"]: f for f in faces}
    edges = []

    def add(a, b, edge_type, distance=0.0):
        edges.append(
            {
                "FromClusterID": a,
                "ToClusterID": b,
                "EdgeType": edge_type,
                "MinDistance": distance,
            }
        )

    # Known analytic adjacency from the stepped-cylinder geometry.
    # 0: inner through-hole, 1: lower outer cylinder, 2: bottom annulus,
    # 3: shoulder annulus, 4: top annulus, 5: upper outer cylinder.
    if {0, 2}.issubset(by_id):
        add(0, 2, "EndCap")
    if {0, 4}.issubset(by_id):
        add(0, 4, "EndCap")
    if {1, 2}.issubset(by_id):
        add(1, 2, "EndCap")
    if {1, 3}.issubset(by_id):
        add(1, 3, "StepShoulder")
    if {5, 3}.issubset(by_id):
        add(5, 3, "StepShoulder")
    if {5, 4}.issubset(by_id):
        add(5, 4, "EndCap")

    return edges


def write_topology(edges):
    fields = ["FromClusterID", "ToClusterID", "EdgeType", "MinDistance"]
    with TOPOLOGY_PATH.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for edge in edges:
            writer.writerow({k: fmt(edge[k]) for k in fields})


def write_primitives(faces):
    face_by_id = {f["ClusterID"]: f for f in faces}
    primitives = []

    if 1 in face_by_id:
        f = face_by_id[1]
        primitives.append(
            {
                "PrimitiveType": "CylinderLower",
                "RelatedClusters": "1;2;3",
                "Length": "",
                "Width": "",
                "Height": f["MaxZ"] - f["MinZ"],
                "Radius": f["Radius"],
                "Depth": f["MaxZ"] - f["MinZ"],
                "BooleanType": "Union",
            }
        )
    if 5 in face_by_id:
        f = face_by_id[5]
        primitives.append(
            {
                "PrimitiveType": "CylinderUpper",
                "RelatedClusters": "5;3;4",
                "Length": "",
                "Width": "",
                "Height": f["MaxZ"] - f["MinZ"],
                "Radius": f["Radius"],
                "Depth": f["MaxZ"] - f["MinZ"],
                "BooleanType": "Union",
            }
        )
    if 0 in face_by_id:
        f = face_by_id[0]
        primitives.append(
            {
                "PrimitiveType": "ThroughHole",
                "RelatedClusters": "0;2;4",
                "Length": "",
                "Width": "",
                "Height": "",
                "Radius": f["Radius"],
                "Depth": f["MaxZ"] - f["MinZ"],
                "BooleanType": "Difference",
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
    ]
    with PRIMITIVE_PATH.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for primitive in primitives:
            writer.writerow({k: fmt(primitive[k]) for k in fields})
    return primitives


def font(size=22, bold=False):
    candidates = [
        "C:/Windows/Fonts/msjh.ttc",
        "C:/Windows/Fonts/arial.ttf",
    ]
    for path in candidates:
        if Path(path).exists():
            return ImageFont.truetype(path, size=size)
    return ImageFont.load_default()


def draw_node(draw, xy, text, fill, outline=(40, 40, 40)):
    x, y, w, h = xy
    draw.rounded_rectangle([x, y, x + w, y + h], radius=10, fill=fill, outline=outline, width=2)
    lines = text.split("\n")
    f = font(20)
    total_h = len(lines) * 24
    yy = y + (h - total_h) / 2
    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=f)
        draw.text((x + (w - (bbox[2] - bbox[0])) / 2, yy), line, fill=(20, 20, 20), font=f)
        yy += 24


def arrow(draw, start, end, fill=(70, 70, 70)):
    draw.line([start, end], fill=fill, width=3)
    sx, sy = start
    ex, ey = end
    ang = math.atan2(ey - sy, ex - sx)
    length = 12
    a1 = ang + math.pi * 0.82
    a2 = ang - math.pi * 0.82
    p1 = (ex + length * math.cos(a1), ey + length * math.sin(a1))
    p2 = (ex + length * math.cos(a2), ey + length * math.sin(a2))
    draw.polygon([end, p1, p2], fill=fill)


def box_center(box):
    x, y, w, h = box
    return (x + w / 2, y + h / 2)


def box_edge_point(box, toward):
    cx, cy = box_center(box)
    tx, ty = toward
    dx, dy = tx - cx, ty - cy
    if abs(dx) < 1e-9 and abs(dy) < 1e-9:
        return (cx, cy)
    x, y, w, h = box
    scale_x = (w / 2) / abs(dx) if abs(dx) > 1e-9 else float("inf")
    scale_y = (h / 2) / abs(dy) if abs(dy) > 1e-9 else float("inf")
    s = min(scale_x, scale_y) * 0.92
    return (cx + dx * s, cy + dy * s)


def arrow_between_boxes(draw, boxes, a, b, fill=(70, 70, 70)):
    ca = box_center(boxes[a])
    cb = box_center(boxes[b])
    start = box_edge_point(boxes[a], cb)
    end = box_edge_point(boxes[b], ca)
    arrow(draw, start, end, fill=fill)


def draw_topology(edges):
    img = Image.new("RGB", (1400, 900), "white")
    d = ImageDraw.Draw(img)
    title = font(34, bold=True)
    d.text((50, 30), "Stepped Cylinder Topology", fill=(0, 0, 0), font=title)
    positions = {
        2: (120, 180, 270, 80),
        3: (565, 180, 270, 80),
        4: (1010, 180, 270, 80),
        1: (180, 430, 270, 80),
        5: (770, 430, 270, 80),
        0: (565, 650, 270, 80),
    }
    labels = {
        2: "Bottom annulus\nPlane",
        3: "Step shoulder\nPlane",
        4: "Top annulus\nPlane",
        1: "Lower outer\nCylinder",
        5: "Upper outer\nCylinder",
        0: "Through hole\nCylinder",
    }
    for edge in edges:
        a, b = edge["FromClusterID"], edge["ToClusterID"]
        if a not in positions or b not in positions:
            continue
        arrow_between_boxes(d, positions, a, b)
    for edge in edges:
        a, b = edge["FromClusterID"], edge["ToClusterID"]
        if a not in positions or b not in positions:
            continue
        ca = box_center(positions[a])
        cb = box_center(positions[b])
        mx = (ca[0] + cb[0]) / 2
        my = (ca[1] + cb[1]) / 2
        d.rounded_rectangle([mx + 4, my - 16, mx + 130, my + 10], radius=4, fill="white")
        d.text((mx + 8, my - 15), edge["EdgeType"], fill=(40, 40, 40), font=font(16))
    for cid, box in positions.items():
        color = (229, 241, 255) if "Plane" in labels[cid] else (255, 232, 232)
        draw_node(d, box, f"ID {cid}\n{labels[cid]}", color)
    img.save(TOPOLOGY_PNG)


def draw_csg(primitives):
    img = Image.new("RGB", (1400, 800), "white")
    d = ImageDraw.Draw(img)
    d.text((50, 30), "Stepped Cylinder CSG Reasoning", fill=(0, 0, 0), font=font(34, bold=True))
    boxes = {
        "solid": (560, 110, 280, 80),
        "diff": (560, 250, 280, 80),
        "union": (360, 400, 280, 80),
        "hole": (780, 400, 280, 80),
        "lower": (170, 560, 280, 80),
        "upper": (550, 560, 280, 80),
    }
    for a, b in [
        ("solid", "diff"),
        ("diff", "union"),
        ("diff", "hole"),
        ("union", "lower"),
        ("union", "upper"),
    ]:
        arrow_between_boxes(d, boxes, a, b)
    draw_node(d, boxes["solid"], "Stepped Cylinder\nSolid", (235, 244, 255))
    draw_node(d, boxes["diff"], "Difference", (255, 245, 225))
    draw_node(d, boxes["union"], "Union", (235, 255, 235))
    draw_node(d, boxes["hole"], "ThroughHole\nDifference", (255, 232, 232))
    draw_node(d, boxes["lower"], "CylinderLower\nUnion", (235, 255, 235))
    draw_node(d, boxes["upper"], "CylinderUpper\nUnion", (235, 255, 235))
    d.text((50, 720), "CSG: Difference(Union(CylinderLower, CylinderUpper), ThroughHole)", fill=(50, 50, 50), font=font(22))
    img.save(CSG_PNG)


def main():
    df = pd.read_csv(RESULT_PATH)
    faces = []
    residual = []
    for cid, group in df.groupby("ClusterID"):
        face = classify_cluster(int(cid), group)
        if face is None:
            residual.append((int(cid), len(group)))
        else:
            faces.append(face)
    faces.sort(key=lambda x: x["ClusterID"])

    write_face_summary(faces)
    edges = topology_edges(faces)
    write_topology(edges)
    primitives = write_primitives(faces)
    draw_topology(edges)
    draw_csg(primitives)

    print(f"FaceSummary: {FACE_PATH} ({len(faces)} faces)")
    print(f"TopologyEdges: {TOPOLOGY_PATH} ({len(edges)} edges)")
    print(f"PrimitiveCandidates: {PRIMITIVE_PATH} ({len(primitives)} primitives)")
    print(f"Topology PNG: {TOPOLOGY_PNG}")
    print(f"CSG PNG: {CSG_PNG}")
    print(f"Residual clusters below semantic-face threshold: {residual}")


if __name__ == "__main__":
    main()
