# 共通方法、案例條件與支援範圍

[專案首頁](../README.md) · [品質證據](results.md) · [原始碼架構](architecture.md) · [資料缺口](missing-information.md)

現行實作由可共用的幾何處理、各案例的語義角色規則，以及歷史分類器共同構成。公開入口重現四個指定案例；下表列出目前程式實際接受的條件。

## 共通處理與輸入契約

| 部分 | 可在程式檢視的處理 | 範圍 |
|---|---|---|
| 輸入 | 點位置 X／Y／Z、法向量 NX／NY／NZ，Python 另讀 ClusterID；各 Python 入口要求 10000 列 | 模型A另要求 FeatureType 欄位；所有入口仍綁定指定範例與來源雜湊 |
| 面型查驗 | 平面／圓柱擬合、最大殘差及最小法向量一致性 | 自由曲面、圓角、轉接曲面不在本輪驗證範圍 |
| 拓樸 | 有限取樣支撐距離、平面法向量及圓柱軸向關係 | 記錄一般相鄰、正交相鄰、端面關係 |
| 候選單元 | 由語義角色、來源群集、面關係與尺寸推得候選，保留 BooleanType | 候選組成含案例專屬規則 |
| CSG | 聯集候選先組成基體，再依序記錄差集候選 | 三例 JSON 為分組格式，盲孔例為巢狀二元格式，見[表示契約](csg-representation.md) |

各例對平面碎片、圓柱及點歸屬的處理不完全相同。例如 L型板會重新做區域成長與曲面合併，模型A另有平面碎片與混合圓柱的處理。共通目標與輸出層級不代表四支程式的每個步驟完全相同。

## 案例專屬條件

| 案例 | 語義階段的必要組成 | 方向與角色條件 | 不符合時 |
|---|---|---|---|
| 階梯狀圓柱 | 3 平面＋3 圓柱面 | 一個內側圓柱、兩個外側圓柱；依共同軸向排序平面及外圓柱 | 面數或內外角色無法唯一決定時拋出錯誤 |
| L型板 | 最終 12 面；9 個平面角色與 3 個圓柱角色 | 平面依座標軸、符號及位置分組；圓柱依 Z／Y 軸及內外方向判斷 | 角色數、圓柱角色或最終面數不符時停止 |
| 模型A | 9 平面＋4 圓柱面 | 預期 X／Y 軸各一組內外圓柱，平面角色依指定軸向、位置與斜面條件配置 | 面數、軸向分組或內外角色不符時停止 |
| 盲孔六角座 | 10 平面＋2 圓柱面 | 4 個水平面與6個側面；一內一外圓柱，封底、肩面及頂面須符合徑向範圍與軸向次序 | 面數、端部或次序無法確認時停止；兩端均封底的孔不在處理範圍 |

這些條件由目前案例程式明確指定；符合面數本身仍不足以通過完整的幾何、拓樸及候選驗收。任意新零件、整體旋轉或尺度改變的支援能力尚未在這四例以外驗證。

## Python 方法參數與初始 C# 分類器分開閱讀

四例方法紀錄中的 Python 參數包括：距離門檻 2.0 mm、法向量內積門檻 0.93、曲面最大殘差 1.5 mm；拓樸使用一般距離 2.0 mm、正交內積小於 0.2，端面距離不超過 5.0 mm 且軸向內積大於 0.95。這些是指定受控資料的記錄值。

下表摘錄實際連結的初始 C# 來源，不能把上述 Python 參數視為所有 C# 分類器的共同設定：

| 初始 C# 來源 | 實際程式條件節錄 |
|---|---|
| 階梯狀圓柱 | IsSimilar 使用距離不超過 3.0；其後以絕對法向量內積大於 0.9999，或兩點的絕對 NZ 均小於 0.05 接受相鄰。類別另宣告 DistanceThreshold=1.5、NormalThreshold=0.999，但 IsSimilar 沒有讀取這兩個欄位 |
| L型板幾何邏輯版 | IsSimilar 讀取 DistanceThreshold=2.0、NormalThreshold=0.93 |
| 模型A | 平面法向量分箱 8 度、距離分箱 1.5 mm；圓柱弧段分群在 XZ／YZ 空間使用不同條件，包含 eps 5.0／3.0 |
| 盲孔六角座修正版 | 平面法向量分箱 8 度、距離分箱 1.5 mm；圓柱沿 Z 軸，XY 弧段分群 eps=5.0 |

這些節錄用於說明來源及階段差異，不是完整參數設定檔。程式內未使用的欄位、舊註解與有效條件須分開檢視；本輪未調整任何條件。[公式到函式對照](method-traceability.md)已補上目前可確認的關係與差異；完整歷史決策資料仍有待補，見[資料缺口](missing-information.md)。門檻的現存尺度依據另見[密度與參數](parameter-evidence.md)。

