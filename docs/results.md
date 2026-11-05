# 四個案例的重建品質與證據

[專案首頁](../README.md) · [機器可讀結果與來源](../provenance/quality-summary.json) · [論文表 4.10](../paper/thesis-public-snapshot-20261105.pdf)

本頁整理既有研究結果，沒有新增實驗。四個案例各含 10000 個 STL 生成的點雲與法向量樣本，現存結果的殘留點均為 0。這些數字描述指定資料、程式及參考幾何下的結果。

## 品質總表

| 案例 | 幾何特徵面 | 拓樸關係 | 候選單元 | 最大曲面殘差（mm） | 最大參數誤差（mm） |
|---|---:|---:|---:|---:|---:|
| 階梯狀圓柱 | 6 | 6 | 3 | 0.0333 | 0.0329 |
| L型板 | 12 | 24 | 5 | 0.0322 | 0.0322 |
| 模型A | 13 | 26 | 6 | 0.0325 | 0.0323 |
| 盲孔六角座 | 12 | 22 | 3 | 0.0327 | 0.0322 |

數值保留論文表 4.10 的四位小數顯示精度。全部計數與兩項最大誤差都由目前封裝的 CSV／驗證報告重新彙整，與指定 Word 表 4.10 核對一致；原精度、程式／輸入／輸出 SHA 綁定及逐項來源列在 quality-summary.json。

## 指標如何解讀

- 最大曲面殘差：對 FaceSummary 的 FitResidualMax 取最大值，表示點與其擬合面的距離；單位為 mm。
- 最小法向量一致性：對 NormalConsistencyMin 取最小值，為無單位方向一致性指標。
- 最大參數誤差：對所有候選適用的長、寬、高、半徑或深度之已記錄絕對誤差取最大值，參考來自既有 STL／Blender 評估網格建立的獨立幾何資料；單位為 mm。

曲面殘差與參數誤差衡量不同的量。Python 曲面驗收的 1.5 mm／0.93 不能拿來當候選尺寸的容許誤差；候選驗收依各報告的參數容許值。

| 案例 | 最小法向量一致性（CSV 原精度） | 最大參數誤差所在候選／參數 |
|---|---:|---|
| 階梯狀圓柱 | 0.996919826 | SC_U02／Radius |
| L型板 | 0.994515096 | LB_U03／Radius |
| 模型A | 0.996222263 | MA_D01／Radius |
| 盲孔六角座 | 0.997858917 | BH_D01／Radius |

## 研究品質與重現檢查的分工

| 證據 | 目前可確認的內容 | 本輪執行情形 |
|---|---|---|
| 歷史五層驗收報告 | 四例的分割、幾何語義、拓樸、候選及 CSG 推論對照均記錄 PASS | 核對報告、數值及來源綁定；本輪未重跑獨立網格驗證 |
| 輸出重現與 CI | 指定四例的初始輸入及六項核心輸出與已記錄 SHA 相符 | 另見[重現查驗](validation.md)及 Actions |
| 本頁統計 | 由已保存表格取得的計數、最大值及最小值與論文一致 | 本輪重新讀檔彙整並核對 |

這三種證據用途不同。現有結果不作真實掃描、未知零件、一般 CAD 實體輸出或跨模型泛化的驗證。

## 各例來源入口

### 階梯狀圓柱

