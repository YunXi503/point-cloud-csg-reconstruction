using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;

// 修正版：以 Model A 分割器為基礎，圓柱偵測改為「Z 軸」(孔 r22.5 / 環 r35 皆沿 Z)。
// 平面分箱、圓弧 DBSCAN、圓擬合、內外判斷、弧段合併、小群丟 -1 等邏輯與 Model A 一致。
namespace 特徵辨識核心演算法Blind_Hole_Hex_Base
{
    public class PointData
    {
        public double X, Y, Z, NX, NY, NZ;
        public int ClusterID = -1;
        public string FeatureType = "unclassified";
    }

    public class FeatureSummary
    {
        public int ClusterID;
        public string Type, Normal, Position;
        public int Count;
        public double Radius;
    }

    class Program
    {
        static void Main(string[] args)
        {
            string inputPath = args.Length > 0 ? args[0]
                : @"C:\Users\Admin\Desktop\云析論文\零件\Blind-Hole Hex Base點雲.csv";
            string outputPath = args.Length > 1 ? args[1]
                : @"C:\Users\Admin\Desktop\云析論文\零件\Result_Blind-Hole Hex Base_fixed.csv";
            new FeatureClassifier().Execute(inputPath, outputPath);
            if (!Console.IsInputRedirected) { Console.WriteLine("\n按下任意鍵結束..."); Console.ReadKey(); }
        }
    }

    public class FeatureClassifier
    {
        private const double NORMAL_BIN_DEG = 8.0;
        private const double D_BIN_MM = 1.5;
        private const double NORMAL_STD_THR = 0.02;
        private const int PLANE_MIN_PTS = 20;

        private const double CYL_XY_EPS = 5.0;
        private const int CYL_XY_MIN_PTS = 5;
        private const double META_EPS = 4.0;
        private const double META_R_SCALE = 0.5;
        private const int CYL_FINAL_MIN_N = 15;

        private const int RELIABLE_CYL_MIN_PTS = 30;
        private const double FIT_RADIUS_MIN = 5.0;
        private const double FIT_RADIUS_MAX = 80.0;
        private const double FIT_MEDIAN_RESID_THR = 0.75;
        private const double REFINE_RADIUS_TOL = 1.5;
        private const double REFINE_AXIS_PAD = 2.0;
        private const double REFINE_NORMAL_ALIGNMENT = 0.80;
        private const double REFINE_AXIS_COMPONENT_MAX = 0.22;

        public void Execute(string inputPath, string outputPath)
        {
            if (!File.Exists(inputPath)) { Console.WriteLine("找不到：" + inputPath); return; }
            var points = ReadPoints(inputPath);
            int n = points.Count;
            Console.WriteLine("讀入 " + n + " 個點");

            int clusterId = 0;
            var summaries = new List<FeatureSummary>();

            int cylZ = ClusterCylindersAxisZ(points, ref clusterId, summaries);
            Console.WriteLine("圓柱(軸Z)：" + cylZ + " 個");

            int planes = ClusterPlanes(points, ref clusterId, summaries);
            Console.WriteLine("平面特徵：" + planes + " 個");

            int refined = RefineCylinderAssignments(points, summaries);
            RecalculateSummaryCounts(points, summaries);
            clusterId = CompactClusterIds(points, summaries);
            RecalculateSummaryCounts(points, summaries);
            Console.WriteLine("圓柱面重分類修正：" + refined + " 個點");

            int classified = points.Count(p => p.ClusterID >= 0);
            int unclassified = points.Count(p => p.ClusterID < 0);
            Console.WriteLine("\n共識別 " + clusterId + " 個幾何特徵");
            Console.WriteLine("已分類：" + classified + " / " + n + "   未分類：" + unclassified);

            PrintSummary(summaries);
            WriteOutput(outputPath, points);
            Console.WriteLine("\n輸出：" + outputPath);
        }

