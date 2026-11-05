# 查驗判準與實測

執行前的預測與證偽條件見 [EXPERIMENT_LOG.md](../EXPERIMENT_LOG.md)。本輪原研究演算法及門檻未改寫。

| 項目 | 判準 | 實測與依據 |
|---|---|---|
| 原研究來源保存 | 複本與固定來源 SHA-256 相同 | 原有 211 個核心來源與新增 25 份歷史敏感度證據，加上本輪五份追溯來源，共 241 檔受保護 |
| 既有分割 CSV→Python | 四範例各 6 項核心 SHA-256 相符 | 搬移環境 24／24，相符紀錄可逐檔查對 |
| 點雲 CSV→C#→Python | 初始 CSV 與所有核心輸出相符 | 搬移環境 4 個初始檔＋24／24 核心輸出相符 |
| NumPy 修補變更 | 只改一個套件，核心輸出不變 | 僅 2.4.0→2.4.1，其餘版本不變，各 24 項相符 |
| 乾淨安裝 | 不繼承系統套件，完整 lock 安裝成功 | 新目錄新建 venv，13 項套件及 pip check 通過 |
| 錯誤偵測 | 漂移、越界、未知檔及覆寫須被阻擋 | 11 個軟體防護測試通過，不用研究假數據 |
| 論文快照 | 實際 Word 唯讀開啟，來源及公式保留 | 75 頁，oMath 97→97，來源及副本雜湊未改變 |

## 原始紀錄

- [搬移後 Python 推論](../validation/2026-11-05/relocated-inference-results.json)
- [搬移後點雲至推論](../validation/2026-11-05/relocated-pipeline-results.json)
- [環境單一變動](../validation/2026-11-05/environment-transition.json)
- [初次未相符來源／runtime](../validation/2026-11-05/initial-source-binding-attempt.json)
- [盲孔輸入來源及直接重生證據](../provenance/recovered-blind-input.json)
- [論文匯出](../validation/2026-11-05/thesis-export.json)

## 結論範圍

v0.1.3 的[品質摘要](results.md)另以既有 CSV／驗證報告彙整四例指標，與指定 Word 表 4.10 核對。這是現存資料的統計與來源查核，歷史敏感度及獨立網格驗證沒有在本輪重新執行。

兩種入口使用相同四個範例，不能合併為更多獨立實驗或準確率。比對證明指定來源、資料及環境的輸出一致，不等同重新驗證全文每個方法敘述、所有舊註解或任意新模型的能力。

初始分類來源各有既有規則，來源版本不同的輸出差異未經內部消融歸因。runtime 比對亦不推定當年使用何者。STL 重取樣、真實掃描及一般 CAD 實體輸出不屬已驗證範圍。

## v0.1.4 缺口追查

只讀比對 138 個歷史輸出及 120 個變體來源；敏感度標記的五筆差異另列勘誤，基準與原檔不變。現有密度資料的 32 項描述值與三個角度重算一致，不是新增取樣或重建實驗。[本輪查核](../validation/2026-11-05/gap-followup-audit.json) · [再次審查](gap-followup-review.md)

## v0.1.5 面試官角度補強

本輪補上兩個工程入口的 Python 本地依賴來源預檢，17 項防護測試在 Python 3.14.2 通過。重新驗證既有四例，兩種入口的 24 個核心輸出均相符，完整路徑的四個初始 CSV 亦逐位元相同；這是入口改動的回歸查驗，沒有新增研究方法或案例。

[工程查核](../validation/2026-11-05/interview-review-audit.json) · [既有分割 CSV 路徑](../validation/2026-11-05/interview-inference-results.json) · [點雲完整路徑](../validation/2026-11-05/interview-pipeline-results.json) · [面試導讀](interview-guide.md)

## v0.1.6 工程實測

23項單元測試（17防護、4解析幾何、2量測工具）；四例兩階段各三次，共24次，84項輸出SHA全符；region_growing四種N各三次；20項曲面與12項圓收斂行為觀察。後者不是全部成功的數值測試。原241份來源保持不變。[實測](measurements.md) · [診斷](geometry-diagnostics.md) · [再次審查](measurement-review.md)