- [曲面殘差與法向量一致性 CSV](../research/%E7%A2%A9%E5%A3%AB%E8%AB%96%E6%96%87/%E7%AC%AC%E5%9B%9B%E7%AB%A0%E9%A9%97%E8%AD%89%E7%B5%90%E6%9E%9C_260722/Stepped_Cylinder_chapter3_verified_v3/FaceSummary_Stepped_Cylinder_chapter3_verified.csv)
- [拓樸關係 CSV](../research/%E7%A2%A9%E5%A3%AB%E8%AB%96%E6%96%87/%E7%AC%AC%E5%9B%9B%E7%AB%A0%E9%A9%97%E8%AD%89%E7%B5%90%E6%9E%9C_260722/Stepped_Cylinder_chapter3_verified_v3/TopologyEdges_Stepped_Cylinder_chapter3_verified.csv)
- [候選與布林角色 CSV](../research/%E7%A2%A9%E5%A3%AB%E8%AB%96%E6%96%87/%E7%AC%AC%E5%9B%9B%E7%AB%A0%E9%A9%97%E8%AD%89%E7%B5%90%E6%9E%9C_260722/Stepped_Cylinder_chapter3_verified_v3/PrimitiveCandidates_Stepped_Cylinder_chapter3_verified.csv)
- [逐參數誤差紀錄](../research/%E7%A2%A9%E5%A3%AB%E8%AB%96%E6%96%87/%E7%AC%AC%E5%9B%9B%E7%AB%A0%E9%A9%97%E8%AD%89%E7%B5%90%E6%9E%9C_260722/Stepped_Cylinder_chapter3_verified_v3/CandidateMapping_Stepped_Cylinder.csv)
- [歷史獨立參考驗證報告](../research/%E7%A2%A9%E5%A3%AB%E8%AB%96%E6%96%87/%E7%AC%AC%E5%9B%9B%E7%AB%A0%E9%A9%97%E8%AD%89%E7%B5%90%E6%9E%9C_260722/Stepped_Cylinder_chapter3_verified_v3/ValidationAgainstIndependentTruth_Stepped_Cylinder.json)
- [程式、輸入與輸出綁定](../research/%E7%A2%A9%E5%A3%AB%E8%AB%96%E6%96%87/%E7%AC%AC%E5%9B%9B%E7%AB%A0%E9%A9%97%E8%AD%89%E7%B5%90%E6%9E%9C_260722/Stepped_Cylinder_chapter3_verified_v3/MethodInferenceManifest_Stepped_Cylinder_chapter3.json)

### L型板

- [曲面殘差與法向量一致性 CSV](../research/%E7%A2%A9%E5%A3%AB%E8%AB%96%E6%96%87/%E7%AC%AC%E5%9B%9B%E7%AB%A0%E9%A9%97%E8%AD%89%E7%B5%90%E6%9E%9C_260722/L_Bracket_chapter3_verified_v3/FaceSummary_L_Bracket_chapter3_verified.csv)
- [拓樸關係 CSV](../research/%E7%A2%A9%E5%A3%AB%E8%AB%96%E6%96%87/%E7%AC%AC%E5%9B%9B%E7%AB%A0%E9%A9%97%E8%AD%89%E7%B5%90%E6%9E%9C_260722/L_Bracket_chapter3_verified_v3/TopologyEdges_L_Bracket_chapter3_verified.csv)
- [候選與布林角色 CSV](../research/%E7%A2%A9%E5%A3%AB%E8%AB%96%E6%96%87/%E7%AC%AC%E5%9B%9B%E7%AB%A0%E9%A9%97%E8%AD%89%E7%B5%90%E6%9E%9C_260722/L_Bracket_chapter3_verified_v3/PrimitiveCandidates_L_Bracket_chapter3_verified.csv)
- [逐參數誤差紀錄](../research/%E7%A2%A9%E5%A3%AB%E8%AB%96%E6%96%87/%E7%AC%AC%E5%9B%9B%E7%AB%A0%E9%A9%97%E8%AD%89%E7%B5%90%E6%9E%9C_260722/L_Bracket_chapter3_verified_v3/ValidationSummary_L_Bracket_chapter3.json)
- [歷史獨立參考驗證報告](../research/%E7%A2%A9%E5%A3%AB%E8%AB%96%E6%96%87/%E7%AC%AC%E5%9B%9B%E7%AB%A0%E9%A9%97%E8%AD%89%E7%B5%90%E6%9E%9C_260722/L_Bracket_chapter3_verified_v3/ValidationSummary_L_Bracket_chapter3.json)
- [程式、輸入與輸出綁定](../research/%E7%A2%A9%E5%A3%AB%E8%AB%96%E6%96%87/%E7%AC%AC%E5%9B%9B%E7%AB%A0%E9%A9%97%E8%AD%89%E7%B5%90%E6%9E%9C_260722/L_Bracket_chapter3_verified_v3/MethodInferenceManifest_L_Bracket_chapter3.json)

