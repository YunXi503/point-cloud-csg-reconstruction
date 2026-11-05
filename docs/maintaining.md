# 維護與發布

依變動範圍執行相關檢查。完整查驗入口如下：

```powershell
./.venv/Scripts/python.exe -m unittest discover -s tests -v
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
