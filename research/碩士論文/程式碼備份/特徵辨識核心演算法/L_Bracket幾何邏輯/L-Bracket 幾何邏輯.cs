using System;
using System.Collections.Generic;
using System.IO;
using System.Globalization;
using System.Linq;

namespace L_Bracket幾何邏輯
{
    public class PointData
    {
        public double X, Y, Z, NX, NY, NZ;
        public int ClusterID = -1;
    }

    public class FaceFeature
    {
        public int ClusterID;
        public string FeatureType;
        public double CenterX, CenterY, CenterZ;
        public double NX, NY, NZ;
        public double AxisX, AxisY, AxisZ;
        public double MinX, MaxX, MinY, MaxY, MinZ, MaxZ;
        public double Radius;
        public List<PointData> Points = new List<PointData>();
        public List<PointData> BoundaryPoints = new List<PointData>();
    }

    public class TopologyEdge
    {
        public int FromClusterID;
        public int ToClusterID;
        public string EdgeType;
        public double MinDistance;
    }

    public class PrimitiveCandidate
    {
        public string PrimitiveType;
        public List<int> RelatedClusters = new List<int>();
        public double Length, Width, Height;
        public double Radius, Depth;
        public string BooleanType;
    }

    class Program
    {
        static void Main(string[] args)
        {
            string inputPath = @"C:\Users\Admin\Desktop\云析論文\零件\L-Bracket點雲.csv";
            string outputPath = @"C:\Users\Admin\Desktop\云析論文\零件\Result_L Bracket.csv";

            FeatureClassifier classifier = new FeatureClassifier();
            classifier.Execute(inputPath, outputPath);

            Console.WriteLine("\n按下任意鍵結束...");
            Console.ReadKey();
        }
    }

    public class FeatureClassifier
    {

        public double DistanceThreshold = 2.0;
        public double NormalThreshold = 0.93;

        // ─────────────────────────────────────────────────────────────────
        // IsSimilar：核心修正 Bug 1 + 2
        // ─────────────────────────────────────────────────────────────────
        private bool IsSimilar(PointData a, PointData b)
        {
            double dist = Math.Sqrt(
                Math.Pow(a.X - b.X, 2) +
                Math.Pow(a.Y - b.Y, 2) +
                Math.Pow(a.Z - b.Z, 2));
            if (dist > DistanceThreshold) return false;

            double dot = Math.Abs(a.NX * b.NX + a.NY * b.NY + a.NZ * b.NZ);
            if (dot < NormalThreshold) return false;

            // 1. 強制切開轉角 (不同軸向絕對不合併)
            // 2. 跨層保護：僅針對 X 軸向 (左右側) 進行切斷
            // Y 軸向的牆面不切斷，以保留完整的一整片「立板後」
            const double splitZ = 5.1;
            if (Math.Abs(a.NX) > 0.8 && Math.Abs(b.NX) > 0.8)
            {
                if ((a.Z <= splitZ && b.Z > splitZ) || (b.Z <= splitZ && a.Z > splitZ))
                    return false;
            }

            return true;
        }

        // ─────────────────────────────────────────────────────────────────
        // 語義標籤
        // ─────────────────────────────────────────────────────────────────
        private string GetSemanticLabel(FaceFeature face)
        {
            string baseType = GetBaseFeatureType(face.FeatureType);

            if (baseType == "Plane_Horizontal") {
                if (face.CenterZ < 1.0) return "底板下";
                if (face.CenterZ < 6.0) return "底板上";
                if (face.CenterZ > 40.0) return "立板上";
                if (face.CenterZ > 30.0) return "圓柱頂";
                return "水平面";
            }

            if (baseType == "Plane_Vertical") {
                if (Math.Abs(face.NY) > 0.8) {
                    if (face.CenterY < 2.5) return "立板後"; // Y=0，整片背牆
                    if (face.CenterY > 70.0) return "底板前"; // Y=80
                    return "立板前"; // Y=5
                }
                if (Math.Abs(face.NX) > 0.8) {
                    // 因 IsSimilar 的 splitZ 已精準分離，可放心標記
                    if (face.CenterZ > 5.1) return (face.CenterX < 0) ? "立板左" : "立板右";
                    return (face.CenterX < 0) ? "底板左" : "底板右";
                }
                return "垂直面";
            }

            if (baseType == "Cylinder") {
                var p = face.Points[0];
                double dot = (p.X - face.CenterX) * p.NX + (p.Y - face.CenterY) * p.NY + (p.Z - face.CenterZ) * p.NZ;
                if (dot > 0) return "圓柱面";
                return (face.AxisZ > 0.8) ? "底板洞" : "立板洞";
            }
            return "其他特徵";
        }

