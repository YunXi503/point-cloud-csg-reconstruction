# 歷史敏感度標記的事後勘誤

[首頁](../README.md) · [品質與限制](results.md) · [逐筆複核 JSON](../provenance/sensitivity-recheck.json) · [原始摘要](../evidence/sensitivity-2026-07-31/sensitivity_results.json)

日期：2026-11-05。原摘要、報告、變體、輸入與輸出均未修改。複核依原判準，只把每筆已存的六項輸出 SHA 與**同案例、同因素**的基準比較；距離基準仍為 2.0 mm，法向量內積基準仍為 0.93。這是保存資料的事後查核，沒有新增或重跑敏感度實驗。

## 發現的五筆標記差異

| 案例 | 因素 | 設定 | 原 matches_baseline | 依保存雜湊複核 |
|---|---|---:|---|---|
| Stepped_Cylinder | distance_mm | 1.50 | false | true |
| Stepped_Cylinder | normal_dot | 0.90 | false | true |
| L_Bracket | normal_dot | 0.90 | false | true |
| Model_A | normal_dot | 0.90 | false | true |
| Blind_Hole_Hex_Base | normal_dot | 0.90 | false | true |

這五筆的六項輸出都與其同因素基準相同，原表中的「否」不應被解讀為實際檔案不同。原工作區的 138 個歷史輸出及 120 個變體來源也逐一核對保存的 SHA，全部吻合；公開包提供逐筆查核與既有 manifest，未收錄全部歷史變體及逐次輸出。

現存[控制程式快照](../evidence/traceability-2026-11-05/run_threshold_sensitivity_260731.py#L101)在迴圈遇到基準設定後才建立 baseline_hashes，而較小設定先被執行，會與尚不存在的基準比較。此邏輯可解釋上述誤標；原摘要沒有控制程式本身的歷史執行 SHA，因此不能證明該快照就是當時執行的完全相同版本。快照僅供讀取，不是公開包的重跑入口。

## 計數如何閱讀

| 分母 | 與同因素基準六檔相同 | 有檔案不同 | 未完成 |
|---|---:|---:|---:|
| 8 組基準自比 | 8 | 0 | 0 |
| 16 組非基準設定 | 10 | 5 | 1 |

非基準的 15 組完成設定中，10 組位元一致、5 組不同；另有 1 組未完成。不要把 8 組基準自比算成額外穩定性證據，也不要將這些數字稱為正確率、獨立模型數或真實掃描魯棒性。

盲孔六角座六組歷史執行使用 fdd5c384… 輸入，現行重現綁定使用 0d69141f…，見[輸入綁定](../provenance/sensitivity-input-bindings.json)。本次複核始終使用各自保存的同因素基準，沒有把兩個輸入版本混在一起比。

L型板距離 1.5 mm 的失敗仍保留，沒有補成通過。該筆沒有輸入 SHA、manifest，保存的輸出目錄也沒有檔案；控制程式只保存輸入路徑，另一個敏感度目錄僅留階梯狀圓柱基準資料。這次仍無法找回失敗輸入的精確位元版本；相鄰成功紀錄的 SHA 不能代填。
