# 可選二維圓擬合：輸入契約與停止狀態

[首頁](../README.md) · [事前計畫](geometry-guard-plan.md) · [原函式診斷](geometry-diagnostics.md) · [再次審查](geometry-guard-review.md) · [12項實際重放](../validation/2026-11-05/geometry-guard-results.json)

這個外層讓呼叫端知道輸入為何被拒絕，以及原求解器有沒有達到原步長停止門檻。它沒有修正原半徑、換求解器或改研究參數；達到步長門檻仍不代表參數準確。四案例的既有入口維持原流程，未自動套用本外層。

## 執行與輸入

沿用首頁的鎖定環境。CSV 必須只有明確的二維座標欄位 `U,V`；不由 `X,Y,Z` 猜軸向或投影。例如：

```powershell
./.venv/Scripts/python.exe tools/check-circle-fit.py --input examples/guarded-circle/arc_360.csv --output runs/new-circle-full.json
./.venv/Scripts/python.exe tools/check-circle-fit.py --input examples/guarded-circle/arc_0.001.csv --implementation lbracket --output runs/new-circle-short.json
```

每次選新輸出路徑，工具拒絕覆寫既有報告。第二個命令在記錄環境回傳代碼3，這是保留未達停止條件的預期狀態。六份[範例CSV及manifest](../examples/guarded-circle/README.md)由原工程fixture匯出，並非論文STL案例或掃描資料。

Python 呼叫可使用 `tools/geometry_guard.py` 的 `guarded_circle_fit(values, implementation="stepped")`，其中 values 為 N×2 實數陣列，implementation 為 `stepped` 或 `lbracket`。原單位沿用輸入，API 不自行換算；本頁解析 fixture 使用 mm。

## 檢查次序與依據

1. 要求 N×2 實數數值，拒絕布林、複數、字串及 object 陣列；使用 float64，拒絕 NaN／Infinity。
2. 要求至少三個不同點，檢查原初始化的 `[2U,2V,1]` 與 `U²+V²` 是否有限。只計算不同點數，不刪除重複列、不改順序或權重。
3. 使用原初始化同一矩陣及 `numpy.linalg.lstsq(rcond=None)` 的回報秩；小於3時拒絕。這是該float64初始化的數值支撐契約，不是物理可識別性的充分必要證明。條件數只列診斷，沒有新增角度或條件數切點。
4. 非線性執行前核對兩份原始碼的固定SHA及保護來源目錄，再由AST讀取100輪與1e−13停止門檻。來源漂移不會更新期望SHA來放行。
5. 外部只讀 trace 觀察原函式最後 step；不修改函式或重新求解。已有 debugger／trace 時不覆蓋，回報無法觀察。正常及例外路徑都恢復先前trace。此診斷介面適合單執行緒呼叫，不作並行服務、完整coverage環境或效能量測承諾。
6. 檢查原回傳結構、有限值、正半徑及迭代範圍。只有可靠觀察到最後步長≤原門檻，才提供 `estimate`。第100輪恰好達標也按步長判斷，不只看輪數。

原來源固定為[共用版本](../research/tools/infer_stepped_cylinder_chapter3_method.py)及[L型板輔助版本](../research/tools/correct_stepped_cylinder_nls_v2.py)。輸入不置中、不重縮放，不增加迭代、不換初始化或正則化，也不放寬門檻。

## 報告與回傳代碼

| status | estimate | CLI代碼 | 解讀 |
|---|---|---:|---|
| `step_threshold_met` | 有，尚未驗證 | 0 | 原步長停止條件達成，不能解讀成半徑正確 |
| `iteration_limit_without_step_threshold` | null | 3 | 達原迭代上限且最後步長仍未達標 |
| `stop_condition_not_met` | null | 3 | 原函式回傳，但可靠觀察未達原停止門檻 |
| `invalid_input` | null | 2 | 欄位、形狀、型別、有限值或初始化運算無效 |
| `insufficient_support` | null | 2 | 點數／不同點數不足或初始化數值秩小於3 |
| `blocked_source_version` | null | 2 | 原始碼或停止契約未通過核對 |
| `solver_exception`／`invalid_solver_result` | null | 2 | 原求解器例外或回傳結構／數值無效 |
| `stop_observation_unavailable` | null | 2 | 已有trace，或最後步長未可靠觀察；不猜收斂 |

`solver_called` 指是否呼叫原非線性求解器；輸入預檢本身會執行初始化矩陣的線性秩檢查。`raw_result` 是原回傳供診斷的參數、最大殘差與輪數，不能拿它繞過狀態當作合格估計。`convergence.step_threshold_met` 未觀察時為 null，不用小殘差或輪數填成 true。

**所有報告均為 `verification.parameters_verified=false`**。本API沒有接受獨立參數參考或經校準的不確定度界線，也不設小殘差即可通過的準確度規則。JSON的非有限診斷值以字串保留，不產生非標準NaN數字或捏造0。

## 同資料重放：拒絕與修正不可混稱

記錄環境 Python 3.14.2、NumPy 2.4.1；兩份實作各六份64點fixture，輸入陣列SHA全與v0.1.6相同。詳見[逐筆CSV](../validation/2026-11-05/geometry-guard-observations.csv)。

| fixture | 原始行為 | 新外層，兩份實作均同 |
|---|---|---|
| 360°／10° | 達原步長條件，半徑約10 | `step_threshold_met`，提供未驗證估計 |
| 0.001° | 100輪，最後步長2.0442546e−6，半徑9.9999865026 | `iteration_limit_without_step_threshold`，estimate=null，保留raw_result |
| 0.00001° | 原函式兩輪達標卻回傳6.3847486990，半徑誤差3.6152513010 | 原初始化數值秩2，`insufficient_support`，不呼叫非線性求解器 |
| 共線／重合 | 原函式仍回傳幾何，沒有唯一解析半徑參考 | `insufficient_support`，不提供估計 |

六次實際呼叫原非線性求解器的回傳，與未加trace的直接呼叫完全相等。這確認本次外層未改回傳，不保證所有平台的浮點結果或所有短弧都相同。半徑誤差以fixture解析生成值另作評估，沒有傳入API或用來調參。

尚未建立完整三維面型拒絕契約、一般短弧角度界線、對雜訊／尺度／座標平移的保證、跨硬體覆蓋或可信區間；見[資料缺口](missing-information.md)。