        // ─────────────────────────────────────────────────────────────────
        // BuildFaceFeature
        // ─────────────────────────────────────────────────────────────────
        private FaceFeature BuildFaceFeature(int id, List<PointData> clusterPoints)
        {
            FaceFeature face = new FaceFeature { ClusterID = id, Points = new List<PointData>(clusterPoints) };

            // 採用 Average 以貼合表面
            face.CenterX = clusterPoints.Average(p => p.X);
            face.CenterY = clusterPoints.Average(p => p.Y);
            face.CenterZ = clusterPoints.Average(p => p.Z);

            face.MinX = clusterPoints.Min(p => p.X); face.MaxX = clusterPoints.Max(p => p.X);
            face.MinY = clusterPoints.Min(p => p.Y); face.MaxY = clusterPoints.Max(p => p.Y);
            face.MinZ = clusterPoints.Min(p => p.Z); face.MaxZ = clusterPoints.Max(p => p.Z);

            // 保留邊界點供拓樸使用
            double spanX = face.MaxX - face.MinX;
            double spanY = face.MaxY - face.MinY;
            double spanZ = face.MaxZ - face.MinZ;
            double searchRadius = Math.Max(1.5, Math.Max(spanX, Math.Max(spanY, spanZ)) * 0.06);
            int minNeighbors = Math.Max(6, clusterPoints.Count / 30);
            face.BoundaryPoints = ExtractBoundaryPoints(clusterPoints, searchRadius, minNeighbors);

            double nx = clusterPoints.Average(p => p.NX), ny = clusterPoints.Average(p => p.NY), nz = clusterPoints.Average(p => p.NZ);
            NormalizeInPlace(ref nx, ref ny, ref nz);
            face.NX = nx; face.NY = ny; face.NZ = nz;

            double avgNZ = clusterPoints.Average(p => Math.Abs(p.NZ));
            face.AxisX = 0.0; face.AxisY = 0.0; face.AxisZ = 0.0;

            if (avgNZ > 0.98) {
                face.FeatureType = "Plane_Horizontal";
                face.AxisZ = 1.0;
            } else {
                var refN = clusterPoints[0];
                double varN = clusterPoints.Average(p => 1.0 - Math.Abs(p.NX * refN.NX + p.NY * refN.NY + p.NZ * refN.NZ));

                if (clusterPoints.Count > 60 && varN > 0.07) {
                    face.FeatureType = "Cylinder";

                    double ax = clusterPoints.Average(p => Math.Abs(p.NX));
                    double ay = clusterPoints.Average(p => Math.Abs(p.NY));
                    double az = clusterPoints.Average(p => Math.Abs(p.NZ));
                    double minA = Math.Min(ax, Math.Min(ay, az));
                    if (minA == az) face.AxisZ = 1.0;
                    else if (minA == ay) face.AxisY = 1.0;
                    else face.AxisX = 1.0;

                    face.Radius = clusterPoints.Average(p => Math.Sqrt(
                        Math.Pow(p.X - face.CenterX, 2) +
                        Math.Pow(p.Y - face.CenterY, 2) +
                        Math.Pow(p.Z - face.CenterZ, 2)));
                } else {
                    face.FeatureType = "Plane_Vertical";
                    face.AxisX = face.NX;
                    face.AxisY = face.NY;
                    face.AxisZ = face.NZ;
                }
            }

            face.FeatureType = $"{face.FeatureType} ({GetSemanticLabel(face)})";
            return face;
        }

