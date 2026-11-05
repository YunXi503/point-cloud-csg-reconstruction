# 階梯狀圓柱：從分割到 CSG 推論

[回圖庫](README.md) · [專案首頁](../../README.md) · [完整論文 PDF](../../paper/thesis-public-snapshot-20261105.pdf)

閱讀重點：共軸圓柱、端面關係與中央貫穿孔。以下沿用原論文圖號與候選編號，依分割、拓樸、候選單元及 CSG 樹順序閱讀。

## 圖 4.2 階梯狀圓柱驗證後幾何特徵分割結果

![圖 4.2 階梯狀圓柱驗證後幾何特徵分割結果](../../assets/thesis/fig-4-2.png)

[開啟原圖](../../assets/thesis/fig-4-2.png) · 論文正文第 36 頁／PDF 第 47 頁

## 圖 4.3 階梯狀圓柱拓樸關係

(a) 拓樸關係矩陣

![圖 4.3 階梯狀圓柱拓樸關係 (a) 拓樸關係矩陣](../../assets/thesis/fig-4-3a.png)

(b) 拓樸關係空間圖

![圖 4.3 階梯狀圓柱拓樸關係 (b) 拓樸關係空間圖](../../assets/thesis/fig-4-3b.png)

[開啟原圖](../../assets/thesis/fig-4-3a.png) · 論文正文第 37 頁／PDF 第 48 頁

## 表 4.6 階梯狀圓柱候選幾何單元查驗結果

![表 4.6 階梯狀圓柱候選幾何單元查驗結果](../../assets/thesis/table-4-6-candidates.png)

此圖直接由公開 PDF 的表格區域匯出，保留原表題、數值及浮水印。正文第 38 頁／PDF 第 49 頁。

<details>
<summary>檢視表格文字（原論文顯示精度）</summary>

| 候選幾何單元 | 布林角色 | 型別 | 主要尺寸(mm) |
|---|---|---|---|
| 下階圓柱 SC_U01 | 聯集 | 圓柱 | 半徑 39.968、深度 40.000 |
| 上階圓柱 SC_U02 | 聯集 | 圓柱 | 半徑 24.967、深度 60.000 |
| 貫穿孔 SC_D01 | 差集 | 圓柱孔 | 半徑 14.970、深度 100.000 |

</details>


## 圖 4.4 階梯狀圓柱階層式 CSG 推論

![圖 4.4 階梯狀圓柱階層式 CSG 推論](../../assets/thesis/fig-4-4.png)

[開啟原圖](../../assets/thesis/fig-4-4.png) · 論文正文第 38 頁／PDF 第 49 頁

CSG 樹中的葉節點呈現候選單元，∪ 與 − 分別表示聯集與差集；圖示呈現論文中的推論與建構關係。軟體輸出範圍為可追溯的 CSG 推論表示。

## 對照程式輸出

- [幾何特徵面 CSV](../../research/%E7%A2%A9%E5%A3%AB%E8%AB%96%E6%96%87/%E7%AC%AC%E5%9B%9B%E7%AB%A0%E9%A9%97%E8%AD%89%E7%B5%90%E6%9E%9C_260722/Stepped_Cylinder_chapter3_verified_v3/FaceSummary_Stepped_Cylinder_chapter3_verified.csv)
- [拓樸關係 CSV](../../research/%E7%A2%A9%E5%A3%AB%E8%AB%96%E6%96%87/%E7%AC%AC%E5%9B%9B%E7%AB%A0%E9%A9%97%E8%AD%89%E7%B5%90%E6%9E%9C_260722/Stepped_Cylinder_chapter3_verified_v3/TopologyEdges_Stepped_Cylinder_chapter3_verified.csv)
- [候選幾何單元 CSV](../../research/%E7%A2%A9%E5%A3%AB%E8%AB%96%E6%96%87/%E7%AC%AC%E5%9B%9B%E7%AB%A0%E9%A9%97%E8%AD%89%E7%B5%90%E6%9E%9C_260722/Stepped_Cylinder_chapter3_verified_v3/PrimitiveCandidates_Stepped_Cylinder_chapter3_verified.csv)
- [CSG 樹 JSON](../../research/%E7%A2%A9%E5%A3%AB%E8%AB%96%E6%96%87/%E7%AC%AC%E5%9B%9B%E7%AB%A0%E9%A9%97%E8%AD%89%E7%B5%90%E6%9E%9C_260722/Stepped_Cylinder_chapter3_verified_v3/CSGTree_Stepped_Cylinder_chapter3_verified.json)

論文表格保留正文的顯示精度；CSV 保留既有輸出欄位及數值。圖表公開不新增研究驗證或跨模型泛化主張。
