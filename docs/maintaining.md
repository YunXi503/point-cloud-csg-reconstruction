# 維護與發布

依變動範圍執行相關檢查。完整查驗入口如下：

```powershell
./.venv/Scripts/python.exe -m unittest discover -s tests -v
./.venv/Scripts/python.exe tools/verify-circle-replays.py --output-dir runs/new-circle-replays
./.venv/Scripts/python.exe tools/verify-reproduction.py --case all --output-dir runs/new-inference-check
./.venv/Scripts/python.exe tools/run-from-point-cloud.py --case all --output-dir runs/new-pipeline-check
```

只改說明文字不必重跑研究程式；執行路徑或環境改動則按影響範圍重查。圖件用 tools/render-gallery.py 產生並視覺檢查，保留來源雜湊。

## 更新封裝清單

```powershell
node tools/seal-release.mjs
node tools/verify-package.mjs
```

seal-release 只記錄位元，不批准方法變更。已記錄研究來源或輸入被修改時，它拒絕重新封裝，不能用更新清單掩蓋資料漂移。方法變更先確認研究計畫，保留上一版及實驗紀錄，再明確處理來源版本。

## Git 與自動查驗

.gitattributes 保留研究來源、CSV 與歷史檔的位元，新程式及說明使用 LF，避免 Windows 換行轉換破壞雜湊。

CI 使用只讀 repository 權限，執行步驟固定到已核對 commit SHA，安裝完整 lock，執行防護測試與兩種重現路徑，保存結果及日誌。遠端成敗以 Actions 的實際執行為準。

私人環境、快取、編譯產物及 runs/ 不納入 Git。公開論文另有版次及著作權範圍，不屬程式 MIT 授權。

## 本地推論依賴

研究入口若新增或改變本地匯入，須同步審查 provenance/inference-dependencies.json 與 cases.json，檢查閉包及來源 SHA；不可直接更新綁定讓未知變更通過。兩個入口都會保存 inference_programs 預檢結果。負向測試以軟體 fixture 驗證停止行為，數值研究測試需另依方法契約建立。

## 二維圓擬合契約

可選外層的兩份原始碼有固定SHA與AST停止條件核對，不能為讓新來源通過而靜默更新綁定。[事前計畫](geometry-guard-plan.md)與[契約](geometry-guard.md)說明數值秩、停止觀察及參數未驗證狀態。改動這些政策時，跑tests/test_geometry_guard.py及六份範例兩實作的重放；缺步長不可猜收斂，小殘差不可改成準確度通過。

v0.1.8以tools/verify-circle-replays.py執行12項CLI重放，已納入CI並保存報告／日誌。每份報告有共同欄位；來源清單格式錯誤或重複路徑須結構化拒絕，CSV讀取失敗不得捏造輸入SHA。tests/test_circle_replays.py以軟體fixture檢查重放器能抓出不利狀態被誤判或欄位錯誤，不能只執行工具而不檢查結果。

v0.1.6量測JSON、其事前協定、量測／彙整／製圖工具及圖件均保留原SHA；新增外層結果另存，不用新資料覆蓋原不利觀察。若要接入四案例或修改研究方法，先另立計畫及影響評估。