### 模型A

- [曲面殘差與法向量一致性 CSV](../research/%E7%A2%A9%E5%A3%AB%E8%AB%96%E6%96%87/%E7%AC%AC%E5%9B%9B%E7%AB%A0%E9%A9%97%E8%AD%89%E7%B5%90%E6%9E%9C_260724/Model_A_chapter3_verified_v3/FaceSummary_Model_A_chapter3_verified.csv)
- [拓樸關係 CSV](../research/%E7%A2%A9%E5%A3%AB%E8%AB%96%E6%96%87/%E7%AC%AC%E5%9B%9B%E7%AB%A0%E9%A9%97%E8%AD%89%E7%B5%90%E6%9E%9C_260724/Model_A_chapter3_verified_v3/TopologyEdges_Model_A_chapter3_verified.csv)
- [候選與布林角色 CSV](../research/%E7%A2%A9%E5%A3%AB%E8%AB%96%E6%96%87/%E7%AC%AC%E5%9B%9B%E7%AB%A0%E9%A9%97%E8%AD%89%E7%B5%90%E6%9E%9C_260724/Model_A_chapter3_verified_v3/PrimitiveCandidates_Model_A_chapter3_verified.csv)
- [逐參數誤差紀錄](../research/%E7%A2%A9%E5%A3%AB%E8%AB%96%E6%96%87/%E7%AC%AC%E5%9B%9B%E7%AB%A0%E9%A9%97%E8%AD%89%E7%B5%90%E6%9E%9C_260724/Model_A_chapter3_verified_v3/CandidateMapping_Model_A_chapter3.csv)
- [歷史獨立參考驗證報告](../research/%E7%A2%A9%E5%A3%AB%E8%AB%96%E6%96%87/%E7%AC%AC%E5%9B%9B%E7%AB%A0%E9%A9%97%E8%AD%89%E7%B5%90%E6%9E%9C_260724/Model_A_chapter3_verified_v3/ValidationAgainstIndependentTruth_Model_A.json)
- [程式、輸入與輸出綁定](../research/%E7%A2%A9%E5%A3%AB%E8%AB%96%E6%96%87/%E7%AC%AC%E5%9B%9B%E7%AB%A0%E9%A9%97%E8%AD%89%E7%B5%90%E6%9E%9C_260724/Model_A_chapter3_verified_v3/MethodInferenceManifest_Model_A_chapter3.json)

### 盲孔六角座

