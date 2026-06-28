# 離線照片分類器

這是一個 Windows 11 適用的離線照片分類器。它會先掃描照片、產生預覽，再由使用者確認 PowerShell 指令後執行。程式設計重點是安全、可預覽、不可刪除。

## 快速開始

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
powershell -ExecutionPolicy Bypass -File tools\run_app.ps1
```

若要執行測試：

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
powershell -ExecutionPolicy Bypass -File tools\run_tests.ps1
```

## 功能

- 依照修改日期、建立日期、較晚日期或 EXIF 拍攝日期分類照片。
- 預設日期規則為修改日期。
- 資料夾名稱格式為 `YYYY-MM-DD (X)`，例如 `2026-06-20 (六)`。
- 星期會依照日期計算，不會隨機產生。
- 預設複製照片並保留原檔，也可在執行前選擇搬移。
- 發生同日期且同檔名時，會在日期資料夾內保留來源根資料夾以下的完整相對路徑。
- 不覆蓋既有檔案；如果完整相對路徑下仍衝突，會列為錯誤。
- 預覽後會顯示圖示化分類前安全報告。
- PowerShell 確認畫面左側顯示指令，右側顯示安全提醒。
- PowerShell 指令可以另存成 `.ps1` 或 `.txt`，方便使用者執行前人工審查。
- 程式啟動後會啟用本機離線防護，阻止 Python 網路連線。
- 程式啟動後會限制外部程序呼叫，阻止執行常見網路工具。
- 來源資料夾與輸出資料夾必須是本機路徑，不允許 UNC 網路路徑或網路磁碟。
- 支援黑底白字、白底黑字、字級調整、系統字型下拉選單。
- 支援 `Ctrl + 滑鼠滾輪` 縮放介面字級。
- 介面預設 14 字級；安全提醒標題為 16 字級、內文為 14 字級。
- 數字與英文預設為 `Times New Roman`。

## 截圖

截圖可放在 `docs/screenshots/`。建議上傳 GitHub 前補：

- 主畫面
- 分類預覽表
- PowerShell 安全確認畫面
- 設定視窗

目前 `docs/screenshots/` 只保留空資料夾占位檔，不包含使用者照片或私人路徑截圖。

## 安全設計

本程式不提供刪除功能，也不會產生刪除用途的 PowerShell 指令。

PowerShell 產生器只用於建立資料夾、複製或搬移照片。執行前會做安全掃描；如果偵測到常見刪除指令字樣，會停用「執行」按鈕，只能取消。

PowerShell 安全掃描也會阻止常見網路傳輸指令，例如 `Invoke-WebRequest`、`Invoke-RestMethod`、`Start-BitsTransfer`、`curl`、`wget`、`ftp`、`sftp`、`scp`、`ssh`、`net`。

程式層會封鎖 Python socket 連線，避免程式執行期間主動透過網路送出資料。這是應用程式內部防線；若需要系統層級保證，請在實體斷網環境或受控 Windows 防火牆規則下執行。

程式也會限制 subprocess 外部程序呼叫。正常操作只需要 PowerShell 執行本程式產生的白名單指令，以及 Explorer 開啟本機輸出資料夾；其他外部程序預設會被阻止。

輸出資料夾不可與來源資料夾相同，也不可放在來源資料夾內。這可以避免下一次掃描時把已分類照片再次掃入。

搬移模式不會刪除照片，但會讓照片離開原本資料夾，因此程式會另外要求使用者確認。

更多資訊請見 [SECURITY.md](SECURITY.md) 與 [PRIVACY.md](PRIVACY.md)。

## EXIF 限制

EXIF 拍攝日期是可選日期規則，不是預設規則。第一版只讀取圖片內常見的 EXIF 日期欄位；如果照片沒有 EXIF、EXIF 被移除、格式不被 Pillow 支援，該照片會被列為略過，不會自動改用其他日期。

可能受影響的情況：

- iPhone 或 iPad 的 HEIC 照片：部分 HEIC metadata 可能無法被目前依賴讀取。
- Android 手機照片：不同品牌相機 App 寫入 EXIF 的方式不完全一致。
- 相機 RAW 或特殊格式轉出的照片：第一版不處理 RAW metadata。
- 通訊軟體、社群平台、雲端下載的照片：EXIF 常被壓縮或移除。
- 截圖、修圖後匯出的圖片：通常沒有原始拍攝日期。

