# 二維圓擬合的工程fixture

六份CSV由既有 [geometry_fixtures.py](../../tools/geometry_fixtures.py) 直接生成，每份64點；不是新的論文案例、真實掃描或修改後的研究輸入。`U,V` 是明確二維座標，弧fixture中心(2,−3)、半徑10；共線及重合點沒有指定唯一解析半徑真值。

[manifest.json](manifest.json) 記錄產生碼SHA、CSV SHA、float64陣列SHA與解析生成參數。使用 `%.17g`、LF匯出，讀回陣列與原fixture逐值相同；陣列SHA也與v0.1.6保存的診斷相符。

```powershell
./.venv/Scripts/python.exe tools/check-circle-fit.py --input examples/guarded-circle/arc_0.00001.csv --output runs/new-circle-rank-report.json
```

在記錄環境此命令回傳代碼2，報告為初始化數值支撐不足，不是要求修改參數重試。[完整契約、其他狀態與未知項目](../../docs/geometry-guard.md)

v0.1.8起可用 `python tools/verify-circle-replays.py --output-dir runs/new-circle-replays` 一次實際執行全部六份CSV×兩份實作。CI也執行此入口，核對每份報告的狀態／退出碼及未驗證旗標；所有契約檢查正確才是重放器成功，不代表12次原求解皆成功。六份CSV與manifest維持v0.1.7位元。