        // ─────────────────────────────────────────────────────────────────
        // MergeCoplanarFaces：合併同平面的碎片
        // ─────────────────────────────────────────────────────────────────
        private List<FaceFeature> MergeCoplanarFaces(List<FaceFeature> faces)
        {
            bool merged = true;
            while (merged)
            {
                merged = false;
                for (int i = 0; i < faces.Count; i++)
                {
                    for (int j = i + 1; j < faces.Count; j++)
                    {
                        var a = faces[i];
                        var b = faces[j];

                        bool aPlane = IsFeatureType(a, "Plane_Horizontal") || IsFeatureType(a, "Plane_Vertical");
                        bool bPlane = IsFeatureType(b, "Plane_Horizontal") || IsFeatureType(b, "Plane_Vertical");
                        if (!aPlane || !bPlane) continue;

                        // 💀 終極防護牆：如果兩個面的「完整語義標籤(包含中文)」不同，絕對不合併！
                        // 這樣「底板左」和「立板左」就永遠不會再黏在一起了。
                        if (a.FeatureType != b.FeatureType) continue;

                        // 法向量必須幾乎完全一致
                        double[] na = NormalizeVector(a.NX, a.NY, a.NZ);
                        double[] nb = NormalizeVector(b.NX, b.NY, b.NZ);
                        double dotN = Math.Abs(na[0] * nb[0] + na[1] * nb[1] + na[2] * nb[2]);
                        if (dotN < 0.995) continue;

                        // 邊界必須夠近
                        var ba = a.BoundaryPoints.Count > 0 ? a.BoundaryPoints : a.Points;
                        var bb = b.BoundaryPoints.Count > 0 ? b.BoundaryPoints : b.Points;
                        if (ComputeBoundaryDistance(ba, bb) > 2.0) continue;

                        var mp = new List<PointData>(a.Points);
                        mp.AddRange(b.Points);
                        faces[i] = RebuildMergedPlaneFace(
                            a.ClusterID, mp, GetBaseFeatureType(a.FeatureType));
                        faces.RemoveAt(j);
                        merged = true;
                        break;
                    }
                    if (merged) break;
                }
            }
            return faces;
        }

        private FaceFeature RebuildMergedPlaneFace(
            int id, List<PointData> pts, string planeBase)
        {
            var face = new FaceFeature
            {
                ClusterID = id,
                FeatureType = planeBase,
                Points = new List<PointData>(pts)
            };
            face.CenterX = pts.Average(p => p.X);
            face.CenterY = pts.Average(p => p.Y);
            face.CenterZ = pts.Average(p => p.Z);
            face.MinX = pts.Min(p => p.X); face.MaxX = pts.Max(p => p.X);
            face.MinY = pts.Min(p => p.Y); face.MaxY = pts.Max(p => p.Y);
            face.MinZ = pts.Min(p => p.Z); face.MaxZ = pts.Max(p => p.Z);

            double nx = pts.Average(p => p.NX);
            double ny = pts.Average(p => p.NY);
            double nz = pts.Average(p => p.NZ);
            NormalizeInPlace(ref nx, ref ny, ref nz);
            face.NX = nx; face.NY = ny; face.NZ = nz;

            if (planeBase == "Plane_Horizontal")
            { face.AxisZ = 1.0; }
            else
            { face.AxisX = face.NX; face.AxisY = face.NY; face.AxisZ = face.NZ; }

            double sr = Math.Max(1.5,
                Math.Max(face.MaxX - face.MinX,
                Math.Max(face.MaxY - face.MinY,
                         face.MaxZ - face.MinZ)) * 0.06);
            int minNb = Math.Max(6, pts.Count / 30);
            face.BoundaryPoints = ExtractBoundaryPoints(pts, sr, minNb);

            // 重新套語義標籤
            face.FeatureType = $"{planeBase} ({GetSemanticLabel(face)})";
            return face;
        }

