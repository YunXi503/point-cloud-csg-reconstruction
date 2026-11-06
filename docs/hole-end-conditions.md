# 貫穿孔與盲孔：端面關係、支撐範圍與深度

[研究總覽](research-overview.md) · [拓樸規則](topology-rules.md) · [L型板既有導讀](case-walkthrough.md) · [資料與SHA](../provenance/research-guides-evidence.json)

本頁對照定稿3.8、4.4、4.6及4.7.3節，以及現存兩份案例程式與CSV。端面關係表示平面和圓柱側面的方向及有限取樣距離符合規則；開口與封底的判別還要讀該端面的支撐形狀。兩條EndCap關係本身不代表孔必然貫穿或封閉。

## 先確認是孔洞候選，再看端部

兩例均由圓柱徑向法向量的一致性區分內外側，並保留來源面及兩個端面關係。L型板的[semantic_roles](../research/tools/infer_lbracket_chapter3_method.py#L260)依軸向與內外方向指定base_hole等案例角色，再於[build_candidates](../research/tools/infer_lbracket_chapter3_method.py#L391)映射為孔洞／Difference候選。盲孔例的[build_candidates](../research/tools/infer_blind_hole_hex_base_chapter3_method.py#L225)對內側孔洞另外呼叫classify_hole_end_condition。

**L型板程式沒有呼叫盲孔案例的端部分類函式。** 論文有共通的孔洞／端面解釋，不代表兩個實作都執行同一段端部分類程式。

| 保存的候選 | 來源面與角色 | EndCap面組 | 半徑／深度（mm，CSV原精度） |
|---|---|---|---|
| LB_D01，BasePlateHole，Difference | RelatedClusters=0;2;9；9=base_hole、0=base_bottom、2=base_top | 0–9、2–9 | Radius=7.970796954；Depth=4.999999993 |
| BH_D01，BlindHole，Difference | RelatedClusters=1;10;11；1=blind_hole_side、10=ring_top、11=blind_hole_floor | 1–10、1–11 | Radius=22.467640162；Depth=50.000000000 |

來源：[L型板候選CSV](../research/碩士論文/第四章驗證結果_260722/L_Bracket_chapter3_verified_v3/PrimitiveCandidates_L_Bracket_chapter3_verified.csv)、[盲孔候選CSV](../research/碩士論文/第四章驗證結果_260725/Blind_Hole_Hex_Base_chapter3_verified_v3/PrimitiveCandidates_Blind_Hole_Hex_Base_chapter3_verified.csv)。FaceSummary、TopologyEdges及逐筆欄位見[證據JSON](../provenance/research-guides-evidence.json)。

## 盲孔案例實際如何判別端部

[radial_extent](../research/tools/infer_blind_hole_hex_base_chapter3_method.py#L56)將每個端面的取樣點移到圓柱軸線座標，去掉軸向分量，再取徑向距離的最小值rho_min及最大值rho_max。[classify_hole_end_condition](../research/tools/infer_blind_hole_hex_base_chapter3_method.py#L195)沿用原擬合容許值1.5 mm，將以下兩個條件同時成立的端面計作封底：

```text
rho_min <= 1.5 mm
rho_max <= cylinder_radius + 1.5 mm
```

| 兩個端面中符合封底條件的數目 | 原函式的回傳／處理 |
|---:|---|
| 0 | ThroughHole；函式文字解釋為兩端為環域開口 |
| 1 | BlindHole；一端為孔截面內部圓盤 |
| 2 | 拋出ValueError，兩端封底不在該實作處理範圍 |

這是有限取樣徑向極值的操作性代理。條件沒有計算連續邊界、圓盤填充率或角度覆蓋，故不能只憑它證明任意點集「完整覆蓋圓盤」。0端封底的分支也沒有額外證明任意形狀必為完整環域開口。上述限制不改寫原函式的回傳名稱。

## BH_D01的現存資料讀回

以下用已保存Result座標及FaceSummary顯示精度的軸線／中心／半徑唯讀重算，非原執行時完整精度的rho收據，也沒有重新擬合或重跑推論。原候選半徑加原容許值為23.967640162 mm。

| 端面 | 點數 | rho_min（mm） | rho_max（mm） | 依原徑向條件讀回 |
|---|---:|---:|---:|---|
| 10：環台頂面 | 548 | 22.493706082 | 34.960874662 | 不計封底 |
| 11：盲孔底面 | 395 | 1.377034407 | 22.393477547 | 計為封底 |

只有一端符合，與保存的BH_D01之BlindHole及InferenceRule一致。底面最小取樣徑向距離不是零，說明此規則使用原容許值及有限取樣；沒有替資料補一個位於圓心的點。

## 深度取自哪裡

| 實作 | 實際計算方式 | 現存資料對照 |
|---|---|---|
| L型板 | 兩個端面擬合中心沿圓柱軸投影，取差的絕對值 | LB_D01的兩個中心軸向座標為0與4.999999993，對應保存Depth |
| 盲孔六角座 | 兩個端面各自的點沿軸投影取中位數，排序後作差 | 以保存軸線讀回10／11面中位數為75與25 mm，對應Depth=50 mm |

盲孔深度不是整個零件高度，也不是只取圓柱側面樣本的軸向最大減最小。FaceSummary中的側面AxisMin／AxisMax是另一組量，不應代填為候選Depth。

## 證據邊界與待補資料

目前有L型板孔洞及BH_D01的保存結果、角色與程式分支。尚未找到用這個盲孔端部分類器單獨驗證0端封底、2端封底、局部缺漏或不完整圓盤覆蓋的專屬執行紀錄；不能用L型板結果代替那些分支測試。四例仍為STL生成的受控資料，原容許值不當作任意尺度／掃描資料的通用判準。

[盲孔原論文圖件](figures/blind-hole-hex-base.md)可對照幾何外觀；[品質報告](results.md)另查尺寸誤差。圖像外觀、RuleStatus=PASS與獨立參數參考各有用途。
