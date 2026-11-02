# YT 音樂下載器

下載 YouTube 音樂為 MP3、批次匯入、音量校正。啟動時會自動檢查 GitHub Releases，有新版會詢問並自動更新。

請僅下載你擁有版權或獲得授權的內容。

## 發佈新版

1. 改 `updater.py` 的 `VERSION`
2. `./build.ps1`
3. `gh release create vX.Y.Z dist/YT-Music-Downloader.exe`（資產檔名必須是 `YT-Music-Downloader.exe`）