        // ─────────────────────────────────────────────────────────────────
        // BuildTopologyEdges：修正 EndCap 距離容忍度
        // ─────────────────────────────────────────────────────────────────
        public List<TopologyEdge> BuildTopologyEdges(
            List<FaceFeature> faces, double epsilon)
        {
            var edges = new List<TopologyEdge>();
            if (faces == null || faces.Count < 2) return edges;

            double thr = Math.Max(epsilon, 1e-6);

            for (int i = 0; i < faces.Count; i++)
                for (int j = i + 1; j < faces.Count; j++)
                {
                    var fA = faces[i]; var fB = faces[j];
                    if (!IsValidFaceType(fA) || !IsValidFaceType(fB)) continue;

                    var bA = fA.BoundaryPoints.Count > 0 ? fA.BoundaryPoints : fA.Points;
                    var bB = fB.BoundaryPoints.Count > 0 ? fB.BoundaryPoints : fB.Points;
                    double minDist = ComputeBoundaryDistance(bA, bB);

                    bool isAdj = minDist <= thr;
                    bool isOrtho = isAdj && AreOrthogonal(fA, fB);
                    bool isEndCap = IsEndCapRelation(fA, fB, minDist, thr);

                    if (!isAdj && !isEndCap) continue;

                    edges.Add(new TopologyEdge
                    {
                        FromClusterID = fA.ClusterID,
                        ToClusterID = fB.ClusterID,
                        EdgeType = isEndCap ? "EndCap"
                                      : (isOrtho ? "OrthogonalAdjacency" : "Adjacency"),
                        MinDistance = minDist
                    });
                }
            return edges;
        }

        private bool IsValidFaceType(FaceFeature f) =>
            IsFeatureType(f, "Plane_Horizontal") ||
            IsFeatureType(f, "Plane_Vertical") ||
            IsFeatureType(f, "Cylinder");

        private static bool AreOrthogonal(FaceFeature a, FaceFeature b)
        {
            var na = NormalizeVector(a.NX, a.NY, a.NZ);
            var nb = NormalizeVector(b.NX, b.NY, b.NZ);
            return Math.Abs(na[0] * nb[0] + na[1] * nb[1] + na[2] * nb[2]) < 0.2;
        }

        private static bool IsEndCapRelation(
            FaceFeature a, FaceFeature b, double dist, double thr)
        {
            if (dist > 5.0) return false;   // 端面距離容忍放寬到 5mm

            bool aCyl = IsFeatureType(a, "Cylinder");
            bool bCyl = IsFeatureType(b, "Cylinder");

            if (aCyl && !bCyl)
                return IsParallel(b.NX, b.NY, b.NZ, a.AxisX, a.AxisY, a.AxisZ);
            if (bCyl && !aCyl)
                return IsParallel(a.NX, a.NY, a.NZ, b.AxisX, b.AxisY, b.AxisZ);
            return false;
        }

        private static bool IsParallel(
            double ax, double ay, double az,
            double bx, double by, double bz)
            => Math.Abs(ax * bx + ay * by + az * bz) > 0.95;

