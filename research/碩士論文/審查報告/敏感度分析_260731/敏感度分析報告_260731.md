# 四案例核心門檻單因子敏感度分析（2026-07-31）

## 設計與判準

本分析固定一項門檻、一次只改變另一項。距離門檻測試 1.5、2.0、2.5 mm；法向量內積門檻測試 0.90、0.93、0.96。每個結果僅與相同因素的基準輸出比較；輸出雜湊完全相同才記為「輸出穩定」，不將穩定誤寫為正確性或泛化能力。

## 事前預期、證偽條件與輸入版本

- **預期**：只改變一項門檻時，可能改變分割、接受面、拓樸關係、候選幾何單元或 CSG 符號輸出；若輸出雜湊不變，僅表示該受控輸入在該設定附近具有局部輸出穩定性。
- **證偽條件**：任一執行失敗，或任一輸出檔雜湊與同一因素的基準設定不一致，即否定該設定的「輸出穩定」；不以面數恰好相同取代雜湊比對。
- **固定輸入與基準**：距離測試固定法向量內積門檻 0.93；法向量測試固定距離門檻 2.0 mm。四個輸入分別為 `Result_Stepped Cylinder.csv`、`Result_L Bracket.csv`、`Result_Model A.csv` 與 `Result_Blind-Hole Hex Base_fixed.csv`。每次執行使用私有程式副本；各副本 SHA-256、原始輸入路徑、標準輸出與錯誤輸出均記錄於 `sensitivity_results.json`。

## 結果摘要

| 實作範例 | 因素 | 設定值 | 執行狀態 | 與基準輸出一致 | 接受面數 | 殘留點 | 拓樸關係 | 候選幾何單元 |
|---|---:|---:|---|---|---:|---:|---:|---:|
| Stepped_Cylinder | distance_mm | 1.50 | 完成 | 否 | 6 | 0 | 6 | 3 |
| Stepped_Cylinder | distance_mm | 2.00 | 完成 | 是 | 6 | 0 | 6 | 3 |
| Stepped_Cylinder | distance_mm | 2.50 | 完成 | 是 | 6 | 0 | 6 | 3 |
| Stepped_Cylinder | normal_dot | 0.90 | 完成 | 否 | 6 | 0 | 6 | 3 |
| Stepped_Cylinder | normal_dot | 0.93 | 完成 | 是 | 6 | 0 | 6 | 3 |
| Stepped_Cylinder | normal_dot | 0.96 | 完成 | 是 | 6 | 0 | 6 | 3 |
| L_Bracket | distance_mm | 1.50 | 失敗 | 不適用 | — | — | — | — |
| L_Bracket | distance_mm | 2.00 | 完成 | 是 | 12 | 0 | 24 | 5 |
| L_Bracket | distance_mm | 2.50 | 完成 | 否 | 12 | 0 | 24 | 5 |
| L_Bracket | normal_dot | 0.90 | 完成 | 否 | 12 | 0 | 24 | 5 |
| L_Bracket | normal_dot | 0.93 | 完成 | 是 | 12 | 0 | 24 | 5 |
| L_Bracket | normal_dot | 0.96 | 完成 | 是 | 12 | 0 | 24 | 5 |
| Model_A | distance_mm | 1.50 | 完成 | 否 | 13 | 0 | 25 | 6 |
| Model_A | distance_mm | 2.00 | 完成 | 是 | 13 | 0 | 26 | 6 |
| Model_A | distance_mm | 2.50 | 完成 | 否 | 13 | 0 | 26 | 6 |
| Model_A | normal_dot | 0.90 | 完成 | 否 | 13 | 0 | 26 | 6 |
| Model_A | normal_dot | 0.93 | 完成 | 是 | 13 | 0 | 26 | 6 |
| Model_A | normal_dot | 0.96 | 完成 | 是 | 13 | 0 | 26 | 6 |
| Blind_Hole_Hex_Base | distance_mm | 1.50 | 完成 | 否 | 12 | 0 | 22 | 3 |
| Blind_Hole_Hex_Base | distance_mm | 2.00 | 完成 | 是 | 12 | 0 | 22 | 3 |
| Blind_Hole_Hex_Base | distance_mm | 2.50 | 完成 | 否 | 12 | 0 | 22 | 3 |
| Blind_Hole_Hex_Base | normal_dot | 0.90 | 完成 | 否 | 12 | 0 | 22 | 3 |
| Blind_Hole_Hex_Base | normal_dot | 0.93 | 完成 | 是 | 12 | 0 | 22 | 3 |
| Blind_Hole_Hex_Base | normal_dot | 0.96 | 完成 | 是 | 12 | 0 | 22 | 3 |

## 未完成執行的如實紀錄

L 型板在距離門檻 1.5 mm 時，第三章推論程式產生 28 個面級記錄，未通過程式內「L 型板應有 12 個面」的一致性檢查而停止。此項結果保留為失敗，不以放寬檢查、併入額外規則或改動其他參數使其通過。

## 證據界線

本分析只使用點級分割結果與公開方法規則；變體程式、副本雜湊、原始輸入與各次輸出均保留於同資料夾。它不讀取真值、網格面或候選模板，亦不取代真實掃描雜訊條件下的魯棒性驗證。
