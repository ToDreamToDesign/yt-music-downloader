# 打包成單一 exe（內含 ffmpeg）。輸出：dist\YT-Music-Downloader.exe
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
$ffdir = Split-Path (Get-Command ffmpeg).Source
python -m PyInstaller --noconfirm --clean --onefile --windowed `
    --name "YT-Music-Downloader" `
    --add-binary "$ffdir\ffmpeg.exe;ffmpeg_bin" `
    --add-binary "$ffdir\ffprobe.exe;ffmpeg_bin" `
    --collect-all yt_dlp `
    app.pyw