        // ─────────────────────────────────────────────────────────────────
        // InferPrimitiveCandidates
        // ─────────────────────────────────────────────────────────────────
        private List<PrimitiveCandidate> InferPrimitiveCandidates(List<FaceFeature> faces, List<TopologyEdge> edges)
        {
            List<PrimitiveCandidate> candidates = new List<PrimitiveCandidate>();

            // 1. 底板 (Base Plate)
            var baseFaces = faces.Where(f => f.FeatureType.Contains("底板") && !f.FeatureType.Contains("洞")).ToList();
            if (baseFaces.Count > 0) {
                candidates.Add(new PrimitiveCandidate {
                    PrimitiveType = "BasePlate",
                    RelatedClusters = baseFaces.Select(f => f.ClusterID).Distinct().OrderBy(i => i).ToList(),
                    Length = baseFaces.Max(f => f.MaxX) - baseFaces.Min(f => f.MinX),
                    Width = baseFaces.Max(f => f.MaxY) - baseFaces.Min(f => f.MinY),
                    Height = baseFaces.Max(f => f.MaxZ) - baseFaces.Min(f => f.MinZ),
                    BooleanType = "Union"
                });
            }

            // 2. 立板 (Upright Plate)
            var uprightFaces = faces.Where(f => f.FeatureType.Contains("立板") && !f.FeatureType.Contains("洞")).ToList();
            if (uprightFaces.Count > 0) {
                candidates.Add(new PrimitiveCandidate {
                    PrimitiveType = "UprightPlate",
                    RelatedClusters = uprightFaces.Select(f => f.ClusterID).Distinct().OrderBy(i => i).ToList(),
                    Length = uprightFaces.Max(f => f.MaxX) - uprightFaces.Min(f => f.MinX),
                    Width = uprightFaces.Max(f => f.MaxY) - uprightFaces.Min(f => f.MinY),
                    Height = uprightFaces.Max(f => f.MaxZ) - uprightFaces.Min(f => f.MinZ),
                    BooleanType = "Union"
                });
            }

            // 3. 圓柱與孔洞
            foreach (var cyl in faces.Where(f => IsFeatureType(f, "Cylinder"))) {
                string type = cyl.FeatureType.Contains("圓柱面") ? "Cylinder" : "Hole";
                candidates.Add(new PrimitiveCandidate {
                    PrimitiveType = type,
                    RelatedClusters = new List<int> { cyl.ClusterID },
                    Radius = cyl.Radius,
                    Depth = (cyl.MaxX - cyl.MinX) + (cyl.MaxY - cyl.MinY) + (cyl.MaxZ - cyl.MinZ),
                    BooleanType = type == "Cylinder" ? "Union" : "Difference"
                });
            }

            return candidates;
        }