        private int ClusterPlanes(List<PointData> points, ref int clusterId, List<FeatureSummary> summaries)
        {
            int n = points.Count;
            double[] nxN = new double[n], nyN = new double[n], nzN = new double[n];
            for (int i = 0; i < n; i++)
                NormalizeNormal(points[i].NX, points[i].NY, points[i].NZ, out nxN[i], out nyN[i], out nzN[i]);

            int[] tBin = new int[n], pBin = new int[n], dBin = new int[n];
            for (int i = 0; i < n; i++)
            {
                double d = nxN[i] * points[i].X + nyN[i] * points[i].Y + nzN[i] * points[i].Z;
                tBin[i] = (int)Math.Round(Math.Atan2(nyN[i], nxN[i]) * 180.0 / Math.PI / NORMAL_BIN_DEG);
                pBin[i] = (int)Math.Round(Math.Asin(Clamp(nzN[i], -1, 1)) * 180.0 / Math.PI / NORMAL_BIN_DEG);
                dBin[i] = (int)Math.Round(d / D_BIN_MM);
            }

            var groups = new Dictionary<(int, int, int), List<int>>();
            for (int i = 0; i < n; i++)
            {
                var key = (tBin[i], pBin[i], dBin[i]);
                if (!groups.ContainsKey(key)) groups[key] = new List<int>();
                groups[key].Add(i);
            }

            int count = 0;
            foreach (var kv in groups.OrderByDescending(g => g.Value.Count))
            {
                var pts = kv.Value;
                if (pts.Count < PLANE_MIN_PTS) continue;

                double nxMean = pts.Average(i => points[i].NX);
                double nzMean = pts.Average(i => points[i].NZ);
                double nxStd = Math.Sqrt(pts.Average(i => Sq(points[i].NX - nxMean)));
                double nzStd = Math.Sqrt(pts.Average(i => Sq(points[i].NZ - nzMean)));
                if (nxStd > NORMAL_STD_THR || nzStd > NORMAL_STD_THR) continue;

                double thR = kv.Key.Item1 * NORMAL_BIN_DEG * Math.PI / 180.0;
                double phR = kv.Key.Item2 * NORMAL_BIN_DEG * Math.PI / 180.0;
                double nxR = Math.Cos(phR) * Math.Cos(thR);
                double nyR = Math.Cos(phR) * Math.Sin(thR);
                double nzR = Math.Sin(phR);
                double dv = kv.Key.Item3 * D_BIN_MM;

                string ftype;
                if (Math.Abs(nzR) > 0.90) ftype = "Plane_XY";
                else if (Math.Abs(nzR) < 0.30) ftype = "Plane_vertical";
                else ftype = "Plane_oblique";

                foreach (int i in pts)
                    if (points[i].ClusterID == -1) { points[i].ClusterID = clusterId; points[i].FeatureType = ftype; }

                summaries.Add(new FeatureSummary
                {
                    ClusterID = clusterId,
                    Type = ftype,
                    Normal = "N=(" + nxR.ToString("F2") + "," + nyR.ToString("F2") + "," + nzR.ToString("F2") + ")",
                    Position = "d=" + dv.ToString("F1"),
                    Count = pts.Count
                });
                clusterId++; count++;
            }
            return count;
        }

        // 圓柱(軸平行Z) — XY 空間 DBSCAN + 圓擬合 + 弧段合併
        private int ClusterCylindersAxisZ(List<PointData> points, ref int clusterId, List<FeatureSummary> summaries)
        {
            var curved = points.Where(p => p.ClusterID < 0 && Math.Abs(p.NZ) < 0.15).ToList();
            if (curved.Count == 0) return 0;

            int m = curved.Count;
            double[] xs = curved.Select(p => p.X).ToArray();
            double[] ys = curved.Select(p => p.Y).ToArray();
            int[] arcLabels = DBSCAN2D(xs, ys, CYL_XY_EPS, CYL_XY_MIN_PTS);

            var arcInfoList = new List<ArcInfo>();
            foreach (int lbl in arcLabels.Distinct().Where(l => l >= 0))
            {
                var idx = Enumerable.Range(0, m).Where(i => arcLabels[i] == lbl).ToList();
                if (idx.Count < CYL_XY_MIN_PTS) continue;

                CircleFit fit;
                if (!TryFitCircle(idx.Select(i => curved[i].X).ToList(),
                                  idx.Select(i => curved[i].Y).ToList(), out fit)) continue;
                if (!IsReliableCircleFit(fit)) continue;

                double sumDot = 0;
                foreach (int i in idx)
                {
                    double da = curved[i].X - fit.C1, db = curved[i].Y - fit.C2;
                    double rr = Math.Sqrt(da * da + db * db);
                    if (rr < 1e-9) continue;
                    sumDot += (da * curved[i].NX + db * curved[i].NY) / rr;
                }
                arcInfoList.Add(new ArcInfo
                {
                    ArcLabel = lbl, CX = fit.C1, CZ = fit.C2, R = fit.R,
                    IsInner = sumDot < 0, PointCount = idx.Count, Indices = idx
                });
            }
            if (arcInfoList.Count == 0) return 0;

            double[] metaX = arcInfoList.Select(a => a.CX).ToArray();
            double[] metaY = arcInfoList.Select(a => a.CZ).ToArray();
            double[] metaR = arcInfoList.Select(a => a.R * META_R_SCALE).ToArray();
            int[] metaLabels = DBSCAN3D(metaX, metaY, metaR, META_EPS, 1);

            int count = 0;
            foreach (int mlbl in metaLabels.Distinct().Where(l => l >= 0))
            {
                var subArcs = Enumerable.Range(0, arcInfoList.Count)
                                        .Where(i => metaLabels[i] == mlbl)
                                        .Select(i => arcInfoList[i]).ToList();
                int totalN = subArcs.Sum(a => a.PointCount);
                if (totalN < CYL_FINAL_MIN_N) continue;

                double cxW = subArcs.Sum(a => a.CX * a.PointCount) / totalN;
                double cyW = subArcs.Sum(a => a.CZ * a.PointCount) / totalN;
                double rW = subArcs.Sum(a => a.R * a.PointCount) / totalN;
                bool isInner = subArcs.Sum(a => (a.IsInner ? 1.0 : 0.0) * a.PointCount) / totalN > 0.5;

                string ftype = isInner ? "Cylinder_axisZ_inner" : "Cylinder_axisZ_outer";
                foreach (var arc in subArcs)
                    foreach (int i in arc.Indices)
                    { curved[i].ClusterID = clusterId; curved[i].FeatureType = ftype; }

                summaries.Add(new FeatureSummary
                {
                    ClusterID = clusterId, Type = ftype, Normal = "axis=Z",
                    Position = "C=(" + cxW.ToString("F0") + "," + cyW.ToString("F0") + ")",
                    Count = totalN, Radius = rW
                });
                clusterId++; count++;
            }
            return count;
        }

