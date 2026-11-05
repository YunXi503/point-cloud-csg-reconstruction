# 可重現執行環境

已在 Windows x64、Python 3.14.2 的新建 venv，依完整鎖定清單安裝及執行。環境未繼承系統套件，專案也搬到含空格及中文的另一個目錄查驗。

## Python 安裝

tools/bootstrap.ps1 從 PATH 與 Python 安裝登錄尋找實際 Python 3.14.2，避開 Windows Store 別名。可傳入 -PythonPath 指定直譯器；它只建立專案 .venv，不變更系統 Python。

若政策不允許執行 PowerShell 腳本，可用已安裝的 Python 3.14.2：

```powershell
python -m venv .venv
./.venv/Scripts/python.exe -m pip install -r requirements.lock.txt
./.venv/Scripts/python.exe -m pip check
```

不必啟用 Activate.ps1 或變更全域執行政策。若 python --version 沒有顯示實際直譯器，請用安裝的 python.exe 完整路徑執行第一行。

## 套件版本

requirements.lock.txt 鎖定這次乾淨環境的全部 13 個執行套件。requirements.txt 指向該清單；requirements-observed.txt 只保留初次環境紀錄。

初次環境的 NumPy 2.4.0 已被 PyPI 撤回。本輪先確認該版本乾淨安裝可重現 24 項輸出，再只換為 2.4.1；其他套件版本相同，24 項仍逐位元相符。[環境紀錄](../validation/2026-11-05/environment-transition.json) · [官方修補說明](https://numpy.org/devdocs/release/2.4.1-notes.html)

這不是歷史環境的完整復原，未主張其他 Python、作業系統或 CPU 上必然逐位元一致。

## C# 環境

| 初始分類來源 | 本次可重現環境 |
|---|---|
| 階梯狀圓柱、L型板、模型A | .NET Framework 4.8，Visual Studio MSBuild |
| 盲孔六角座修正版 | .NET 8；實測 runtime 8.0.20，建置 SDK 9.0.305 |

盲孔同一來源在 .NET Framework 4.8 無法符合歷史 CSV，在 .NET 8 下則相符。Microsoft 說明不同 .NET 世代的浮點解析／一般格式有差異；本輪記錄可重現環境，不推定當年使用何者，也未逐項隔離解析、運算與格式化的貢獻。[Microsoft 說明](https://learn.microsoft.com/en-us/dotnet/standard/base-types/standard-numeric-format-strings)

保留的 CSV 演算法使用小數點。轉接器拒絕小數分隔符號不是 . 的文化設定，不靜默變更研究計算的文化設定。