        // ─────────────────────────────────────────────────────────────────
        // Execute：修正點數門檻 (Bug 2)
        // ─────────────────────────────────────────────────────────────────
        public void Execute(string inputPath, string outputPath)
        {
            if (!File.Exists(inputPath))
            {
                Console.WriteLine($"找不到輸入檔案：{inputPath}");
                return;
            }

            var points = new List<PointData>();
            var lines = File.ReadAllLines(inputPath);
            for (int i = 1; i < lines.Length; i++)
            {
                var cols = lines[i].Split(',');
                if (cols.Length < 6) continue;
                points.Add(new PointData
                {
                    X = double.Parse(cols[0], CultureInfo.InvariantCulture),
                    Y = double.Parse(cols[1], CultureInfo.InvariantCulture),
                    Z = double.Parse(cols[2], CultureInfo.InvariantCulture),
                    NX = double.Parse(cols[3], CultureInfo.InvariantCulture),
                    NY = double.Parse(cols[4], CultureInfo.InvariantCulture),
                    NZ = double.Parse(cols[5], CultureInfo.InvariantCulture)
                });
            }

            // ── 生長分群 ─────────────────────────────────────────────────
            int currentID = 0;
            for (int i = 0; i < points.Count; i++)
            {
                if (points[i].ClusterID != -1) continue;

                var stack = new Stack<PointData>();
                stack.Push(points[i]);
                points[i].ClusterID = currentID;

                int count = 0;
                while (stack.Count > 0)
                {
                    var p = stack.Pop();
                    count++;
                    foreach (var t in points)
                    {
                        if (t.ClusterID != -1) continue;
                        if (IsSimilar(p, t))
                        {
                            t.ClusterID = currentID;
                            stack.Push(t);
                        }
                    }
                }

                // 門檻維持 60，確保能抓到細長的左右側牆
                if (count > 60)
                {
                    Console.WriteLine($"偵測到特徵 ID:{currentID}，點數：{count}");
                    currentID++;
                }
            }

            Console.WriteLine("\n--- 幾何特徵提取報告 (L-Bracket 14特徵版) ---");

            // ── 建立 FaceFeature（過濾 < 60 點的雜訊，保留 >= 60 的）──
            var faces = new List<FaceFeature>();
            for (int id = 0; id < currentID; id++)
            {
                var cp = points.Where(p => p.ClusterID == id).ToList();
                if (cp.Count < 60) continue;

                var face = BuildFaceFeature(id, cp);
                faces.Add(face);
                Console.WriteLine($"ID {id}: {face.FeatureType}");
            }

            // ── 合併同平面碎片 ────────────────────────────────────────────
            faces = MergeCoplanarFaces(faces);
            Console.WriteLine($"\n合併後：{faces.Count} 個特徵面");
            foreach (var f in faces.OrderBy(f => f.ClusterID))
                Console.WriteLine($"  ID {f.ClusterID:2d}: {f.FeatureType}  (n={f.Points.Count})");

            // ── 輸出 CSV ─────────────────────────────────────────────────
            string dir = Path.GetDirectoryName(outputPath) ?? string.Empty;
            WriteFaceSummaryCsv(Path.Combine(dir, "FaceSummary_LBracket.csv"), faces);

            var edges = BuildTopologyEdges(faces, epsilon: 2.0);
            WriteTopologyEdgesCsv(Path.Combine(dir, "TopologyEdges_LBracket.csv"), edges);

            var primitives = InferPrimitiveCandidates(faces, edges);
            WritePrimitiveCandidatesCsv(Path.Combine(dir, "PrimitiveCandidates_LBracket.csv"), primitives);

            using (var sw = new StreamWriter(outputPath))
            {
                sw.WriteLine("X,Y,Z,NX,NY,NZ,ClusterID");
                foreach (var p in points)
                    sw.WriteLine(
                        $"{p.X},{p.Y},{p.Z},{p.NX},{p.NY},{p.NZ},{p.ClusterID}");
            }

            Console.WriteLine($"\n完成！成功識別出 {faces.Count} 個語義特徵面。");
        }

        // ─────────────────────────────────────────────────────────────────
        // 工具方法
        // ─────────────────────────────────────────────────────────────────
        public List<PointData> ExtractBoundaryPoints(
            List<PointData> pts, double radius, int minNeighbors)
        {
            if (pts == null || pts.Count == 0) return new List<PointData>();
            double r2 = radius * radius;
            var result = new List<PointData>();
            foreach (var pt in pts)
            {
                int nb = 0;
                foreach (var other in pts)
                {
                    double dx = pt.X - other.X, dy = pt.Y - other.Y, dz = pt.Z - other.Z;
                    if (dx * dx + dy * dy + dz * dz <= r2) nb++;
                }
                if (nb < minNeighbors) result.Add(pt);
            }
            return result;
        }

        public double ComputeBoundaryDistance(
            List<PointData> bA, List<PointData> bB)
        {
            if (bA == null || bB == null ||
                bA.Count == 0 || bB.Count == 0) return double.PositiveInfinity;

            double minD = double.PositiveInfinity;
            foreach (var a in bA)
                foreach (var b in bB)
                {
                    double dx = a.X - b.X, dy = a.Y - b.Y, dz = a.Z - b.Z;
                    double d = Math.Sqrt(dx * dx + dy * dy + dz * dz);
                    if (d < minD) { minD = d; if (minD <= 0) return 0; }
                }
            return minD;
        }

        private static string GetBaseFeatureType(string ft)
        {
            if (string.IsNullOrWhiteSpace(ft)) return string.Empty;
            int idx = ft.IndexOf(" (", StringComparison.Ordinal);
            return idx >= 0 ? ft.Substring(0, idx) : ft;
        }

        private static bool IsFeatureType(FaceFeature f, string baseType) =>
            string.Equals(GetBaseFeatureType(f.FeatureType),
                          baseType, StringComparison.OrdinalIgnoreCase);

