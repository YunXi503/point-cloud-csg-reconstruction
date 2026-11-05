# 三項補全後的再次審查

日期：2026-11-05；版本：0.1.3。以 v0.1.2 為前版，先補分工、品質與案例條件，再從招聘閱讀與維護者角度逐項檢視。這是同一執行者使用不同查核準則的審查。

## 招聘閱讀角度

| 查核問題 | 發現與改善 | 依據 |
|---|---|---|
| 作者到底負責哪些工作？ | 依本人確認，明列研究實作、資料、程式、驗證、圖件與論文；老師提供概念與題目方向 | [分工聲明](../provenance/contribution-statement.json)及[成果連結](contributions.md) |
| 首頁能否直接看到品質結果？ | 把個人工作、品質表及方法範圍入口放在大型圖件之前 | [README](../README.md) |
| 「重現相符」是否被當成「重建準確」？ | 品質表引用曲面殘差與相對幾何參考的參數誤差，另保留雜湊重現說明 | [品質定義](results.md)及[逐項來源](../provenance/quality-summary.json) |
| 0.03 mm 附近的數值能否套用其他模型？ | 表題與內文明列四個受控 STL 資料案例、每例點數及固定來源；沒有外推精度主張 | [方法範圍](method-scope.md) |
| 是否有真實失敗或限制？ | 保存 L型板距離 1.5 mm 的未完成紀錄；列明案例面數／方向條件及尚未量測能力 | [歷史敏感度](../evidence/sensitivity-2026-07-31/report.md)與[資料缺口](missing-information.md) |

## 維護者與證據角度

| 查核問題 | 發現與改善 | 依據 |
|---|---|---|
| 最大曲面殘差與候選誤差是否混為同一個量？ | 分別定義統計欄位、參考對象及單位；每例保留造成最大參數誤差的候選與參數 | [品質摘要](results.md) |
| 是否只看門檻欄位名稱而忽略有效條件？ | 階梯狀圓柱 C# 的同名欄位沒有被 IsSimilar 讀取；文件改依有效函式條件說明，並區分 Python 階段 | [方法對照](method-scope.md)；原來源保持不變 |
| 敏感度輸入真的沒有留下雜湊嗎？ | 從原工作區找回 23 份執行 manifest，與當次變體及輸出紀錄核對；剩 1 組失敗執行未留 manifest | [逐次綁定](../provenance/sensitivity-input-bindings.json) |
| 找回的輸入是否與現在的案例都相同？ | 17 組相同；盲孔 6 組用 fdd5c384…，現行核心用 0d69141f…，原樣保留並明列差異 | [逐次綁定](../provenance/sensitivity-input-bindings.json)及[盲孔追溯](../provenance/recovered-blind-input.json) |
| 三項補全是否引入研究程式變更？ | 原有 211 個核心來源、資料、既有輸出、圖件與論文保留；新增 25 份歷史證據也納入來源雜湊保護 | [來源清單](../provenance/file-manifest.csv)及[本輪查核](../validation/2026-11-05/portfolio-completion-audit.json) |
| 原始資料與文件入口是否易讀？ | 原始識別字、數值與 SHA 留在機器可讀資料，連結用途改為中文，首頁提供四個新文件入口 | [結果來源](results.md)與 README |
| 新增的歷史報告會不會被 Git 改換行？ | evidence/ 與 research/、archive/ 同樣停用文字換行轉換，保留來源位元；新撰說明仍使用 LF | [.gitattributes](../.gitattributes)及發布前 checkout 查核 |
| 歷史 JSON 是否可被嚴格解析器直接讀取？ | 找出模型A六份歷史敏感度 manifest 的 NaN 記號，保留原檔並補上欄位位置；品質摘要與輸入綁定使用嚴格 JSON | [解析備註](../provenance/historical-json-notes.json) |

## 完成判準與保留項目

前三項的完成判準為：作者分工有明確確認；四例品質指標可追溯且與表 4.10 相符；四例專屬條件可對照實際程式；未能確認的資料獨立列出。本輪只讀取與整理既有研究結果。

[M1–M3 資料缺口](missing-information.md)持續保留。效能、未知模型、真實掃描及 CAD 幾何核心結果需要各自的量測或研究計畫。完整案例導讀、影片與統一輸出格式仍屬後續工作。

驗證以本輪查核 JSON、封裝工具及對應 GitHub Actions 實際結果為準；歷史敏感度與獨立網格驗證並未因文件更新而重跑。
