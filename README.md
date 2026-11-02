# YT 音樂下載器

下載 YouTube 音樂為 MP3、批次匯入清單、整批音量校正。啟動時會自動檢查 GitHub Releases，有新版會詢問並自動更新。

請僅下載你擁有版權或獲得授權的內容，遵守 YouTube 服務條款與當地著作權法。

- 倉庫：https://github.com/ToDreamToDesign/yt-music-downloader（公開）
- 本機：`C:\Users\Meng\yt-music-downloader\`
- 星座：雙子座 Gemini（INDEX 內 source_repo＝`YT Music Downloader`）
- 目前版本：見 `updater.py` 的 `VERSION`

## 架構

| 檔案 | 作用 |
|---|---|
| `app.pyw` | Tkinter 主程式：單曲下載、批次下載（.txt 清單）、音量校正（EBU R128，-14 LUFS） |
| `updater.py` | 啟動時背景查 GitHub 最新 Release，有新版詢問後下載並替換自己 |
| `build.ps1` | PyInstaller 單檔打包，內含 ffmpeg／ffprobe（`ffmpeg_bin/`） |

## 重要設計與踩過的坑

- **YouTube 擋機器人**：需要 cookies。優先讀程式同層的 `cookies.txt`，沒有才讀 Chrome 的 cookies（Chrome 執行中可能讀取失敗，需先完全關閉）。`cookies.txt` 已列入 `.gitignore`，絕不上傳。
- **player_client 輪替**：依序嘗試 ios → android → web+android → web_safari → tv；遇到 `reload`／`requested format is not available`／`sabr` 錯誤才換下一個，其他錯誤直接拋出。
- **批次清單格式**：每個網址對應上一行非網址、非 `-` 的文字當歌名，開頭編號會被去掉。
- **音量校正**：輸出到儲存資料夾下的「已校正」子資料夾，不動原檔。
- **預設儲存位置**：`~/Desktop/YT音樂`。

## 自動更新機制

1. 啟動後背景請求 `releases/latest`（逾時 5 秒），失敗一律靜默略過，照常開啟舊版。
2. Release 版本號大於程式內 `VERSION`，且有名為 `YT-Music-Downloader.exe` 的資產，才詢問使用者。
3. 同意後下載到 `<exe>.new`，大小核對無誤，寫一個暫存 bat：等本程式結束 → `move /y` 蓋掉舊 exe（失敗就每秒重試）→ 重新啟動，並設 `PYINSTALLER_RESET_ENVIRONMENT=1` 避免繼承舊的解壓目錄。
4. 只在打包成 exe 時才會替換；直接跑 `.pyw` 只會提示有新版。

已驗證：exe 能啟動、能查到 Release、換檔 bat 邏輯正確。**完整的「跳出視窗→下載→重開」流程要等發第二個版本才能實測。**

## 發佈新版

1. 改 `updater.py` 的 `VERSION`
2. `./build.ps1`（輸出 `dist/YT-Music-Downloader.exe`，約 205 MB，因為內含完整版 ffmpeg）
3. `gh release create vX.Y.Z dist/YT-Music-Downloader.exe`（資產檔名必須是 `YT-Music-Downloader.exe`）

## 已知限制

- exe 約 205 MB，每次更新要下載整包；若嫌大可改用精簡版 ffmpeg 重打包。
- yt-dlp 封在 exe 裡，YouTube 改規則導致失效時，需重新打包發新版才能修。