        private static double[] NormalizeVector(double x, double y, double z)
        {
            double len = Math.Sqrt(x * x + y * y + z * z);
            return len < 1e-6
                ? new[] { 0.0, 0.0, 1.0 }
                : new[] { x / len, y / len, z / len };
        }

        private static void NormalizeInPlace(ref double x, ref double y, ref double z)
        {
            double len = Math.Sqrt(x * x + y * y + z * z);
            if (len < 1e-9) { x = 0; y = 0; z = 1; return; }
            x /= len; y /= len; z /= len;
        }

        private void WriteFaceSummaryCsv(string path, List<FaceFeature> faces)
        {
            using (var sw = new StreamWriter(path))
            {
                sw.WriteLine("ClusterID,FeatureType,PointCount," +
                             "CenterX,CenterY,CenterZ,NX,NY,NZ," +
                             "AxisX,AxisY,AxisZ," +
                             "MinX,MaxX,MinY,MaxY,MinZ,MaxZ,Radius,BoundaryPointCount");
                foreach (var f in faces)
                    sw.WriteLine(string.Join(",", new[]
                    {
                        f.ClusterID.ToString(CultureInfo.InvariantCulture),
                        f.FeatureType,
                        f.Points.Count.ToString(CultureInfo.InvariantCulture),
                        f.CenterX.ToString(CultureInfo.InvariantCulture),
                        f.CenterY.ToString(CultureInfo.InvariantCulture),
                        f.CenterZ.ToString(CultureInfo.InvariantCulture),
                        f.NX.ToString(CultureInfo.InvariantCulture),
                        f.NY.ToString(CultureInfo.InvariantCulture),
                        f.NZ.ToString(CultureInfo.InvariantCulture),
                        f.AxisX.ToString(CultureInfo.InvariantCulture),
                        f.AxisY.ToString(CultureInfo.InvariantCulture),
                        f.AxisZ.ToString(CultureInfo.InvariantCulture),
                        f.MinX.ToString(CultureInfo.InvariantCulture),
                        f.MaxX.ToString(CultureInfo.InvariantCulture),
                        f.MinY.ToString(CultureInfo.InvariantCulture),
                        f.MaxY.ToString(CultureInfo.InvariantCulture),
                        f.MinZ.ToString(CultureInfo.InvariantCulture),
                        f.MaxZ.ToString(CultureInfo.InvariantCulture),
                        f.Radius.ToString(CultureInfo.InvariantCulture),
                        f.BoundaryPoints.Count.ToString(CultureInfo.InvariantCulture)
                    }));
            }
        }

        private void WriteTopologyEdgesCsv(string path, List<TopologyEdge> edges)
        {
            using (var sw = new StreamWriter(path))
            {
                sw.WriteLine("FromClusterID,ToClusterID,EdgeType,MinDistance");
                foreach (var e in edges)
                    sw.WriteLine($"{e.FromClusterID},{e.ToClusterID},{e.EdgeType}," +
                                 e.MinDistance.ToString(CultureInfo.InvariantCulture));
            }
        }

        private void WritePrimitiveCandidatesCsv(
            string path, List<PrimitiveCandidate> cands)
        {
            using (var sw = new StreamWriter(path))
            {
                sw.WriteLine("PrimitiveType,RelatedClusters," +
                             "Length,Width,Height,Radius,Depth,BooleanType");
                foreach (var c in cands)
                    sw.WriteLine(string.Join(",", new[]
                    {
                        c.PrimitiveType,
                        string.Join(";", c.RelatedClusters),
                        c.Length.ToString(CultureInfo.InvariantCulture),
                        c.Width.ToString(CultureInfo.InvariantCulture),
                        c.Height.ToString(CultureInfo.InvariantCulture),
                        c.Radius.ToString(CultureInfo.InvariantCulture),
                        c.Depth.ToString(CultureInfo.InvariantCulture),
                        c.BooleanType
                    }));
            }
        }
    }
}