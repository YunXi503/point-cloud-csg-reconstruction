# 論文 CSG 圖與 JSON 的表示對照

[專案首頁](../README.md) · [模型A圖件](figures/model-a.md) · [完整論文](../paper/thesis-public-snapshot-20261105.pdf)

論文圖使用逐步展開的二元 CSG 樹。現有四個案例的 JSON 有兩種格式，讀取時應先確認案例格式，再參考候選編號及展開順序。

| 案例 | 現有 JSON 格式 |
|---|---|
| 階梯狀圓柱 | base／children／subtractors 分組式表示 |
| L型板 | base／children／subtractors 分組式表示 |
| 模型A | base／children／subtractors 分組式表示 |
| 盲孔六角座 | left／right 巢狀二元表示 |

前三例沒有將每一次二元運算展開成巢狀節點；盲孔六角座已使用巢狀二元格式。現行查驗保留各例既有格式，不將它們默認為同一個 schema。

## 現有檔案格式

以模型A為例，JSON 的 tree 部分如下：

```json
{
  "op": "Difference",
  "base": {
    "op": "Union",
    "children": [
      {"candidate": "MA_U01"},
      {"candidate": "MA_U02"},
      {"candidate": "MA_U03"},
      {"candidate": "MA_U04"}
    ]
  },
  "subtractors": [
    {"candidate": "MA_D01"},
    {"candidate": "MA_D02"}
  ]
}
```

這個格式保留了候選群組與順序。Union 的 children 在此例有四項，Difference 的 subtractors 有兩項，因此此檔本身並非每個運算節點恰有兩個子節點的巢狀二元樹。

程式 canonical_csg_tree 依 CandidateID 排序兩組候選；論文第 3.9 節再以左結合方式說明二元展開：先將聯集候選依序合併，再逐一切除差集候選。

## 對應圖 4.10 的閱讀表示

依上述順序，可將此例寫成：

```text
B1 = Union(MA_U01, MA_U02)
B2 = Union(B1, MA_U03)
B3 = Union(B2, MA_U04)
C1 = Difference(B3, MA_D01)
T  = Difference(C1, MA_D02)
```

此處 B1、B2、B3、C1 是本頁用來逐步閱讀的中間名稱，不代表 JSON 已輸出這些節點名稱。正式圖件沿用其原有標註。

這是依論文規則說明 JSON 與圖件之間的展開關係；該版沒有新增轉換器，也沒有改寫既有 JSON。若下游需要四例統一使用巢狀二元 JSON，前三例仍須另行提供明確的格式轉接及語義查驗，盲孔六角座則保留原有二元表示。

## 從候選回查來源

模型A的 MA_D01 在候選 CSV 中記錄為 MainAxisYThroughHole，來源群集為 1、2、10，BooleanType 為 Difference；它位於 JSON 的 subtractors 中，並對應圖 4.10 的孔洞候選。

這條對照鏈可由候選編號回到 RelatedClusters，再查看 FaceSummary 及 TopologyEdges；JSON 中的候選 ID 不單獨包含所有面級幾何證據。

## 查核來源

- [現有模型A JSON](../research/碩士論文/第四章驗證結果_260724/Model_A_chapter3_verified_v3/CSGTree_Model_A_chapter3_verified.json)
- [候選 CSV](../research/碩士論文/第四章驗證結果_260724/Model_A_chapter3_verified_v3/PrimitiveCandidates_Model_A_chapter3_verified.csv)
- [面級資料](../research/碩士論文/第四章驗證結果_260724/Model_A_chapter3_verified_v3/FaceSummary_Model_A_chapter3_verified.csv)
- [拓樸資料](../research/碩士論文/第四章驗證結果_260724/Model_A_chapter3_verified_v3/TopologyEdges_Model_A_chapter3_verified.csv)
- [原樣推論程式](../research/tools/infer_model_a_chapter3_method.py)：canonical_csg_tree

檔案重現檢查支持既有輸出的一致性；圖與 JSON 的格式對照不另構成 CAD 幾何執行、新模型或準確率驗證。
