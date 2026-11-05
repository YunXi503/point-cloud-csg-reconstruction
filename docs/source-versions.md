# 原始碼與資料版本對照

發布整理版本為 portfolio-2026-11-05，軟體版本 0.1.0。preparation 與 verification 前版封裝及機器可讀歷史紀錄保留供追溯。

## 研究來源

211 個逐位元複製的來源檔列於 [file-manifest.csv](../provenance/file-manifest.csv)。包含原論文工作區、原 VS 工作區，以及從相同專案核對補回的 4 個 AssemblyInfo.cs。研究演算法與研究參數沒有改寫。

目前來源與輸入綁定見 [cases.json](../examples/cases.json) 及 [segmentation.json](../examples/segmentation.json)。初始 C# 分類器按實際產出比對選定來源及 runtime，不由目錄名推定版本。

## 四範例輸出

既有初始分割 CSV 的 Python 路徑重現 24／24 核心輸出。從已提供點雲 CSV 經 C# 再到 Python 的路徑，4 個初始 CSV 與 24／24 核心輸出均相符。兩條路徑在搬移後的乾淨環境查驗，詳細紀錄列於 validation/2026-11-05/。

基本 L型板來源與歷史資料有 298 個標籤差異，改查原有幾何邏輯版才相符；未作內部差異的消融歸因。盲孔同源程式在 .NET Framework 與 .NET 8 的結果不同，本次相符環境為 .NET 8，不推定歷史使用何者。

## 盲孔輸入

原工作區 _fixed.csv 的 fdd5c384… 版本保持原樣。data/recovered/ 的 0d69141f… 檔先由歷史資料的換行序列精確找回，之後也由原點雲與未改寫 C# 程式在 .NET 8 直接重新產生相同位元。[完整來源紀錄](../provenance/recovered-blind-input.json)

這些是輸入位元與輸出重現證據，不將歷史結果找回程序當作新的獨立正確性驗證。

## 論文公開快照

早期索引所記 Word SHA-256：e09079dfb99af92aee5da8257fbbf3d8e1fcaab47bcb61db66d5c4797d498ae3

現存來源 Word SHA-256：6f3a5df703ffe2669d0957d17c253e257a941a6a1f9700cd7a896536883c4b5e

文字快照比對確認有誌謝標點、目錄頁碼、術語及用字調整。公開 PDF 從現存 Word 唯讀副本原樣匯出，沒有冒充舊雜湊版本，也沒有覆寫正式原檔。

公開 PDF：1f867bb8877e0a44207b37386719199ea63beff6778706378e663a0f603ae10c；75 頁；Word oMath 97→97；來源及工作副本雜湊未改變。[版本與勘誤](../paper/README.md)

## 歷史資料

3 個歷史 csproj 缺件保留供追溯，現行來源連結入口不依賴其缺件。Hex Base with Holed 保持獨立歷史資產，不與盲孔模型靜默合併。1 個歷史 JSON 的 NaN 保留原位元並另列解析問題。
