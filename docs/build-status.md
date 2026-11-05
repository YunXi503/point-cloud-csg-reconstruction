# 建置與執行狀態

## 現行入口

在 Windows x64 的搬移副本，從點雲 CSV 經來源連結 C# 分類器再到 Python 的四個範例全部通過。4 個初始 CSV 與 24 個核心輸出符合歷史 SHA-256。

三個初始分類來源使用 .NET Framework 4.8，盲孔修正版使用 .NET 8。轉接器直接呼叫既有 Execute，不呼叫硬編桌面路徑的 Main，也不設定分類門檻。[來源綁定](../examples/segmentation.json) · [實測](../validation/2026-11-05/relocated-pipeline-results.json)

## 歷史專案

原 csproj 曾實際編譯 9 個通過、0 個編譯失敗，另外 3 個因來源缺件未編譯。這些數量含副本及舊分支，不代表 12 種方法。缺件仍原樣保留，沒有猜測 Program.cs 或借用不同模型的組件身分。[舊專案清單](../provenance/csharp-project-audit.json)

## 環境

Python 3.14.2 重新建立隔離 venv、安裝完整 13 個鎖定套件及 pip check 通過。NumPy 單獨由 2.4.0 改 2.4.1 的前後紀錄保留；目前預設使用後者。完整環境與手動安裝見 [environment.md](environment.md)。

STL／Blender 重新取樣、其他作業系統、任意新模型及 CAD 幾何核心輸出未在本輪驗證。