- [曲面殘差與法向量一致性 CSV](../research/%E7%A2%A9%E5%A3%AB%E8%AB%96%E6%96%87/%E7%AC%AC%E5%9B%9B%E7%AB%A0%E9%A9%97%E8%AD%89%E7%B5%90%E6%9E%9C_260725/Blind_Hole_Hex_Base_chapter3_verified_v3/FaceSummary_Blind_Hole_Hex_Base_chapter3_verified.csv)
- [拓樸關係 CSV](../research/%E7%A2%A9%E5%A3%AB%E8%AB%96%E6%96%87/%E7%AC%AC%E5%9B%9B%E7%AB%A0%E9%A9%97%E8%AD%89%E7%B5%90%E6%9E%9C_260725/Blind_Hole_Hex_Base_chapter3_verified_v3/TopologyEdges_Blind_Hole_Hex_Base_chapter3_verified.csv)
- [候選與布林角色 CSV](../research/%E7%A2%A9%E5%A3%AB%E8%AB%96%E6%96%87/%E7%AC%AC%E5%9B%9B%E7%AB%A0%E9%A9%97%E8%AD%89%E7%B5%90%E6%9E%9C_260725/Blind_Hole_Hex_Base_chapter3_verified_v3/PrimitiveCandidates_Blind_Hole_Hex_Base_chapter3_verified.csv)
- [逐參數誤差紀錄](../research/%E7%A2%A9%E5%A3%AB%E8%AB%96%E6%96%87/%E7%AC%AC%E5%9B%9B%E7%AB%A0%E9%A9%97%E8%AD%89%E7%B5%90%E6%9E%9C_260725/Blind_Hole_Hex_Base_chapter3_verified_v3/CandidateMapping_Blind_Hole_Hex_Base_chapter3.csv)
- [歷史獨立參考驗證報告](../research/%E7%A2%A9%E5%A3%AB%E8%AB%96%E6%96%87/%E7%AC%AC%E5%9B%9B%E7%AB%A0%E9%A9%97%E8%AD%89%E7%B5%90%E6%9E%9C_260725/Blind_Hole_Hex_Base_chapter3_verified_v3/ValidationAgainstIndependentTruth_Blind_Hole_Hex_Base.json)
- [程式、輸入與輸出綁定](../research/%E7%A2%A9%E5%A3%AB%E8%AB%96%E6%96%87/%E7%AC%AC%E5%9B%9B%E7%AB%A0%E9%A9%97%E8%AD%89%E7%B5%90%E6%9E%9C_260725/Blind_Hole_Hex_Base_chapter3_verified_v3/MethodInferenceManifest_Blind_Hole_Hex_Base_chapter3.json)

## 門檻敏感度與未完成案例

留存的 2026-07-31 分析包含四例、兩個因素、每個因素三種設定，共 24 組執行紀錄，23 組完成。L型板在距離門檻 1.5 mm 時得到 28 個面級記錄，未通過既有 12 面條件而停止。此未完成結果保持原樣。

分析的兩個因素為距離 1.5／2.0／2.5 mm 與法向量內積 0.90／0.93／0.96；每次只改其中一項，另一項固定在基準值。這是 Python 推論階段、從既有分割 CSV 開始的歷史分析，沒有重新執行 C# 初始分類。

23 組完成表示程式完成執行；輸出穩定依該紀錄的同因素基準雜湊判定。它們都不等同 23 組正確、23 個獨立模型或真實掃描魯棒性。本輪只收錄並核對歷史報告，未重跑這 24 組。

[原始敏感度報告](../evidence/sensitivity-2026-07-31/report.md) · [原始 JSON 紀錄](../evidence/sensitivity-2026-07-31/sensitivity_results.json)

原摘要 JSON 沒有逐次列出原始輸入 SHA，但本輪從原工作區找回 23 組已完成執行的歷史 MethodInferenceManifest，輸入 SHA、變體程式與輸出雜湊均可對上。[逐次綁定紀錄](../provenance/sensitivity-input-bindings.json)保留來源與核對結果；未完成的 L型板 1.5 mm 執行沒有留下對應 manifest，其輸入雜湊仍列為[待補資訊](missing-information.md)。

其中 17 組完成執行的輸入 SHA 與現行案例綁定相同；盲孔六角座的 6 組敏感度執行使用 fdd5c384… 輸入位元版本，對應本庫保留的原 _fixed.csv。現行品質與重現路徑使用 0d69141f… 的已找回版本。這兩組位元版本分開記錄，敏感度結果依其當時的輸入與基準解讀，不當成現行輸入版本已重新實測的證據。

原方法 manifest 與模型A的六份敏感度 manifest 含非標準 NaN 記號，來源位元保持不變，位置列於[歷史 JSON 解析備註](../provenance/historical-json-notes.json)。本頁品質摘要及逐次綁定另以嚴格 JSON 提供，NaN 欄位不被解讀或填成數值結果。