        private int RefineCylinderAssignments(List<PointData> points, List<FeatureSummary> summaries)
        {
            var circles = BuildReliableCylinderCircles(points);
            int refined = 0;
            foreach (var p in points)
            {
                if (p.FeatureType.StartsWith("Cylinder", StringComparison.Ordinal)) continue;
                CylinderCircle best = null;
                double bestResidual = REFINE_RADIUS_TOL;
                foreach (var c in circles)
                {
                    double axisCoord = p.Z, axisNormal = Math.Abs(p.NZ);
                    double da = p.X - c.C1, db = p.Y - c.C2;
                    double rr = Math.Sqrt(da * da + db * db);
                    if (rr < 1e-9) continue;
                    double radialNormal = Math.Abs((da * p.NX + db * p.NY) / rr);
                    double residual = Math.Abs(rr - c.R);
                    if (axisCoord < c.MinAxis - REFINE_AXIS_PAD || axisCoord > c.MaxAxis + REFINE_AXIS_PAD) continue;
                    if (axisNormal > REFINE_AXIS_COMPONENT_MAX) continue;
                    if (radialNormal < REFINE_NORMAL_ALIGNMENT) continue;
                    if (residual > REFINE_RADIUS_TOL) continue;
                    if (residual < bestResidual) { bestResidual = residual; best = c; }
                }
                if (best == null) continue;
                p.ClusterID = best.ClusterID; p.FeatureType = best.Type; refined++;
            }
            return refined;
        }

        private List<CylinderCircle> BuildReliableCylinderCircles(List<PointData> points)
        {
            var circles = new List<CylinderCircle>();
            foreach (var group in points.Where(p => p.FeatureType.StartsWith("Cylinder", StringComparison.Ordinal))
                                        .GroupBy(p => p.ClusterID))
            {
                var pts = group.ToList();
                if (pts.Count < RELIABLE_CYL_MIN_PTS) continue;
                CircleFit fit;
                if (!TryFitCircle(pts.Select(p => p.X).ToList(), pts.Select(p => p.Y).ToList(), out fit)) continue;
                if (!IsReliableCircleFit(fit)) continue;
                circles.Add(new CylinderCircle
                {
                    ClusterID = group.Key, Type = pts[0].FeatureType, Axis = "Z",
                    C1 = fit.C1, C2 = fit.C2, R = fit.R,
                    MinAxis = pts.Min(p => p.Z), MaxAxis = pts.Max(p => p.Z), PointCount = pts.Count
                });
            }
            return circles;
        }

        private void RecalculateSummaryCounts(List<PointData> points, List<FeatureSummary> summaries)
        {
            var counts = points.Where(p => p.ClusterID >= 0).GroupBy(p => p.ClusterID)
                               .ToDictionary(g => g.Key, g => g.Count());
            summaries.RemoveAll(s => !counts.ContainsKey(s.ClusterID));
            foreach (var s in summaries) s.Count = counts[s.ClusterID];
        }

