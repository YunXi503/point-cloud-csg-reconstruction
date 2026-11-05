# 發布封裝與公開論文 QA

版本：0.1.6／portfolio-measurements-2026-11-05。原始來源、兩條執行路徑與研究證據邊界見 [查驗紀錄](validation.md)，本輪三項補全的再次審查見 [completion-review.md](completion-review.md)。

## 檔案與程式

原有 211 個核心來源與新增 25 份歷史敏感度證據，再加五份追溯來源，共 241 個來源應與固定 SHA-256 一致；公開 seal 工具先驗證它們再建立全檔清單，verify 工具同時偵測位元變更與未列入的新檔。編譯產物、快取、私人環境、個人知識庫及第三方文獻 PDF 不納入。

新程式與文件使用 LF，原研究與歷史資料保持原位元。已從本地 commit 實際 clone 至含空格與中文的新路徑，設定 core.autocrlf=true，當時全部 289 檔案通過雜湊檢查。新文件中的 49 個本地連結及 268 個文字檔的指定憑證格式掃描也通過，原 Word 雜湊不變。[發布檢查紀錄](../validation/2026-11-05/publication-audit.json)

GitHub Actions 的結果以該次遠端執行紀錄為準，不把新增 CI 設定當成 CI 已執行。

## 論文來源與格式

已優先對照 碩士論文/碩士論文格式-系上格式.pdf，文字輔助檔只作查找。公開快照保留來源版面，並非新做送審格式認證。

Microsoft Word 實際以唯讀副本開啟，來源及副本關閉後 SHA-256 均不變；oMath 前後為 97／97。Word 與 PDF 均 75 頁，全部 A4，沒有文字區塊超出頁面。實測邊界上／下 24.994 mm、左 30.004 mm、右 20.003 mm，符合規範 25／25／30／20 mm 的 Word 量化。

已看過全部 75 頁縮略總覽，並詳檢 PDF 實體第 26、30、40、44、59、75 頁的公式、流程、圖表與文字。表 4.4 的表題及表格均在本文第 34 頁。公開 PDF 獨立渲染未出現解析警告。[匯出](../validation/2026-11-05/thesis-export.json) · [渲染](../validation/2026-11-05/thesis-render-checks.json)

原稿 NIST 名稱勘誤及已辨識的版次差異列於 paper/README.md，未靜默改寫正文。論文保留原著作權，MIT 範圍為程式及新增說明。

## 論文圖庫增補

本輪沿用同一 Word／PDF，完整列出圖 3.1–3.9、圖 4.1–4.13，取出 28 張原位元 PNG 與四張候選表。已查看全部 32 張資產的總覽與模型A CSG 樹、候選表原尺寸，核對來源圖號及連結。候選表另提供直接取自 Word 儲存格的可搜尋文字，保留正文顯示精度。[圖件查驗](../validation/2026-11-05/thesis-figures-audit.json)

## 保留的限制

本輪審查釐清了二元 CSG 圖示與分組式 JSON 的表示差異，修正首頁及架構措辭，未以格式說明宣稱已新增轉換器或 CAD 幾何執行。詳見 [CSG 表示對照](csg-representation.md) 與 [補全審查](portfolio-review.md)。

歷史 3 個 csproj 缺件不強行補造，現行入口另以可核對來源建置。資料與模型未另行宣告新的再利用授權。未將本輪工程查驗宣稱為真實掃描、一般 CAD 輸出或方法優越性證據。

## 本輪缺口追查

[再次審查](gap-followup-review.md)及[查核 JSON](../validation/2026-11-05/gap-followup-audit.json)列出保存來源、敏感度勘誤與密度重算。原 Word、PDF、圖件及程式未變；舊版 QA 及執行紀錄仍保留原版本語境，沒有宣稱已重跑歷史研究實驗。

## 面試審查補強

[面試導讀](interview-guide.md)與[L型板資料流](case-walkthrough.md)只使用現有來源；預檢改動限於工程入口。原 241 份來源與幾何品質結果保留，17 項防護測試及本版兩種重現路徑的結果見[查核](../validation/2026-11-05/interview-review-audit.json)。

## 效能與數值診斷

本輪新增量測工具、解析fixture、原始觀察、統計與圖表。原研究、參數、期望輸出與論文圖件不變；原生峰值計數先驗PID與64 MiB配置探針，排除錯誤啟動器數字。圖表使用實測數據，450 DPI PNG／SVG與來源manifest均保留。[量測審查](measurement-review.md)
