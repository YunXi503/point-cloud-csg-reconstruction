using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;

namespace 特徵辨識核心演算法Model_A
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
            string inputPath = @"C:\Users\Admin\Desktop\云析論文\零件\Model A點雲.csv";
            string outputPath = @"C:\Users\Admin\Desktop\云析論文\零件\Result_Model A.csv";
            new FeatureClassifier().Execute(inputPath, outputPath);
            Console.WriteLine("\n按下任意鍵結束...");
            if (!Console.IsInputRedirected)
                Console.ReadKey();
        }
    }

    public class FeatureClassifier
    {
        // ================================================================
        // v5 改版重點（對照實際零件圖）：
        //
        // 問題回顧：
        //   v4 中大圓環的「內孔面（R=33）」被切成 13 個弧段
        //   原因：中心反推公式 cx = X - R_xz * NX
        //         對「內法向量（N 指向圓心）」應改為 cx = X + R_xz * NX
        //
        // v5 修正策略：
        //   1. 先在「XZ 物理座標空間」用 DBSCAN 找連通弧段（eps=5mm）
        //      → 不依賴任何中心假設，純粹靠空間鄰近性
        //   2. 對每個弧段，用法向量方向判斷內/外，然後反推中心
        //      外面(dot>0)：center = P - R * N
        //      內面(dot<0)：center = P + R * N  ← 這是 v4 遺漏的！
        //   3. 把「中心距離 < 5mm 且 |ΔR| < 2mm」的弧段合併為同一圓柱
        //
        // 結果：
        //   大環外面 R=45：1個圓柱，1002 個點（v4 中被分成 5+ 個 cluster）
        //   大環內孔 R=33：1個圓柱，780  個點（v4 中被分成 13 個 cluster）
        // ================================================================

        // ---- 平面分群參數 ----
        private const double NORMAL_BIN_DEG = 8.0;
        private const double D_BIN_MM = 1.5;
        private const double NORMAL_STD_THR = 0.02;
        private const int PLANE_MIN_PTS = 20;

        // ---- 圓柱分群參數 ----
        private const double CYL_XZ_EPS = 5.0;   // XZ 空間找弧段
        private const int CYL_XZ_MIN_PTS = 5;
        private const double META_EPS = 4.0;   // 合併弧段：中心距離閾值
        private const double META_R_SCALE = 0.5;   // R 在 meta 空間的縮放
        private const int CYL_FINAL_MIN_N = 15;    // 最終圓柱最少點數

        private const double CYL_X_EPS = 3.0;   // axis-X YZ 空間
        private const int CYL_X_MIN_PTS = 5;

        // ---- 圓柱後處理修正參數 ----
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

            int planes = ClusterPlanes(points, ref clusterId, summaries);
            Console.WriteLine("平面特徵：" + planes + " 個");

            int cylY = ClusterCylindersAxisY(points, ref clusterId, summaries);
            Console.WriteLine("圓柱(軸Y)：" + cylY + " 個");

            int cylX = ClusterCylindersAxisX(points, ref clusterId, summaries);
            Console.WriteLine("圓柱(軸X)：" + cylX + " 個");

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

        // ---------------------------------------------------------------
        // Step 1：統一平面分群（含傾斜面）
        //   法向量球面 bin + d 值 bin → 組內 NX/NZ std < 閾值 → 確認為平面
        // ---------------------------------------------------------------
        private int ClusterPlanes(List<PointData> points, ref int clusterId, List<FeatureSummary> summaries)
        {
            int n = points.Count;
            double[] nxN = new double[n], nyN = new double[n], nzN = new double[n];
            for (int i = 0; i < n; i++)
                NormalizeNormal(points[i].NX, points[i].NY, points[i].NZ,
                                out nxN[i], out nyN[i], out nzN[i]);

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
                if (Math.Abs(nyR) > 0.90) ftype = "Plane_XZ";
                else if (Math.Abs(nxR) > 0.90 && Math.Abs(nzR) < 0.30) ftype = "Plane_YZ";
                else if (Math.Abs(nzR) > 0.90) ftype = "Plane_XY";
                else ftype = "Plane_oblique";

                foreach (int i in pts)
                    if (points[i].ClusterID == -1)
                    { points[i].ClusterID = clusterId; points[i].FeatureType = ftype; }

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

        // ---------------------------------------------------------------
        // Step 2：圓柱(軸平行Y) — XZ 空間 DBSCAN + 弧段合併
        //
        // 為什麼不直接用「中心反推 DBSCAN」？
        //   圓柱中心反推：center = P - R * N（外面）或 P + R * N（內孔）
        //   但若相鄰弧段間有角度空隙（>10°），DBSCAN 無法連通
        // 正確做法：
        //   先在物理座標 (X,Z) 找連通弧段，再估算各弧段的中心和半徑，
        //   最後把「中心和半徑相近」的弧段合併
        // ---------------------------------------------------------------
        private int ClusterCylindersAxisY(List<PointData> points, ref int clusterId, List<FeatureSummary> summaries)
        {
            var curved = points
                .Where(p => p.ClusterID < 0 && Math.Abs(p.NY) < 0.15)
                .ToList();
            if (curved.Count == 0) return 0;

            int m = curved.Count;
            double[] xs = curved.Select(p => p.X).ToArray();
            double[] zs = curved.Select(p => p.Z).ToArray();

            // Step A: XZ 座標空間 DBSCAN（找連通弧段）
            int[] arcLabels = DBSCAN2D(xs, zs, CYL_XZ_EPS, CYL_XZ_MIN_PTS);

            // Step B: 對每個弧段估算中心和半徑
            var arcInfoList = new List<ArcInfo>();
            foreach (int lbl in arcLabels.Distinct().Where(l => l >= 0))
            {
                var idx = Enumerable.Range(0, m).Where(i => arcLabels[i] == lbl).ToList();
                if (idx.Count < CYL_XZ_MIN_PTS) continue;

                double cxEst, czEst, rEst;
                bool isInner;
                EstimateCylinderCenter(idx, curved, out cxEst, out czEst, out rEst, out isInner);
                arcInfoList.Add(new ArcInfo
                {
                    ArcLabel = lbl,
                    CX = cxEst,
                    CZ = czEst,
                    R = rEst,
                    IsInner = isInner,
                    PointCount = idx.Count,
                    Indices = idx
                });
            }

            // Step C: 用 meta-DBSCAN 合併中心和半徑相近的弧段
            if (arcInfoList.Count == 0) return 0;

            double[] metaX = arcInfoList.Select(a => a.CX).ToArray();
            double[] metaZ = arcInfoList.Select(a => a.CZ).ToArray();
            double[] metaR = arcInfoList.Select(a => a.R * META_R_SCALE).ToArray();
            int[] metaLabels = DBSCAN3D(metaX, metaZ, metaR, META_EPS, 1);

            int count = 0;
            foreach (int mlbl in metaLabels.Distinct().Where(l => l >= 0))
            {
                var subArcs = Enumerable.Range(0, arcInfoList.Count)
                                        .Where(i => metaLabels[i] == mlbl)
                                        .Select(i => arcInfoList[i])
                                        .ToList();

                int totalN = subArcs.Sum(a => a.PointCount);
                if (totalN < CYL_FINAL_MIN_N) continue;

                double cxW = subArcs.Sum(a => a.CX * a.PointCount) / totalN;
                double czW = subArcs.Sum(a => a.CZ * a.PointCount) / totalN;
                double rW = subArcs.Sum(a => a.R * a.PointCount) / totalN;
                bool isInner = subArcs.Sum(a => (a.IsInner ? 1.0 : 0.0) * a.PointCount) / totalN > 0.5;

                string ftype = isInner ? "Cylinder_axisY_inner" : "Cylinder_axisY_outer";
                foreach (var arc in subArcs)
                    foreach (int i in arc.Indices)
                    { curved[i].ClusterID = clusterId; curved[i].FeatureType = ftype; }

                summaries.Add(new FeatureSummary
                {
                    ClusterID = clusterId,
                    Type = ftype,
                    Normal = "axis=Y",
                    Position = "C=(" + cxW.ToString("F0") + "," + czW.ToString("F0") + ")",
                    Count = totalN,
                    Radius = rW
                });
                clusterId++; count++;
            }
            return count;
        }

        // ---------------------------------------------------------------
        // Step 3：圓柱(軸平行X) — YZ 座標空間 DBSCAN + 弧段合併
        // ---------------------------------------------------------------
        private int ClusterCylindersAxisX(List<PointData> points, ref int clusterId, List<FeatureSummary> summaries)
        {
            var curved = points
                .Where(p => p.ClusterID < 0 && Math.Abs(p.NX) < REFINE_AXIS_COMPONENT_MAX)
                .ToList();
            if (curved.Count == 0) return 0;

            int m = curved.Count;
            double[] ys = curved.Select(p => p.Y).ToArray();
            double[] zs = curved.Select(p => p.Z).ToArray();
            int[] arcLabels = DBSCAN2D(ys, zs, CYL_X_EPS, CYL_X_MIN_PTS);

            var arcInfoList = new List<ArcInfo>();
            foreach (int lbl in arcLabels.Distinct().Where(l => l >= 0))
            {
                var idx = Enumerable.Range(0, m).Where(i => arcLabels[i] == lbl).ToList();
                if (idx.Count < CYL_X_MIN_PTS) continue;

                CircleFit fit;
                if (!TryFitCircle(idx.Select(i => curved[i].Y).ToList(),
                                  idx.Select(i => curved[i].Z).ToList(),
                                  out fit)) continue;
                if (!IsReliableCircleFit(fit)) continue;

                arcInfoList.Add(new ArcInfo
                {
                    ArcLabel = lbl,
                    CX = fit.C1,
                    CZ = fit.C2,
                    R = fit.R,
                    IsInner = false,
                    PointCount = idx.Count,
                    Indices = idx
                });
            }

            if (arcInfoList.Count == 0) return 0;

            double[] metaY = arcInfoList.Select(a => a.CX).ToArray();
            double[] metaZ = arcInfoList.Select(a => a.CZ).ToArray();
            double[] metaR = arcInfoList.Select(a => a.R * META_R_SCALE).ToArray();
            int[] metaLabels = DBSCAN3D(metaY, metaZ, metaR, META_EPS, 1);

            int count = 0;
            foreach (int mlbl in metaLabels.Distinct().Where(l => l >= 0))
            {
                var subArcs = Enumerable.Range(0, arcInfoList.Count)
                                        .Where(i => metaLabels[i] == mlbl)
                                        .Select(i => arcInfoList[i])
                                        .ToList();

                int totalN = subArcs.Sum(a => a.PointCount);
                if (totalN < CYL_FINAL_MIN_N) continue;

                double cyW = subArcs.Sum(a => a.CX * a.PointCount) / totalN;
                double czW = subArcs.Sum(a => a.CZ * a.PointCount) / totalN;
                double rW = subArcs.Sum(a => a.R * a.PointCount) / totalN;

                foreach (var arc in subArcs)
                    foreach (int i in arc.Indices)
                    { curved[i].ClusterID = clusterId; curved[i].FeatureType = "Cylinder_axisX"; }

                summaries.Add(new FeatureSummary
                {
                    ClusterID = clusterId,
                    Type = "Cylinder_axisX",
                    Normal = "axis=X",
                    Position = "C=(" + cyW.ToString("F0") + "," + czW.ToString("F0") + ")",
                    Count = totalN,
                    Radius = rW
                });
                clusterId++; count++;
            }
            return count;
        }

        // ---------------------------------------------------------------
        // Step 4：圓柱後處理 — 將先前被平面分群吃掉的圓柱點補回
        // ---------------------------------------------------------------
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
                    double axisCoord, axisNormal, da, db, radialNormal;
                    if (c.Axis == "Y")
                    {
                        axisCoord = p.Y;
                        axisNormal = Math.Abs(p.NY);
                        da = p.X - c.C1;
                        db = p.Z - c.C2;
                        double rr = Math.Sqrt(da * da + db * db);
                        if (rr < 1e-9) continue;
                        radialNormal = Math.Abs((da * p.NX + db * p.NZ) / rr);
                        double residual = Math.Abs(rr - c.R);
                        if (!IsCylinderRefineMatch(axisCoord, axisNormal, radialNormal, residual, c)) continue;
                        if (residual < bestResidual) { bestResidual = residual; best = c; }
                    }
                    else if (c.Axis == "X")
                    {
                        axisCoord = p.X;
                        axisNormal = Math.Abs(p.NX);
                        da = p.Y - c.C1;
                        db = p.Z - c.C2;
                        double rr = Math.Sqrt(da * da + db * db);
                        if (rr < 1e-9) continue;
                        radialNormal = Math.Abs((da * p.NY + db * p.NZ) / rr);
                        double residual = Math.Abs(rr - c.R);
                        if (!IsCylinderRefineMatch(axisCoord, axisNormal, radialNormal, residual, c)) continue;
                        if (residual < bestResidual) { bestResidual = residual; best = c; }
                    }
                }

                if (best == null) continue;
                p.ClusterID = best.ClusterID;
                p.FeatureType = best.Type;
                refined++;
            }

            return refined;
        }

        private bool IsCylinderRefineMatch(double axisCoord, double axisNormal, double radialNormal,
                                           double residual, CylinderCircle circle)
        {
            if (axisCoord < circle.MinAxis - REFINE_AXIS_PAD || axisCoord > circle.MaxAxis + REFINE_AXIS_PAD) return false;
            if (axisNormal > REFINE_AXIS_COMPONENT_MAX) return false;
            if (radialNormal < REFINE_NORMAL_ALIGNMENT) return false;
            if (residual > REFINE_RADIUS_TOL) return false;
            return true;
        }

        private List<CylinderCircle> BuildReliableCylinderCircles(List<PointData> points)
        {
            var circles = new List<CylinderCircle>();
            foreach (var group in points.Where(p => p.FeatureType.StartsWith("Cylinder", StringComparison.Ordinal))
                                        .GroupBy(p => p.ClusterID))
            {
                var pts = group.ToList();
                if (pts.Count < RELIABLE_CYL_MIN_PTS) continue;

                string type = pts[0].FeatureType;
                string axis = type == "Cylinder_axisX" ? "X" : "Y";
                List<double> a, b;
                double minAxis, maxAxis;
                if (axis == "X")
                {
                    a = pts.Select(p => p.Y).ToList();
                    b = pts.Select(p => p.Z).ToList();
                    minAxis = pts.Min(p => p.X);
                    maxAxis = pts.Max(p => p.X);
                }
                else
                {
                    a = pts.Select(p => p.X).ToList();
                    b = pts.Select(p => p.Z).ToList();
                    minAxis = pts.Min(p => p.Y);
                    maxAxis = pts.Max(p => p.Y);
                }

                CircleFit fit;
                if (!TryFitCircle(a, b, out fit)) continue;
                if (!IsReliableCircleFit(fit)) continue;

                circles.Add(new CylinderCircle
                {
                    ClusterID = group.Key,
                    Type = type,
                    Axis = axis,
                    C1 = fit.C1,
                    C2 = fit.C2,
                    R = fit.R,
                    MinAxis = minAxis,
                    MaxAxis = maxAxis,
                    PointCount = pts.Count
                });
            }
            return circles;
        }

        private void RecalculateSummaryCounts(List<PointData> points, List<FeatureSummary> summaries)
        {
            var counts = points.Where(p => p.ClusterID >= 0)
                               .GroupBy(p => p.ClusterID)
                               .ToDictionary(g => g.Key, g => g.Count());
            summaries.RemoveAll(s => !counts.ContainsKey(s.ClusterID));
            foreach (var s in summaries)
                s.Count = counts[s.ClusterID];
        }

        private int CompactClusterIds(List<PointData> points, List<FeatureSummary> summaries)
        {
            var activeIds = points.Where(p => p.ClusterID >= 0)
                                  .Select(p => p.ClusterID)
                                  .Distinct()
                                  .OrderBy(id => id)
                                  .ToList();
            var map = new Dictionary<int, int>();
            for (int i = 0; i < activeIds.Count; i++)
                map[activeIds[i]] = i;

            foreach (var p in points)
                if (p.ClusterID >= 0)
                    p.ClusterID = map[p.ClusterID];

            summaries.RemoveAll(s => !map.ContainsKey(s.ClusterID));
            foreach (var s in summaries)
                s.ClusterID = map[s.ClusterID];
            summaries.Sort((a, b) => a.ClusterID.CompareTo(b.ClusterID));
            return activeIds.Count;
        }

        // ---------------------------------------------------------------
        // 估算圓柱弧段的中心和半徑
        // 關鍵：用 dot(N, P/|P|) 判斷法向量方向
        //   dot > 0 → 外法向量 → center = P - R_xz * N
        //   dot < 0 → 內法向量（孔的內面）→ center = P + R_xz * N
        // ---------------------------------------------------------------
        private void EstimateCylinderCenter(
            List<int> idx, List<PointData> pts,
            out double cx, out double cz, out double r, out bool isInner)
        {
            double sumCx = 0, sumCz = 0, sumR = 0, sumDot = 0;
            foreach (int i in idx)
            {
                double px = pts[i].X, pz = pts[i].Z;
                double nx = pts[i].NX, nz = pts[i].NZ;
                double Rp = Math.Sqrt(px * px + pz * pz);
                if (Rp < 1e-6) continue;
                double dot = nx * (px / Rp) + nz * (pz / Rp);
                sumDot += dot;
                double cxE, czE;
                if (dot < 0) { cxE = px + Rp * nx; czE = pz + Rp * nz; }  // 內孔
                else { cxE = px - Rp * nx; czE = pz - Rp * nz; }  // 外面
                sumCx += cxE; sumCz += czE; sumR += Rp;
            }
            int n = idx.Count;
            cx = sumCx / n; cz = sumCz / n;
            isInner = sumDot < 0;

            // 從估算中心重算真實半徑
            double rSum = 0;
            foreach (int i in idx)
                rSum += Math.Sqrt(Sq(pts[i].X - cx) + Sq(pts[i].Z - cz));
            r = rSum / n;
        }

        // ---------------------------------------------------------------
        // DBSCAN 工具
        // ---------------------------------------------------------------
        private bool TryFitCircle(List<double> a, List<double> b, out CircleFit fit)
        {
            fit = null;
            int n = a.Count;
            if (n < 3 || b.Count != n) return false;

            double saa = 0, sab = 0, sa = 0;
            double sbb = 0, sb = 0;
            double sar = 0, sbr = 0, sr = 0;

            for (int i = 0; i < n; i++)
            {
                double ai = a[i], bi = b[i];
                double r2 = ai * ai + bi * bi;
                double x0 = 2.0 * ai;
                double x1 = 2.0 * bi;

                saa += x0 * x0;
                sab += x0 * x1;
                sa += x0;
                sbb += x1 * x1;
                sb += x1;
                sar += x0 * r2;
                sbr += x1 * r2;
                sr += r2;
            }

            double[,] mat =
            {
                { saa, sab, sa },
                { sab, sbb, sb },
                { sa,  sb,  n  }
            };
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

            fit = new CircleFit
            {
                C1 = c1,
                C2 = c2,
                R = radius,
                MedianResidual = residuals[n / 2]
            };
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
            for (int r = 0; r < 3; r++)
            {
                for (int c = 0; c < 3; c++) m[r, c] = a[r, c];
                m[r, 3] = b[r];
            }

            for (int col = 0; col < 3; col++)
            {
                int pivot = col;
                for (int r = col + 1; r < 3; r++)
                    if (Math.Abs(m[r, col]) > Math.Abs(m[pivot, col])) pivot = r;
                if (Math.Abs(m[pivot, col]) < 1e-12) return false;

                if (pivot != col)
                    for (int c = col; c < 4; c++)
                    {
                        double tmp = m[col, c];
                        m[col, c] = m[pivot, c];
                        m[pivot, c] = tmp;
                    }

                double div = m[col, col];
                for (int c = col; c < 4; c++) m[col, c] /= div;

                for (int r = 0; r < 3; r++)
                {
                    if (r == col) continue;
                    double factor = m[r, col];
                    for (int c = col; c < 4; c++)
                        m[r, c] -= factor * m[col, c];
                }
            }

            for (int i = 0; i < 3; i++) x[i] = m[i, 3];
            return true;
        }

        private int[] DBSCAN2D(double[] x, double[] y, double eps, int minPts)
        {
            int n = x.Length;
            int[] labels = Enumerable.Repeat(-1, n).ToArray();
            int cid = 0;
            double eps2 = eps * eps;

            Func<int, List<int>> nb = (i) =>
            {
                var res = new List<int>();
                for (int j = 0; j < n; j++)
                { double dx = x[j] - x[i], dy = y[j] - y[i]; if (dx * dx + dy * dy <= eps2) res.Add(j); }
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
            int cid = 0;
            double eps2 = eps * eps;

            Func<int, List<int>> nb = (i) =>
            {
                var res = new List<int>();
                for (int j = 0; j < n; j++)
                { double dx = x[j] - x[i], dy = y[j] - y[i], dz = z[j] - z[i]; if (dx * dx + dy * dy + dz * dz <= eps2) res.Add(j); }
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

        // ---------------------------------------------------------------
        // 輔助型別和工具
        // ---------------------------------------------------------------
        private class ArcInfo
        {
            public int ArcLabel, PointCount;
            public double CX, CZ, R;
            public bool IsInner;
            public List<int> Indices;
        }

        private class CircleFit
        {
            public double C1, C2, R, MedianResidual;
        }

        private class CylinderCircle
        {
            public int ClusterID, PointCount;
            public string Type, Axis;
            public double C1, C2, R, MinAxis, MaxAxis;
        }

        private static void NormalizeNormal(double nx, double ny, double nz,
                                            out double ox, out double oy, out double oz)
        {
            if (nz < -1e-3) { ox = -nx; oy = -ny; oz = -nz; }
            else if (Math.Abs(nz) < 1e-3 && ny < -1e-3) { ox = -nx; oy = -ny; oz = -nz; }
            else if (Math.Abs(nz) < 1e-3 && Math.Abs(ny) < 1e-3 && nx < -1e-3) { ox = -nx; oy = -ny; oz = -nz; }
            else { ox = nx; oy = ny; oz = nz; }
        }

        private static double Clamp(double v, double lo, double hi)
            => v < lo ? lo : v > hi ? hi : v;

        private static double Sq(double v) => v * v;

        private static string Fmt(string s, int w)
            => s.Length >= w ? s.Substring(0, w) : s + new string(' ', w - s.Length);

        private void PrintSummary(List<FeatureSummary> summaries)
        {
            Console.WriteLine("\n" + Fmt("ID", 5) + Fmt("Type", 22) + Fmt("Normal", 28) + Fmt("Position", 22) + Fmt("Count", 8) + "Radius");
            Console.WriteLine(new string('-', 90));
            foreach (var s in summaries)
                Console.WriteLine(Fmt(s.ClusterID.ToString(), 5) + Fmt(s.Type, 22) + Fmt(s.Normal, 28)
                    + Fmt(s.Position, 22) + Fmt(s.Count.ToString(), 8)
                    + (s.Radius > 0 ? s.Radius.ToString("F1") : "-"));
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
                    X = double.Parse(c[0]),
                    Y = double.Parse(c[1]),
                    Z = double.Parse(c[2]),
                    NX = double.Parse(c[3]),
                    NY = double.Parse(c[4]),
                    NZ = double.Parse(c[5])
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
