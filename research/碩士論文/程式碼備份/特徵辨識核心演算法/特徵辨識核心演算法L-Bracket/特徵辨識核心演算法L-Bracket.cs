using System;
using System.Collections.Generic;
using System.IO;
using System.Globalization;
using System.Linq;

namespace 特徵辨識核心演算法L_Bracket
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
        // 門檻要夠狠，才能切得乾淨
        public double DistanceThreshold = 2.0;
        public double NormalThreshold = 0.96; // 再次放寬！讓小圓角的點能連成一塊

        private bool IsSimilar(PointData a, PointData b)
        {
            double dist = Math.Sqrt(Math.Pow(a.X - b.X, 2) + Math.Pow(a.Y - b.Y, 2) + Math.Pow(a.Z - b.Z, 2));
            if (dist > 3.0) return false; // 階梯圓柱較簡單，門檻放寬一點

            double dot = Math.Abs((a.NX * b.NX) + (a.NY * b.NY) + (a.NZ * b.NZ));
            // 0.96 容許約 16 度的偏差，這對偵測小半徑圓弧非常重要
            if (dot < 0.96) return false;

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

                // 核心修改：將雜訊過濾門檻調低到 50 點
                // 因為小圓角的表面積小，點數本來就少
                if (count > 50)
                {
                    Console.WriteLine($"偵測到特徵 ID:{currentID}，點數：{count}");
                    currentID++;
                }
            }

            Console.WriteLine("\n--- 幾何特徵提取報告 (L-Bracket 修正版) ---");

            for (int id = 0; id < currentID; id++)
            {
                var clusterPoints = points.FindAll(p => p.ClusterID == id);
                if (clusterPoints.Count < 100) continue;

                double avgNZ = clusterPoints.Average(p => Math.Abs(p.NZ));

                // 1. 判斷水平平面 (頂/底面)
                if (avgNZ > 0.98)
                {
                    Console.WriteLine($"ID {id}: 【水平平面】，高度 Z = {clusterPoints.Average(p => p.Z):F2}");
                }
                // 2. 處理垂直區域 (側面)
                else if (avgNZ < 0.1)
                {
                    // --- 核心改進：檢查法向量方向是否「單一」 ---
                    // 取第一點為基準，看其他點的法向量是否跟它幾乎一樣
                    var refN = clusterPoints[0];
                    double normalVariation = clusterPoints.Average(p =>
                        1.0 - Math.Abs(p.NX * refN.NX + p.NY * refN.NY + p.NZ * refN.NZ));

                    // 如果法向量幾乎沒變 (偏差 < 0.001)，代表它是平的
                    if (normalVariation < 0.001)
                    {
                        Console.WriteLine($"ID {id}: 【垂直平面 (側面)】");
                    }
                    else
                    {
                        // 只有當法向量在變動時，才去檢查是否為圓柱
                        double centerX = clusterPoints.Average(p => p.X);
                        double centerY = clusterPoints.Average(p => p.Y);
                        var distances = clusterPoints.Select(p => Math.Sqrt(Math.Pow(p.X - centerX, 2) + Math.Pow(p.Y - centerY, 2))).ToList();
                        double avgR = distances.Average();
                        double stdDevR = Math.Sqrt(distances.Average(d => Math.Pow(d - avgR, 2)));

                        // 調整 stdDevR 門檻，圓角半徑小，偏差容許度要調到 1.5 左右
                        if (normalVariation > 0.05 && stdDevR < 1.5)
                        {
                            Console.WriteLine($"ID {id}: 【偵測成功：圓角/圓柱特徵】，R = {avgR:F2} mm");
                        }
                        else
                        {
                            Console.WriteLine($"ID {id}: 【垂直平面 (轉角或雜訊)】");
                        }
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