## 目前公開入口

較短入口從已記錄的初始分割 CSV 執行 Python；完整程式路徑從已提供的點雲／法向量 CSV 呼叫 C#，再接 Python。STL／Blender 重新取樣保留來源，但尚未納入本輪一鍵重跑。

公開重現工具只提供 all 與四個案例選項，並在執行前驗證程式及輸入雜湊。它是指定案例的重現入口；擴充任意輸入需要另外建立輸入驗收與案例規則，而非只替換檔名。

## 逐例來源

| 案例 | Python | 初始 C# |
|---|---|---|
| 階梯狀圓柱 | [方法程式](../research/tools/infer_stepped_cylinder_chapter3_method.py) | [分類器來源](../research/%E7%A2%A9%E5%A3%AB%E8%AB%96%E6%96%87/%E7%A8%8B%E5%BC%8F%E7%A2%BC%E5%82%99%E4%BB%BD/%E7%89%B9%E5%BE%B5%E8%BE%A8%E8%AD%98%E6%A0%B8%E5%BF%83%E6%BC%94%E7%AE%97%E6%B3%95/%E7%89%B9%E5%BE%B5%E8%BE%A8%E8%AD%98%E6%A0%B8%E5%BF%83%E6%BC%94%E7%AE%97%E6%B3%95Stepped%20Cylinder/%E7%89%B9%E5%BE%B5%E8%BE%A8%E8%AD%98%E6%A0%B8%E5%BF%83%E6%BC%94%E7%AE%97%E6%B3%95Stepped%20Cylinder.cs) |
| L型板 | [方法程式](../research/tools/infer_lbracket_chapter3_method.py) | [分類器來源](../research/%E7%A2%A9%E5%A3%AB%E8%AB%96%E6%96%87/%E7%A8%8B%E5%BC%8F%E7%A2%BC%E5%82%99%E4%BB%BD/%E7%89%B9%E5%BE%B5%E8%BE%A8%E8%AD%98%E6%A0%B8%E5%BF%83%E6%BC%94%E7%AE%97%E6%B3%95/L_Bracket%E5%B9%BE%E4%BD%95%E9%82%8F%E8%BC%AF/L-Bracket%20%E5%B9%BE%E4%BD%95%E9%82%8F%E8%BC%AF.cs) |
| 模型A | [方法程式](../research/tools/infer_model_a_chapter3_method.py) | [分類器來源](../research/%E7%A2%A9%E5%A3%AB%E8%AB%96%E6%96%87/%E7%A8%8B%E5%BC%8F%E7%A2%BC%E5%82%99%E4%BB%BD/%E7%89%B9%E5%BE%B5%E8%BE%A8%E8%AD%98%E6%A0%B8%E5%BF%83%E6%BC%94%E7%AE%97%E6%B3%95/%E7%89%B9%E5%BE%B5%E8%BE%A8%E8%AD%98%E6%A0%B8%E5%BF%83%E6%BC%94%E7%AE%97%E6%B3%95Model%20A/%E7%89%B9%E5%BE%B5%E8%BE%A8%E8%AD%98%E6%A0%B8%E5%BF%83%E6%BC%94%E7%AE%97%E6%B3%95Model%20A.cs) |
| 盲孔六角座 | [方法程式](../research/tools/infer_blind_hole_hex_base_chapter3_method.py) | [分類器來源](../research/%E7%A2%A9%E5%A3%AB%E8%AB%96%E6%96%87/%E7%A8%8B%E5%BC%8F%E7%A2%BC%E5%82%99%E4%BB%BD/%E7%89%B9%E5%BE%B5%E8%BE%A8%E8%AD%98%E6%A0%B8%E5%BF%83%E6%BC%94%E7%AE%97%E6%B3%95/%E7%89%B9%E5%BE%B5%E8%BE%A8%E8%AD%98%E6%A0%B8%E5%BF%83%E6%BC%94%E7%AE%97%E6%B3%95Blind-Hole%20Hex%20Base/%E7%89%B9%E5%BE%B5%E8%BE%A8%E8%AD%98%E6%A0%B8%E5%BF%83%E6%BC%94%E7%AE%97%E6%B3%95Blind_Hole_Hex_Base_%E4%BF%AE%E6%AD%A3%E7%89%88.cs) |

Python 核對位置：各例 build_outputs；階梯狀圓柱／模型A／盲孔六角座的 assign_semantic_roles；L型板的 semantic_roles 及最終面數查驗。孔洞端部條件見盲孔例 classify_hole_end_condition。