若需要最穩定的分類結果，建議使用預設的「修改日期」或手動切換為「建立日期」「較晚日期」。

## 資料庫狀態

目前第一版不建立資料庫，也不保存分類歷史。程式只使用本機設定檔保存介面偏好，例如主題、字級、字型與預設日期規則。

因此目前沒有 SQL 注入攻擊面；專案也已移除未使用的資料庫安全層，避免第一版增加不必要複雜度。

## 使用方式

1. 安裝 Python 3.10 以上版本。
2. 在專案資料夾中安裝依賴：

```powershell
python -m pip install -r requirements.txt
```

3. 啟動程式：

```powershell
$env:PYTHONPATH = "$PWD\src"
python -m photo_sorter
```

也可以使用專案內的啟動腳本：

```powershell
powershell -ExecutionPolicy Bypass -File tools\run_app.ps1
```

4. 選擇來源資料夾與輸出資料夾。
5. 選擇日期規則與檔案動作。
6. 按「產生預覽」確認分類結果與安全報告。
7. 按「產生 PowerShell」檢查指令。
8. 確認沒有刪除或網路傳輸相關指令後，按「執行」。

## 離線安裝依賴

在可上網電腦先下載完整安裝包：

```powershell
py -m pip download -r requirements-dev.txt -d C:\photo_sorter_offline
```

把 `C:\photo_sorter_offline` 複製到離線電腦後，在專案資料夾安裝：

```powershell
.\.venv\Scripts\python.exe -m pip install --no-index --find-links C:\photo_sorter_offline -r requirements-dev.txt
```

若只要執行程式、不跑測試或打包，可把上面的 `requirements-dev.txt` 改成 `requirements.txt`。

## 打包成 Windows 執行檔

安裝開發依賴後可用 PyInstaller 打包：

```powershell
python -m pip install -r requirements-dev.txt
powershell -ExecutionPolicy Bypass -File tools\build_exe.ps1
```

打包完成後，執行檔會出現在：

```text
dist\OfflinePhotoSorter.exe
```

如果尚未安裝 PyInstaller，請先執行：

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
```

注意：`dist` 與 `build` 資料夾已被 `.gitignore` 排除，不應上傳到 GitHub 原始碼 repository。若要發布 exe，建議之後使用 GitHub Release 附加檔案。

## GitHub 上傳準備

第一次建立 Git 專案：

```powershell
git init
git add README.md LICENSE SECURITY.md PRIVACY.md CHANGELOG.md pyproject.toml .gitignore requirements.txt requirements-dev.txt docs src tests tools .github
git commit -m "initial: offline photo sorter"
```

之後可建立 GitHub repository，再依照 GitHub 頁面提供的 remote 指令推送。

若本機已設定好 `origin/main`，可用以下指令上傳目前 commit：

```powershell
git push
git status
```

當 `git status` 顯示類似以下內容時，代表本機 `main` 分支和 GitHub 的 `origin/main` 已同步，且目前沒有尚未提交的程式碼變更：

```text
On branch main
Your branch is up to date with 'origin/main'.
nothing to commit, working tree clean
```

注意：這只代表原始碼和文件已同步。`dist\OfflinePhotoSorter.exe` 屬於打包產物，預設不放進 GitHub 原始碼 repository；若要提供 EXE 給使用者下載，建議另外用 GitHub Release 上傳。

## 開發備份機制

`tools/dev_checkpoint.ps1` 是給開發者使用的備份輔助腳本。每完成一次軟體修正後執行一次：

```powershell
powershell -ExecutionPolicy Bypass -File tools/dev_checkpoint.ps1
```

第 1 次只記錄計數；第 2 次若程式碼有變更，會自動建立 Git commit。這個機制只備份程式碼，不會備份使用者照片、分類輸出或私人設定。

## 測試

```powershell
python -m pip install -r requirements-dev.txt
powershell -ExecutionPolicy Bypass -File tools\run_tests.ps1
```

測試涵蓋日期與星期、同名檔案分流、禁止覆蓋、錯誤分類、圖示化安全報告、輸出資料夾位置防呆、網路路徑阻擋、網路連線防護、安全掃描、EXIF 缺失處理，以及 PowerShell 產生邏輯。

## 授權

本專案使用 MIT License。詳見 [LICENSE](LICENSE)。
