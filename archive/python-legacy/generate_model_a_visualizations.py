from pathlib import Path
import math

import numpy as np
import pandas as pd
from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parents[1]
PART_DIR = ROOT / "零件"
RESULT_PATH = PART_DIR / "Result_Model A.csv"
FACE_PATH = PART_DIR / "FaceSummary_Model A.csv"
PRIMITIVE_PATH = PART_DIR / "PrimitiveCandidates_Model A.csv"

SEMANTIC_PNG = ROOT / "Model A Semantic Face Visualization.png"
BOOLEAN_PNG = ROOT / "Model A Boolean Role Visualization.png"
OVERVIEW_PNG = ROOT / "Model A Complete Chain Visualization.png"

CANVAS_W = 1800
CANVAS_H = 1180
PLOT_W = 1180
PLOT_H = 900
PLOT_X = 60
PLOT_Y = 160


PALETTE = [
    (31, 119, 180),
    (255, 127, 14),
    (44, 160, 44),
    (214, 39, 40),
    (148, 103, 189),
    (140, 86, 75),
    (227, 119, 194),
    (127, 127, 127),
    (188, 189, 34),
    (23, 190, 207),
    (174, 199, 232),
    (255, 187, 120),
    (152, 223, 138),
    (255, 152, 150),
    (197, 176, 213),
    (196, 156, 148),
    (247, 182, 210),
    (199, 199, 199),
    (219, 219, 141),
    (158, 218, 229),
    (57, 59, 121),
    (82, 84, 163),
]


ROLE_COLORS = {
    "UnionFace": (44, 123, 182),
    "DifferenceFace": (215, 48, 39),
    "SmallOutputFace": (253, 174, 97),
    "unclassified": (135, 135, 135),
}


def font(size=22):
    for path in ["C:/Windows/Fonts/msjh.ttc", "C:/Windows/Fonts/arial.ttf"]:
        if Path(path).exists():
            return ImageFont.truetype(path, size=size)
    return ImageFont.load_default()


def projected_coordinates(df):
    x = df["X"].to_numpy(dtype=float)
    y = df["Y"].to_numpy(dtype=float)
    z = df["Z"].to_numpy(dtype=float)

    angle = math.radians(35)
    u = (x - y) * math.cos(angle)
    v = (x + y) * math.sin(angle) - z * 1.15

    u = (u - u.min()) / max(u.max() - u.min(), 1e-9)
    v = (v - v.min()) / max(v.max() - v.min(), 1e-9)
    px = PLOT_X + u * PLOT_W
    py = PLOT_Y + v * PLOT_H
    return px, py


def draw_header(draw, title, subtitle):
    draw.text((55, 32), title, fill=(20, 20, 20), font=font(36))
    draw.text((58, 78), subtitle, fill=(80, 80, 80), font=font(20))


def draw_plot_frame(draw):
    draw.rectangle([PLOT_X - 20, PLOT_Y - 20, PLOT_X + PLOT_W + 20, PLOT_Y + PLOT_H + 20], outline=(215, 215, 215), width=2)
    draw.text((PLOT_X, PLOT_Y + PLOT_H + 30), "isometric projection of X/Y/Z point cloud", fill=(95, 95, 95), font=font(18))


def draw_points(draw, df, color_by_cluster=None, color_by_role=None):
    px, py = projected_coordinates(df)
    order = np.argsort(py)
    cluster_values = df["ClusterID"].to_numpy()

    for idx in order:
        cid = int(cluster_values[idx])
        if cid < 0:
            color = ROLE_COLORS["unclassified"]
            r = 2
        elif color_by_cluster is not None:
            color = color_by_cluster.get(cid, (80, 80, 80))
            r = 2
        else:
            role = color_by_role.get(cid, "UnionFace")
            color = ROLE_COLORS.get(role, (80, 80, 80))
            r = 3 if role == "DifferenceFace" else 2
        x = int(px[idx])
        y = int(py[idx])
        draw.ellipse([x - r, y - r, x + r, y + r], fill=color)


