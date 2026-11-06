# 論文公式到實作的可追溯對照

[首頁](../README.md) · [方法範圍](method-scope.md) · [機器可讀來源](../provenance/method-traceability.json) · [仍缺資料](missing-information.md)

本頁對照現存正式 Word、公開來源與已有執行紀錄，未修改論文或研究程式。它補足 M1 的技術對照，不能還原未留存的開發決策、歷史編譯檔或當時 runtime。

## 五階段與公式

| 論文位置 | 實際實作位置 | 可確認的對應與界線 |
|---|---|---|
| 點雲生成；公式 3-1、3-2 | 各例 build_outputs 讀取 X/Y/Z、NX/NY/NZ 及既有初始分割欄位 | 現行入口使用已生成的 10000 點 CSV；保留取樣來源，不代表該版重新執行 Blender 取樣 |
| 幾何特徵分割；公式 3-3 | [L型板 region_growing](../research/tools/infer_lbracket_chapter3_method.py#L52) | 在距離鄰近點對中保留有向法向量內積達門檻者，再取連通分量；此處可直接對到距離／法向量條件 |
| 幾何特徵分割及語義特徵面 | [階梯狀圓柱 infer_surfaces](../research/tools/infer_stepped_cylinder_chapter3_method.py#L222)、[模型A infer_point_assignments](../research/tools/infer_model_a_chapter3_method.py#L287)、[盲孔 build_outputs](../research/tools/infer_blind_hole_hex_base_chapter3_method.py#L336) | 使用既有群集、擬合與案例修正；不能將這些流程都稱為 L型板的 region_growing 或公式 3-3 的逐行相同實作 |
| 語義拓樸；公式 3-4 | [共用 min_distance／build_topology](../research/tools/infer_stepped_cylinder_chapter3_method.py#L323)、[L型板 build_topology](../research/tools/infer_lbracket_chapter3_method.py#L321) | 以有限取樣點支撐的最小距離判定；不是連續解析曲面邊界距離 |
| 正交相鄰；公式 3-5 | 同上 build_topology | 已相鄰的平面組以法向量內積絕對值小於 0.2 判斷；以實際 Word 公式及程式為準，純文字抽取不保證保留公式排版符號 |
| 端面關係；公式 3-6 | 同上 build_topology | 平面／圓柱距離不超過 5.0 mm 且軸向內積絕對值大於 0.95，優先記 EndCap；之後才考慮正交／一般相鄰。端面可使用較大的接觸距離，不要求先通過 2.0 mm 一般相鄰門檻 |
| 候選幾何單元；第三章 3.8 | 四例 build_candidates；盲孔另有 [classify_hole_end_condition](../research/tools/infer_blind_hole_hex_base_chapter3_method.py#L195) | 依來源面、語義角色、拓樸、尺寸與 Union／Difference 推論；候選角色仍含各例專屬條件 |
| 階層式 CSG；公式 3-7 | 四例 canonical_csg_tree | 論文為依 CandidateID 左結合的二元遞迴文法；前三例 JSON 是候選分組，盲孔為二元巢狀。這是表示層差異，不能宣稱四份 JSON 已逐節點輸出論文二元樹，見[表示契約](csg-representation.md) |

模型A與盲孔的 build_topology 從階梯狀圓柱模組匯入；L型板另有本地版本。各例函式的來源 SHA、起訖行與正式 Word 段落摘錄列於 method-traceability.json，行號只對本版保存來源有效。

## 初始 C# 與 Python 分開判讀

初始分類器的有效條件已列在[方法範圍](method-scope.md)：階梯狀圓柱為硬編碼 3.0 mm／絕對內積 0.9999 或側面條件；L型板幾何邏輯版為 2.0／0.93；模型A與盲孔另有法向量分箱及弧段分群。這些差異與公式 3-3 的共通敘述不能畫上完全一致的等號。

[現行 C# 綁定](../examples/segmentation.json)與[搬移後執行紀錄](../validation/2026-11-05/relocated-pipeline-results.json)可證明目前選定來源／環境產出四份初始 CSV 及 24 份核心輸出相同位元；無法據此推定原開發時使用相同編譯產物或 runtime。

另找回的[流程圖任務包](../evidence/traceability-2026-11-05/flowchart-task-original.md)已要求揭露案例門檻及非二元 JSON 差異。它只是歷史規劃證據，沒有被提升為方法實際執行證明。原始決策時間線與各差異的完整歷史理由仍缺，M1 維持部分補齊。
