# 查驗判準與實測

執行前的預測與證偽條件見 [EXPERIMENT_LOG.md](../EXPERIMENT_LOG.md)。本輪原研究演算法及門檻未改寫。

| 項目 | 判準 | 實測與依據 |
|---|---|---|
| 原研究來源保存 | 複本與固定來源 SHA-256 相同 | 211 個來源檔受保護，逐檔核對 |
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

兩種入口使用相同四個範例，不能合併為更多獨立實驗或準確率。比對證明指定來源、資料及環境的輸出一致，不等同重新驗證全文每個方法敘述、所有舊註解或任意新模型的能力。

初始分類來源各有既有規則，來源版本不同的輸出差異未經內部消融歸因。runtime 比對亦不推定當年使用何者。STL 重取樣、真實掃描及一般 CAD 實體輸出不屬已驗證範圍。
