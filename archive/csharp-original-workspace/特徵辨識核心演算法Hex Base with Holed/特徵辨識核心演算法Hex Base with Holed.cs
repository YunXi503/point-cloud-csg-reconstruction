using System;
using System.Collections.Generic;
using System.IO;
using System.Globalization;
using System.Linq;

namespace 特徵辨識核心演算法Hex_Base_with_Holed
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
        public double NormalThreshold = 0.9999; // 法向量夾角要在 0.8 度以內

        private bool IsSimilar(PointData a, PointData b)
        {
            double dist = Math.Sqrt(Math.Pow(a.X - b.X, 2) + Math.Pow(a.Y - b.Y, 2) + Math.Pow(a.Z - b.Z, 2));
            if (dist > 3.0) return false; // 階梯圓柱較簡單，門檻放寬一點

            // 法向量內積：
            // 如果設為 0.9999，夾角只要超過 0.8 度就會被切斷。
            // 這樣六角形的轉角(60度或120度)就會被精準切開，變成 6 個獨立 ID。
            double dot = Math.Abs((a.NX * b.NX) + (a.NY * b.NY) + (a.NZ * b.NZ));
            if (dot < 0.9999) return false;

            return true;
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

            Console.WriteLine("\n--- 幾何特徵提取報告 (半徑修正版) ---");

            for (int id = 0; id < currentID; id++)
            {
                var clusterPoints = points.FindAll(p => p.ClusterID == id);
                if (clusterPoints.Count < 200) continue; // 點數太少跳過

                double avgNZ = clusterPoints.Average(p => Math.Abs(p.NZ));

                // 1. 水平平面
                if (avgNZ > 0.98)
                {
                    Console.WriteLine($"ID {id}: 【水平平面】，高度 Z = {clusterPoints.Average(p => p.Z):F2}");
                }
                // 2. 垂直特徵 (NZ < 0.1)
                else if (avgNZ < 0.1)
                {
                    double centerX = clusterPoints.Average(p => p.X);
                    double centerY = clusterPoints.Average(p => p.Y);

                    // 計算標準差：如果真的是圓柱，點到圓心的距離應該非常一致
                    var distances = clusterPoints.Select(p => Math.Sqrt(Math.Pow(p.X - centerX, 2) + Math.Pow(p.Y - centerY, 2))).ToList();
                    double avgR = distances.Average();
                    double stdDevR = Math.Sqrt(distances.Average(d => Math.Pow(d - avgR, 2)));

                    // 關鍵判斷：
                    // 如果標準差 stdDevR 很小 (例如 < 0.5)，代表是圓柱
                    // 如果標準差很大 (例如六角形)，代表是平面側面
                    if (stdDevR < 0.5)
                    {
                        Console.WriteLine($"ID {id}: 【偵測成功：圓柱面 (孔)】");
                        Console.WriteLine($"   -> 圓心: ({centerX:F2}, {centerY:F2}), 半徑 R = {avgR:F2} mm");
                    }
                    else
                    {
                        Console.WriteLine($"ID {id}: 【偵測為：垂直平面 (六角側面)】，標準差={stdDevR:F2}");
                    }
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