        private int CompactClusterIds(List<PointData> points, List<FeatureSummary> summaries)
        {
            var activeIds = points.Where(p => p.ClusterID >= 0).Select(p => p.ClusterID)
                                  .Distinct().OrderBy(id => id).ToList();
            var map = new Dictionary<int, int>();
            for (int i = 0; i < activeIds.Count; i++) map[activeIds[i]] = i;
            foreach (var p in points) if (p.ClusterID >= 0) p.ClusterID = map[p.ClusterID];
            summaries.RemoveAll(s => !map.ContainsKey(s.ClusterID));
            foreach (var s in summaries) s.ClusterID = map[s.ClusterID];
            summaries.Sort((a, b) => a.ClusterID.CompareTo(b.ClusterID));
            return activeIds.Count;
        }

        private bool TryFitCircle(List<double> a, List<double> b, out CircleFit fit)
        {
            fit = null;
            int n = a.Count;
            if (n < 3 || b.Count != n) return false;
            double saa = 0, sab = 0, sa = 0, sbb = 0, sb = 0, sar = 0, sbr = 0, sr = 0;
            for (int i = 0; i < n; i++)
            {
                double ai = a[i], bi = b[i], r2 = ai * ai + bi * bi, x0 = 2.0 * ai, x1 = 2.0 * bi;
                saa += x0 * x0; sab += x0 * x1; sa += x0; sbb += x1 * x1; sb += x1;
                sar += x0 * r2; sbr += x1 * r2; sr += r2;
            }
            double[,] mat = { { saa, sab, sa }, { sab, sbb, sb }, { sa, sb, n } };
            double[] rhs = { sar, sbr, sr };
            double[] sol;
            if (!Solve3x3(mat, rhs, out sol)) return false;
            double c1 = sol[0], c2 = sol[1], k = sol[2];
            double r2fit = c1 * c1 + c2 * c2 + k;
            if (r2fit <= 0 || double.IsNaN(r2fit) || double.IsInfinity(r2fit)) return false;
            double radius = Math.Sqrt(r2fit);
            var residuals = new List<double>();
            for (int i = 0; i < n; i++)
                residuals.Add(Math.Abs(Math.Sqrt(Sq(a[i] - c1) + Sq(b[i] - c2)) - radius));
            residuals.Sort();
            fit = new CircleFit { C1 = c1, C2 = c2, R = radius, MedianResidual = residuals[n / 2] };
            return true;
        }

        private bool IsReliableCircleFit(CircleFit fit)
        {
            if (fit.R < FIT_RADIUS_MIN || fit.R > FIT_RADIUS_MAX) return false;
            if (fit.MedianResidual > FIT_MEDIAN_RESID_THR) return false;
            return true;
        }

        private bool Solve3x3(double[,] a, double[] b, out double[] x)
        {
            x = new double[3];
            double[,] m = new double[3, 4];
            for (int r = 0; r < 3; r++) { for (int c = 0; c < 3; c++) m[r, c] = a[r, c]; m[r, 3] = b[r]; }
            for (int col = 0; col < 3; col++)
            {
                int pivot = col;
                for (int r = col + 1; r < 3; r++) if (Math.Abs(m[r, col]) > Math.Abs(m[pivot, col])) pivot = r;
                if (Math.Abs(m[pivot, col]) < 1e-12) return false;
                if (pivot != col) for (int c = col; c < 4; c++) { double t = m[col, c]; m[col, c] = m[pivot, c]; m[pivot, c] = t; }
                double div = m[col, col];
                for (int c = col; c < 4; c++) m[col, c] /= div;
                for (int r = 0; r < 3; r++) { if (r == col) continue; double f = m[r, col]; for (int c = col; c < 4; c++) m[r, c] -= f * m[col, c]; }
            }
            for (int i = 0; i < 3; i++) x[i] = m[i, 3];
            return true;
        }

        private int[] DBSCAN2D(double[] x, double[] y, double eps, int minPts)
        {
            int n = x.Length;
            int[] labels = Enumerable.Repeat(-1, n).ToArray();
            int cid = 0; double eps2 = eps * eps;
            Func<int, List<int>> nb = (i) =>
            {
                var res = new List<int>();
                for (int j = 0; j < n; j++) { double dx = x[j] - x[i], dy = y[j] - y[i]; if (dx * dx + dy * dy <= eps2) res.Add(j); }
                return res;
            };
            for (int i = 0; i < n; i++)
            {
                if (labels[i] != -1) continue;
                var seeds = nb(i);
                if (seeds.Count < minPts) { labels[i] = -2; continue; }
                labels[i] = cid;
                var q = new Queue<int>(seeds);
                while (q.Count > 0)
                {
                    int p = q.Dequeue();
                    if (labels[p] == -2) labels[p] = cid;
                    if (labels[p] != -1) continue;
                    labels[p] = cid;
                    var pnb = nb(p);
                    if (pnb.Count >= minPts) foreach (int r in pnb) q.Enqueue(r);
                }
                cid++;
            }
            return labels;
        }

