using System;
using System.Collections.Generic;
using System.IO;
using System.Globalization;
using System.Linq;

namespace PointCloudReconstruction
{
    // 1. 定義資料結構
    public class PointData
    {
        public double X, Y, Z, NX, NY, NZ;
        public int ClusterID = -1;
    }

    class Program
    {
        static void Main(string[] args)
        {
            // === 請修改這裡的檔案路徑 ===
            string inputPath = @"C:\Users\Admin\Desktop\云析論文\零件\Hex Base with Holed點雲.csv";
            string outputPath = @"C:\Users\Admin\Desktop\云析論文\零件\Result_Hex Base with Holed.csv";

            FeatureClassifier classifier = new FeatureClassifier();
            classifier.Execute(inputPath, outputPath);

            Console.WriteLine("\n按下任意鍵結束...");
            Console.ReadKey();
        }
    }

    public class FeatureClassifier
    {
        // 門檻要夠狠，才能切得乾淨
        public double DistanceThreshold = 1.5; // 針對 20.0 密度的點雲，1.5mm 最剛好
        public double NormalThreshold = 0.999; // 法向量夾角要在 2.5 度以內

        private bool IsSimilar(PointData a, PointData b)
        {
            double dist = Math.Sqrt(Math.Pow(a.X - b.X, 2) + Math.Pow(a.Y - b.Y, 2) + Math.Pow(a.Z - b.Z, 2));
            if (dist > 3.0) return false; // 階梯圓柱較簡單，門檻放寬一點

            // 情況 A：平面辨識 (法向量幾乎一樣)
            double dot = Math.Abs((a.NX * b.NX) + (a.NY * b.NY) + (a.NZ * b.NZ));
            if (dot > 0.9999) return true;

            // 情況 B：垂直圓柱辨識 (關鍵！)
            // 如果兩點的 NZ 都是 0 (代表都在垂直面上)，且距離夠近，就歸為同一群
            if (Math.Abs(a.NZ) < 0.05 && Math.Abs(b.NZ) < 0.05)
            {
                return true;
            }

            return false;
        }

        public void Execute(string inputPath, string outputPath)
        {
            if (!File.Exists(inputPath)) return;

            List<PointData> points = new List<PointData>();
            string[] lines = File.ReadAllLines(inputPath);

            // 使用每一筆點雲資料
            for (int i = 1; i < lines.Length; i += 1)
            {
                string[] cols = lines[i].Split(',');
                if (cols.Length < 6) continue;
                points.Add(new PointData
                {
                    X = double.Parse(cols[0]),
                    Y = double.Parse(cols[1]),
                    Z = double.Parse(cols[2]),
                    NX = double.Parse(cols[3]),
                    NY = double.Parse(cols[4]),
                    NZ = double.Parse(cols[5])
                });
            }

            int currentID = 0;
            for (int i = 0; i < points.Count; i++)
            {
                if (points[i].ClusterID != -1) continue;

                Stack<PointData> stack = new Stack<PointData>();
                stack.Push(points[i]);
                points[i].ClusterID = currentID;

                int count = 0;
                while (stack.Count > 0)
                {
                    PointData p = stack.Pop();
                    count++;

                    foreach (var target in points)
                    {
                        if (target.ClusterID != -1) continue;
                        if (IsSimilar(p, target))
                        {
                            target.ClusterID = currentID;
                            stack.Push(target);
                        }
                    }
                }

                // 過濾雜訊：特徵點數必須 > 150 點才記錄
                if (count > 150)
                {
                    Console.WriteLine($"偵測到特徵 ID:{currentID}，點數：{count}");
                    currentID++;
                }
            }

            // --- 新增：幾何特徵提取邏輯 ---
            Console.WriteLine("\n--- 幾何特徵提取報告 ---");

            for (int id = 0; id < currentID; id++)
            {
                var clusterPoints = points.FindAll(p => p.ClusterID == id);
                if (clusterPoints.Count == 0) continue;

                // 判斷是否為平面 (法向量 Z 軸佔比很高)
                double avgNZ = clusterPoints.Average(p => Math.Abs(p.NZ));
                if (avgNZ > 0.99)
                {
                    double avgZ = clusterPoints.Average(p => p.Z);
                    Console.WriteLine($"ID {id}: 偵測為【平面】，高度 Z = {avgZ:F2} mm");
                }
                // 判斷是否為垂直圓柱 (法向量 Z 軸幾乎為 0)
                else if (avgNZ < 0.05)
                {
                    // 算出 XY 中心點 (圓心)
                    double centerX = clusterPoints.Average(p => p.X);
                    double centerY = clusterPoints.Average(p => p.Y);
                    // 算出點到圓心的平均距離 (半徑 R)
                    double radius = clusterPoints.Average(p => Math.Sqrt(Math.Pow(p.X - centerX, 2) + Math.Pow(p.Y - centerY, 2)));

                    Console.WriteLine($"ID {id}: 偵測為【圓柱面】");
                    Console.WriteLine($"   -> 預估圓心位置: ({centerX:F2}, {centerY:F2})");
                    Console.WriteLine($"   -> 預估半徑 R: {radius:F2} mm");
                }
            }

            using (StreamWriter sw = new StreamWriter(outputPath))
            {
                sw.WriteLine("X,Y,Z,NX,NY,NZ,ClusterID");
                foreach (var p in points)
                    sw.WriteLine($"{p.X},{p.Y},{p.Z},{p.NX},{p.NY},{p.NZ},{p.ClusterID}");
            }
            Console.WriteLine($"\n完成！偵測到 {currentID} 個特徵。");
        }
    }
}