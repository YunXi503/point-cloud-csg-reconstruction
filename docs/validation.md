# 查驗判準與證據

[首頁](../README.md) · [文件一致性](documentation-validation.md) · [研究品質](results.md) · [資料缺口](missing-information.md)

輸出回歸、幾何品質與軟體契約是不同層次的證據。公開入口保存原研究來源與參數，使用固定輸入及參考輸出；各版執行報告記錄當時實際結果。[GitHub Actions](https://github.com/YunXi503/point-cloud-csg-reconstruction/actions/workflows/verify.yml)提供每個提交的現行查驗結果。

## 現行檢查範圍

| 項目 | 判準 | 保存證據與限制 |
|---|---|---|
| 原研究來源 | 241份保護來源逐檔SHA-256相符 | [來源清單](../provenance/copied-sources.json)；不可改參考雜湊來接受來源漂移 |
| 整包內容 | 所有列入封裝的檔案與發布manifest相符 | [封裝清單](../provenance/release-manifest.json)與verify-package.mjs；未知檔或內容漂移須報錯 |
| 單元測試 | 65項，失敗數為0 | [v0.1.8報告](../validation/2026-11-06/guard-hardening-tests.json)；17防護、4解析基準、2量測工具、34圓擬合外層／CLI、8重放檢查器 |
| CLI集成重放 | 六份CSV×兩實作，共12項契約檢查 | [v0.1.8報告](../validation/2026-11-06/circle-replay-results.json)；含預期拒絕，參數仍未驗證；與65項單元測試分開計數 |
| 既有分割CSV→Python | 四例各6項核心輸出SHA相符，共24項 | [v0.1.8推論報告](../validation/2026-11-06/guard-hardening-reproduction.json) |
| 點雲CSV→C#→Python | 四個初始CSV及24項核心輸出相符 | [v0.1.8完整路徑報告](../validation/2026-11-06/guard-hardening-pipeline.json)；初始內容比較與位元SHA分欄，保存結果兩者均相符 |

65項為v0.1.8起的單元測試合計，沒有因新增研究導讀增加。歷史v0.1.5／v0.1.6／v0.1.7分別為17／23／51項；CI對目前提交重新執行現行檢查，歷史報告保留其版本意義。

## 研究品質與工程量測

四例各10000點，曲面殘差與候選參數誤差由[品質總表](results.md)及保存CSV／幾何參考報告支持。公開重現入口比對既有輸出，未重新建立獨立網格參考或執行歷史五層幾何驗收。兩條入口使用相同四例，不能合併為八個研究模型或辨識準確率。

[時間與工作集量測](measurements.md)保存四例兩階段各三次，共24次執行，84項初始／核心輸出SHA全符；函式規模量測只涵蓋region_growing。峰值工作集是單程序的Windows原生指標，不是程序樹總記憶體。20項曲面行為及12項圓收斂觀察包含退化與未達原停止條件的結果，詳見[幾何診斷](geometry-diagnostics.md)，不能寫成全部求解成功。

## 環境、論文與歷史來源

- [搬移後推論](../validation/2026-11-05/relocated-inference-results.json)及[完整路徑](../validation/2026-11-05/relocated-pipeline-results.json)：含空格及中文的新目錄中重新安裝13項鎖定套件後查驗。
- [環境單一變動](../validation/2026-11-05/environment-transition.json)：NumPy 2.4.0→2.4.1，其餘版本不變，兩側核心輸出各24項相符。
- [初次來源／runtime未相符紀錄](../validation/2026-11-05/initial-source-binding-attempt.json)及[盲孔輸入追溯](../provenance/recovered-blind-input.json)：區分歷史來源、現行來源及輸入位元版本。
- [論文匯出紀錄](../validation/2026-11-05/thesis-export.json)：當時Word唯讀開啟為75頁，oMath為97；公開PDF為另記雜湊的閱讀快照。[版本說明](../paper/README.md)
- [敏感度勘誤](sensitivity-errata.md)：原標記與保存SHA的差異另列，舊紀錄不回寫；未重跑全部24組敏感度或補造失敗收據。

輸出位元一致只支持指定來源、資料及環境下的回歸，不能代替真實掃描、未知零件泛化、STL重新取樣、文獻優越性或CAD實體布林驗證。小殘差與步長達標也不保證參數準確。