        private int[] DBSCAN3D(double[] x, double[] y, double[] z, double eps, int minPts)
        {
            int n = x.Length;
            int[] labels = Enumerable.Repeat(-1, n).ToArray();
            int cid = 0; double eps2 = eps * eps;
            Func<int, List<int>> nb = (i) =>
            {
                var res = new List<int>();
                for (int j = 0; j < n; j++) { double dx = x[j] - x[i], dy = y[j] - y[i], dz = z[j] - z[i]; if (dx * dx + dy * dy + dz * dz <= eps2) res.Add(j); }
                return res;
            };
            for (int i = 0; i < n; i++)
            {
                if (labels[i] != -1) continue;
                var seeds = nb(i);
                if (seeds.Count < minPts) { labels[i] = -2; continue; }
                labels[i] = cid;
                var q = new Queue<int>(seeds);
                while (q.Count > 0)
                {
                    int p = q.Dequeue();
                    if (labels[p] == -2) labels[p] = cid;
                    if (labels[p] != -1) continue;
                    labels[p] = cid;
                    var pnb = nb(p);
                    if (pnb.Count >= minPts) foreach (int r in pnb) q.Enqueue(r);
                }
                cid++;
            }
            return labels;
        }

        private class ArcInfo { public int ArcLabel, PointCount; public double CX, CZ, R; public bool IsInner; public List<int> Indices; }
        private class CircleFit { public double C1, C2, R, MedianResidual; }
        private class CylinderCircle { public int ClusterID, PointCount; public string Type, Axis; public double C1, C2, R, MinAxis, MaxAxis; }

        private static void NormalizeNormal(double nx, double ny, double nz, out double ox, out double oy, out double oz)
        {
            if (nz < -1e-3) { ox = -nx; oy = -ny; oz = -nz; }
            else if (Math.Abs(nz) < 1e-3 && ny < -1e-3) { ox = -nx; oy = -ny; oz = -nz; }
            else if (Math.Abs(nz) < 1e-3 && Math.Abs(ny) < 1e-3 && nx < -1e-3) { ox = -nx; oy = -ny; oz = -nz; }
            else { ox = nx; oy = ny; oz = nz; }
        }

        private static double Clamp(double v, double lo, double hi) => v < lo ? lo : v > hi ? hi : v;
        private static double Sq(double v) => v * v;
        private static string Fmt(string s, int w) => s.Length >= w ? s.Substring(0, w) : s + new string(' ', w - s.Length);

        private void PrintSummary(List<FeatureSummary> summaries)
        {
            Console.WriteLine("\n" + Fmt("ID", 5) + Fmt("Type", 24) + Fmt("Normal", 24) + Fmt("Position", 18) + Fmt("Count", 8) + "Radius");
            Console.WriteLine(new string('-', 88));
            foreach (var s in summaries)
                Console.WriteLine(Fmt(s.ClusterID.ToString(), 5) + Fmt(s.Type, 24) + Fmt(s.Normal, 24)
                    + Fmt(s.Position, 18) + Fmt(s.Count.ToString(), 8) + (s.Radius > 0 ? s.Radius.ToString("F2") : "-"));
        }

        private List<PointData> ReadPoints(string path)
        {
            var pts = new List<PointData>();
            var lines = File.ReadAllLines(path);
            for (int i = 1; i < lines.Length; i++)
            {
                var c = lines[i].Split(',');
                if (c.Length < 6) continue;
                pts.Add(new PointData
                {
                    X = double.Parse(c[0]), Y = double.Parse(c[1]), Z = double.Parse(c[2]),
                    NX = double.Parse(c[3]), NY = double.Parse(c[4]), NZ = double.Parse(c[5])
                });
            }
            return pts;
        }

        private void WriteOutput(string path, List<PointData> points)
        {
            using (var sw = new StreamWriter(path))
            {
                sw.WriteLine("X,Y,Z,NX,NY,NZ,ClusterID,FeatureType");
                foreach (var p in points)
                    sw.WriteLine(p.X + "," + p.Y + "," + p.Z + "," + p.NX + "," + p.NY + "," + p.NZ
                                 + "," + p.ClusterID + "," + p.FeatureType);
            }
        }
    }
}