def draw_semantic_legend(draw, faces, color_by_cluster):
    x0 = 1290
    y = 125
    draw.text((x0, y), "語義特徵面", fill=(30, 30, 30), font=font(24))
    y += 42
    for _, row in faces.iterrows():
        cid = int(row["ClusterID"])
        color = color_by_cluster[cid]
        label = f"ID {cid:>2}  {row['FeatureType']}  N={row['PointCount']}"
        if row["QualityFlag"] == "SmallOutputFace":
            label += "  small"
        draw.rectangle([x0, y + 4, x0 + 22, y + 26], fill=color, outline=(80, 80, 80))
        draw.text((x0 + 34, y), label, fill=(45, 45, 45), font=font(16))
        y += 33
    draw.rectangle([x0, y + 4, x0 + 22, y + 26], fill=ROLE_COLORS["unclassified"], outline=(80, 80, 80))
    draw.text((x0 + 34, y), "unclassified  N=87", fill=(45, 45, 45), font=font(16))


def draw_role_legend(draw, faces, primitives):
    x0 = 1290
    y = 125
    draw.text((x0, y), "布林角色", fill=(30, 30, 30), font=font(24))
    y += 46
    legend = [
        ("UnionFace", "Union faces / additive shell"),
        ("DifferenceFace", "Difference candidate faces"),
        ("SmallOutputFace", "Small output faces"),
        ("unclassified", "Unclassified points"),
    ]
    for key, label in legend:
        draw.rectangle([x0, y + 4, x0 + 26, y + 30], fill=ROLE_COLORS[key], outline=(80, 80, 80))
        draw.text((x0 + 40, y), label, fill=(45, 45, 45), font=font(18))
        y += 42

    y += 28
    draw.text((x0, y), "候選幾何單元", fill=(30, 30, 30), font=font(24))
    y += 42
    for _, row in primitives.iterrows():
        text = f"{row['PrimitiveType']} / {row['BooleanType']} / {row['Confidence']}"
        draw.text((x0, y), text, fill=(45, 45, 45), font=font(16))
        y += 32


def semantic_visualization(df, faces):
    img = Image.new("RGB", (CANVAS_W, CANVAS_H), "white")
    draw = ImageDraw.Draw(img)
    draw_header(
        draw,
        "Model A 語義特徵面視覺化",
        "22 semantic faces from FaceSummary_Model A.csv; 87 unclassified points shown in gray.",
    )
    draw_plot_frame(draw)
    color_by_cluster = {int(row["ClusterID"]): PALETTE[i % len(PALETTE)] for i, row in faces.iterrows()}
    draw_points(draw, df, color_by_cluster=color_by_cluster)
    draw_semantic_legend(draw, faces, color_by_cluster)
    img.save(SEMANTIC_PNG)


def boolean_visualization(df, faces, primitives):
    img = Image.new("RGB", (CANVAS_W, CANVAS_H), "white")
    draw = ImageDraw.Draw(img)
    draw_header(
        draw,
        "Model A 候選幾何單元布林角色視覺化",
        "Union/Difference roles inferred from FaceSummary_Model A.csv and PrimitiveCandidates_Model A.csv.",
    )
    draw_plot_frame(draw)
    role_by_cluster = {}
    for _, row in faces.iterrows():
        cid = int(row["ClusterID"])
        role_by_cluster[cid] = row["QualityFlag"] if row["QualityFlag"] == "SmallOutputFace" else row["BooleanRole"]
    draw_points(draw, df, color_by_role=role_by_cluster)
    draw_role_legend(draw, faces, primitives)
    img.save(BOOLEAN_PNG)


def overview_visualization():
    semantic = Image.open(SEMANTIC_PNG).resize((900, 590))
    boolean = Image.open(BOOLEAN_PNG).resize((900, 590))
    img = Image.new("RGB", (1800, 805), "white")
    draw = ImageDraw.Draw(img)
    draw.text((55, 32), "Model A 完整鏈視覺化總覽", fill=(20, 20, 20), font=font(38))
    draw.text((58, 82), "Semantic faces and Boolean-role point-cloud visualizations for Chapter 4.", fill=(80, 80, 80), font=font(20))
    img.paste(semantic, (0, 125))
    img.paste(boolean, (900, 125))
    draw.text((60, 750), "Left: FaceSummary semantic faces. Right: Primitive candidate Boolean roles.", fill=(80, 80, 80), font=font(20))
    img.save(OVERVIEW_PNG)


def main():
    df = pd.read_csv(RESULT_PATH)
    faces = pd.read_csv(FACE_PATH)
    primitives = pd.read_csv(PRIMITIVE_PATH)

    semantic_visualization(df, faces)
    boolean_visualization(df, faces, primitives)
    overview_visualization()

    print(f"Semantic visualization: {SEMANTIC_PNG}")
    print(f"Boolean role visualization: {BOOLEAN_PNG}")
    print(f"Overview visualization: {OVERVIEW_PNG}")


if __name__ == "__main__":
    main()
