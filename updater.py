"""啟動時檢查 GitHub Releases，有新版就下載並自動替換 exe 後重開。

只在打包成 exe（sys.frozen）時才會真的替換；直接跑 .pyw 時只做版本檢查、不動檔案。
任何網路或下載錯誤都靜默略過，不影響程式正常開啟。
"""
import os
import re
import subprocess
import sys
import tempfile
import threading
import tkinter as tk
from tkinter import messagebox
import requests

VERSION = "2.1.0"
GITHUB_REPO = "ToDreamToDesign/yt-music-downloader"
ASSET_NAME = "YT-Music-Downloader.exe"
API_URL = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"


def _parse(tag):
    return tuple(int(n) for n in re.findall(r"\d+", tag)[:3])


def _fetch_latest():
    r = requests.get(API_URL, timeout=5, headers={"Accept": "application/vnd.github+json"})
    r.raise_for_status()
    data = r.json()
    for a in data.get("assets", []):
        if a["name"] == ASSET_NAME:
            return data["tag_name"], a["browser_download_url"], a["size"]
    return None


def check_for_update(root, status_cb=None):
    """背景檢查更新；有新版時在主執行緒詢問使用者。"""
    def worker():
        try:
            latest = _fetch_latest()
            if not latest or _parse(latest[0]) <= _parse(VERSION):
                return
            root.after(0, _ask, root, latest, status_cb)
        except Exception:
            pass
    threading.Thread(target=worker, daemon=True).start()


def _ask(root, latest, status_cb):
    tag, url, size = latest
    msg = f"有新版本 {tag}（目前 v{VERSION}，約 {size // 1024 // 1024} MB）。要現在更新嗎？"
    if not getattr(sys, "frozen", False):
        messagebox.showinfo("有新版本", msg + "\n\n（目前是以 .pyw 執行，請改用 exe 才能自動更新）")
        return
    if messagebox.askyesno("有新版本", msg):
        _show_progress(root, url, size)


def _show_progress(root, url, size):
    win = tk.Toplevel(root)
    win.title("更新中")
    win.geometry("320x90")
    win.resizable(False, False)
    win.transient(root)
    label = tk.Label(win, text="下載中... 0%")
    label.pack(expand=True)
    win.protocol("WM_DELETE_WINDOW", lambda: None)

    def worker():
        exe = sys.executable
        new_path = exe + ".new"
        try:
            with requests.get(url, stream=True, timeout=15) as r:
                r.raise_for_status()
                done = 0
                with open(new_path, "wb") as f:
                    for chunk in r.iter_content(1024 * 256):
                        f.write(chunk)
                        done += len(chunk)
                        pct = int(done / size * 100) if size else 0
                        root.after(0, label.config, {"text": f"下載中... {pct}%"})
            if size and os.path.getsize(new_path) != size:
                raise IOError("下載大小不符")
            root.after(0, _apply, root, exe, new_path)
        except Exception as e:
            try:
                os.remove(new_path)
            except OSError:
                pass
            root.after(0, win.destroy)
            root.after(0, messagebox.showerror, "更新失敗", f"{e}\n\n請稍後再試，程式仍可正常使用舊版。")

    threading.Thread(target=worker, daemon=True).start()


def _apply(root, exe, new_path):
    """寫一個 bat：等本程式結束 → 換檔 → 重新開啟，然後自己結束。"""
    bat = os.path.join(tempfile.gettempdir(), "ytdl_update.bat")
    script = (
        "@echo off\r\n"
        "set PYINSTALLER_RESET_ENVIRONMENT=1\r\n"
        ":retry\r\n"
        "ping 127.0.0.1 -n 2 >nul\r\n"
        f'move /y "{new_path}" "{exe}" >nul 2>&1\r\n'
        "if errorlevel 1 goto retry\r\n"
        f'start "" "{exe}"\r\n'
        '(goto) 2>nul & del "%~f0"\r\n'
    )
    with open(bat, "w", encoding="mbcs") as f:
        f.write(script)
    subprocess.Popen(
        ["cmd", "/c", bat], creationflags=0x08000000, close_fds=True  # CREATE_NO_WINDOW
    )
    root.destroy()
    os._exit(0)
