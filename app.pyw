import os
import re
import sys
import threading
import tkinter as tk
from tkinter import ttk, messagebox, filedialog

# 若被打包成 exe（PyInstaller），內建的 ffmpeg 放在暫存目錄的 ffmpeg_bin 子資料夾，
# 執行時把它加進 PATH，這樣 yt-dlp / ffmpeg-normalize 才找得到 ffmpeg。
if getattr(sys, "frozen", False):
    _bundled_ffmpeg_dir = os.path.join(sys._MEIPASS, "ffmpeg_bin")
    if os.path.isdir(_bundled_ffmpeg_dir):
        os.environ["PATH"] = _bundled_ffmpeg_dir + os.pathsep + os.environ.get("PATH", "")

import yt_dlp
from ffmpeg_normalize import FFmpegNormalize

from updater import VERSION, check_for_update

DEFAULT_OUTPUT_DIR = os.path.join(os.path.expanduser("~"), "Desktop", "YT音樂")
NORMALIZED_SUBDIR = "已校正"

# YouTube 近期會擋自動化工具（跳出「Sign in to confirm you're not a bot」），
# 需要用 cookies 證明是已登入的真人瀏覽器在存取。優先順序：
#   1. 跟這個程式同一層的 cookies.txt（手動匯出，最穩定，不受 Chrome 是否在執行影響）
#   2. 直接讀取 Chrome 的 cookies 資料庫（較方便，但 Chrome 執行中時可能會讀取失敗）
# 若你平常登入 YouTube 用的不是預設的 Chrome 個人檔案，把下面改成
# ("chrome", "Profile 1") 這種形式（個人檔案名稱可在 chrome://version 查看）。
COOKIES_FROM_BROWSER = ("chrome",)
_APP_DIR = os.path.dirname(sys.executable if getattr(sys, "frozen", False) else os.path.abspath(__file__))
COOKIES_TXT_PATH = os.path.join(_APP_DIR, "cookies.txt")
URL_RE = re.compile(r"^https?://")
INVALID_CHARS_RE = re.compile(r'[\\/:*?"<>|]')


def sanitize_filename(name):
    name = INVALID_CHARS_RE.sub("", name).strip()
    return name or "未命名"


def friendly_error(e):
    """把常見的 cookies 讀取失敗訊息轉成好懂的中文提示。"""
    msg = str(e)
    lowered = msg.lower()
    if "could not copy" in lowered and "cookie" in lowered:
        return msg + "\n\n→ 請先完全關閉 Chrome（工作管理員確認沒有殘留的 chrome.exe），再重試一次。"
    if "sign in to confirm" in lowered or "not a bot" in lowered:
        return msg + "\n\n→ 請確認 Chrome 目前是登入 YouTube 的狀態，並確認電腦上有安裝 Chrome。"
    return msg


def parse_song_list(path):
    """解析文字檔：每個 URL 對應上一行非 URL、非 '-' 的文字當作歌名。"""
    pairs = []
    pending_title = None
    with open(path, "r", encoding="utf-8-sig") as f:
        for raw_line in f:
            line = raw_line.strip()
            if not line:
                continue
            # 允許「編號\t內容」或「編號 內容」格式，去掉開頭編號
            line = re.sub(r"^\d+[\t.]\s*", "", line).strip()
            if URL_RE.match(line):
                if pending_title:
                    pairs.append((pending_title, line))
                pending_title = None
            elif line == "-":
                pending_title = None
            else:
                pending_title = line
    return pairs


BG_MAIN = "#1a1b22"
BG_CARD = "#242530"
BG_CARD_BORDER = "#34354a"
FG_TEXT = "#f0f0f5"
FG_MUTED = "#8b8c9e"
ACCENT = "#6c5ce7"
ACCENT_HOVER = "#7d6ff0"
ACCENT_FG = "#ffffff"
BTN_BG = "#33344a"
BTN_HOVER = "#3f4160"
ENTRY_BG = "#2f303d"
LOG_BG = "#121319"
FONT_BASE = ("Segoe UI", 10)
FONT_HEADER = ("Segoe UI", 17, "bold")
FONT_SUB = ("Segoe UI", 9)
FONT_CARD_TITLE = ("Segoe UI", 9, "bold")
FONT_BTN = ("Segoe UI", 10, "bold")
FONT_LOG = ("Consolas", 9)


class DownloaderApp:
    def __init__(self, root):
        self.root = root
        root.title(f"YouTube 音樂下載器 v{VERSION}")
        root.geometry("640x600")
        root.minsize(640, 600)
        root.configure(bg=BG_MAIN)

        self.output_dir = tk.StringVar(value=DEFAULT_OUTPUT_DIR)
        self.status_var = tk.StringVar(value="請貼上 YouTube 網址後按下載")
        self.progress_var = tk.DoubleVar(value=0)

        self._setup_style()

        outer = tk.Frame(root, bg=BG_MAIN)
        outer.pack(fill="both", expand=True, padx=18, pady=16)

        # --- 標題 ---
        header = tk.Frame(outer, bg=BG_MAIN)
        header.pack(fill="x", pady=(0, 14))
        tk.Label(
            header, text="🎵 YT 音樂下載器", font=FONT_HEADER, bg=BG_MAIN, fg=FG_TEXT
        ).pack(anchor="w")
        tk.Label(
            header, text="下載 · 批次匯入 · 音量校正", font=FONT_SUB, bg=BG_MAIN, fg=FG_MUTED
        ).pack(anchor="w")

        # --- 卡片：下載單曲 ---
        card1 = self._make_card(outer, "下載單曲")
        row1 = tk.Frame(card1, bg=BG_CARD)
        row1.pack(fill="x")
        self.url_entry = tk.Entry(
            row1, font=FONT_BASE, bg=ENTRY_BG, fg=FG_TEXT, insertbackground=FG_TEXT,
            relief="flat", highlightthickness=1, highlightbackground=BG_CARD_BORDER,
            highlightcolor=ACCENT,
        )
        self.url_entry.pack(side="left", fill="x", expand=True, ipady=6, padx=(0, 8))
        self.download_btn = self._make_button(
            row1, "下載 MP3", self.start_download, accent=True
        )
        self.download_btn.pack(side="left")

        # --- 卡片：儲存位置 ---
        card2 = self._make_card(outer, "儲存資料夾")
        row2 = tk.Frame(card2, bg=BG_CARD)
        row2.pack(fill="x")
        tk.Entry(
            row2, textvariable=self.output_dir, state="readonly", font=FONT_BASE,
            readonlybackground=ENTRY_BG, fg=FG_MUTED, relief="flat",
            highlightthickness=1, highlightbackground=BG_CARD_BORDER,
        ).pack(side="left", fill="x", expand=True, ipady=6, padx=(0, 8))
        self._make_button(row2, "變更", self.choose_folder).pack(side="left", padx=(0, 6))
        self._make_button(row2, "開啟", self.open_folder).pack(side="left")

        # --- 卡片：批次工具 ---
        card3 = self._make_card(outer, "批次工具")
        self.batch_btn = self._make_button(
            card3, "📋　批次下載（匯入清單 .txt）", self.start_batch_download, full_width=True
        )
        self.batch_btn.pack(fill="x", pady=(0, 8))
        self.normalize_btn = self._make_button(
            card3, "🔊　音量校正（整批，輸出到「已校正」資料夾）", self.start_normalize,
            full_width=True,
        )
        self.normalize_btn.pack(fill="x")

        # --- 進度 / 狀態 ---
        progress_frame = tk.Frame(outer, bg=BG_MAIN)
        progress_frame.pack(fill="x", pady=(4, 4))
        self.progress = ttk.Progressbar(
            progress_frame, variable=self.progress_var, maximum=100, style="Accent.Horizontal.TProgressbar"
        )
        self.progress.pack(fill="x")
        tk.Label(
            outer, textvariable=self.status_var, anchor="w", font=FONT_SUB, bg=BG_MAIN, fg=FG_MUTED
        ).pack(fill="x", pady=(4, 10))

        # --- 紀錄 ---
        log_card = tk.Frame(outer, bg=BG_CARD, highlightthickness=1, highlightbackground=BG_CARD_BORDER)
        log_card.pack(fill="both", expand=True)
        tk.Label(
            log_card, text="紀錄", font=FONT_CARD_TITLE, bg=BG_CARD, fg=FG_MUTED
        ).pack(anchor="w", padx=12, pady=(8, 4))
        log_body = tk.Frame(log_card, bg=BG_CARD)
        log_body.pack(fill="both", expand=True, padx=12, pady=(0, 12))
        scrollbar = tk.Scrollbar(log_body)
        scrollbar.pack(side="right", fill="y")
        self.log = tk.Text(
            log_body, height=8, state="disabled", font=FONT_LOG, bg=LOG_BG, fg=FG_TEXT,
            relief="flat", wrap="word", yscrollcommand=scrollbar.set, padx=8, pady=6,
        )
        self.log.pack(side="left", fill="both", expand=True)
        scrollbar.config(command=self.log.yview)
        self.log.tag_config("ok", foreground="#5fd97a")
        self.log.tag_config("err", foreground="#ff6b6b")

        # --- 免責聲明 ---
        tk.Label(
            outer,
            text="請僅下載你擁有版權或獲得授權的內容，遵守 YouTube 服務條款與當地著作權法。",
            font=("Segoe UI", 8), bg=BG_MAIN, fg=FG_MUTED, wraplength=600, justify="left",
        ).pack(fill="x", pady=(10, 0))

    def _setup_style(self):
        style = ttk.Style(self.root)
        style.theme_use("clam")
        style.configure(
            "Accent.Horizontal.TProgressbar",
            troughcolor=BG_CARD, background=ACCENT, bordercolor=BG_CARD,
            lightcolor=ACCENT, darkcolor=ACCENT, thickness=8,
        )

    def _make_card(self, parent, title):
        card = tk.Frame(parent, bg=BG_CARD, highlightthickness=1, highlightbackground=BG_CARD_BORDER)
        card.pack(fill="x", pady=(0, 12))
        inner = tk.Frame(card, bg=BG_CARD)
        inner.pack(fill="both", padx=14, pady=12)
        tk.Label(inner, text=title, font=FONT_CARD_TITLE, bg=BG_CARD, fg=FG_MUTED).pack(
            anchor="w", pady=(0, 8)
        )
        return inner

    def _make_button(self, parent, text, command, accent=False, full_width=False):
        bg = ACCENT if accent else BTN_BG
        hover = ACCENT_HOVER if accent else BTN_HOVER
        fg = ACCENT_FG if accent else FG_TEXT
        btn = tk.Button(
            parent, text=text, command=command, font=FONT_BTN, bg=bg, fg=fg,
            activebackground=hover, activeforeground=fg, relief="flat", bd=0,
            cursor="hand2", padx=16, pady=9 if full_width else 8,
        )
        btn.bind("<Enter>", lambda e: btn.config(bg=hover) if btn["state"] != "disabled" else None)
        btn.bind("<Leave>", lambda e: btn.config(bg=bg) if btn["state"] != "disabled" else None)
        return btn

    def log_msg(self, msg, tag=None):
        if tag is None:
            tag = "ok" if msg.startswith("[完成]") else "err" if msg.startswith("[錯誤]") else None
        self.log.config(state="normal")
        self.log.insert("end", msg + "\n", tag or ())
        self.log.see("end")
        self.log.config(state="disabled")

    def choose_folder(self):
        folder = filedialog.askdirectory(initialdir=self.output_dir.get())
        if folder:
            self.output_dir.set(folder)

    def open_folder(self):
        folder = self.output_dir.get()
        os.makedirs(folder, exist_ok=True)
        os.startfile(folder)

    def start_download(self):
        url = self.url_entry.get().strip()
        if not url or not URL_RE.match(url):
            messagebox.showwarning("提醒", "請輸入有效的網址 (需以 http:// 或 https:// 開頭)")
            return

        os.makedirs(self.output_dir.get(), exist_ok=True)
        self.set_buttons_state("disabled")
        self.download_btn.config(text="下載中...")
        self.status_var.set("準備下載...")
        self.progress_var.set(0)

        thread = threading.Thread(target=self.run_download, args=(url,), daemon=True)
        thread.start()

    def set_buttons_state(self, state):
        self.download_btn.config(state=state)
        self.batch_btn.config(state=state)
        self.normalize_btn.config(state=state)

    def progress_hook(self, d):
        if d["status"] == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate")
            downloaded = d.get("downloaded_bytes", 0)
            if total:
                pct = downloaded / total * 100
                self.root.after(0, self.progress_var.set, pct)
            self.root.after(0, self.status_var.set, f"下載中... {d.get('_percent_str', '').strip()}")
        elif d["status"] == "finished":
            self.root.after(0, self.status_var.set, "轉檔中 (擷取 MP3)...")
            self.root.after(0, self.progress_var.set, 100)

    def download_one(self, url, outtmpl, progress_hooks=None):
        base_opts = {
            "format": "bestaudio/best",
            "outtmpl": outtmpl,
            "postprocessors": [
                {"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "192"}
            ],
            "noplaylist": True,
            "progress_hooks": progress_hooks or [],
            "quiet": True,
            "no_warnings": True,
        }
        if os.path.isfile(COOKIES_TXT_PATH):
            base_opts["cookiefile"] = COOKIES_TXT_PATH
        else:
            base_opts["cookiesfrombrowser"] = COOKIES_FROM_BROWSER

        # 部分 YouTube 播放端點（player_client）近期常出現：
        #   - 「The page needs to be reloaded」（該端點解析被擋）
        #   - 「Requested format is not available」（該端點只回傳受限格式清單）
        # 換一個端點通常就能繞過，所以依序嘗試幾種組合。ios 目前較不受
        # PO Token 限制影響，優先放前面。
        player_client_attempts = [
            ["ios"],
            ["android"],
            ["web", "android"],
            ["web_safari"],
            ["tv"],
        ]
        RETRYABLE_ERROR_HINTS = ("reload", "requested format is not available", "sabr")

        last_error = None
        for clients in player_client_attempts:
            ydl_opts = dict(base_opts)
            ydl_opts["extractor_args"] = {"youtube": {"player_client": clients}}
            try:
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(url, download=True)
                    return info.get("title", "未知標題")
            except Exception as e:
                last_error = e
                if not any(hint in str(e).lower() for hint in RETRYABLE_ERROR_HINTS):
                    raise
        raise last_error

    def run_download(self, url):
        outtmpl = os.path.join(self.output_dir.get(), "%(title)s.%(ext)s")
        try:
            title = self.download_one(url, outtmpl, [self.progress_hook])
            self.root.after(0, self.on_success, title)
        except Exception as e:
            self.root.after(0, self.on_error, friendly_error(e))

    def on_success(self, title):
        self.status_var.set("完成！")
        self.log_msg(f"[完成] {title}.mp3")
        self.set_buttons_state("normal")
        self.download_btn.config(text="下載音樂 (MP3)")
        self.url_entry.delete(0, "end")

    def on_error(self, err):
        self.status_var.set("下載失敗")
        self.log_msg(f"[錯誤] {err}")
        messagebox.showerror("下載失敗", err)
        self.set_buttons_state("normal")
        self.download_btn.config(text="下載音樂 (MP3)")

    def start_batch_download(self):
        path = filedialog.askopenfilename(
            title="選擇歌曲清單 (.txt)", filetypes=[("文字檔", "*.txt")]
        )
        if not path:
            return
        try:
            pairs = parse_song_list(path)
        except Exception as e:
            messagebox.showerror("讀取失敗", str(e))
            return
        if not pairs:
            messagebox.showwarning("提醒", "在這個檔案裡沒有找到「歌名 + 網址」的配對")
            return
        if not messagebox.askyesno("確認", f"找到 {len(pairs)} 首歌，確定要全部下載嗎？"):
            return

        os.makedirs(self.output_dir.get(), exist_ok=True)
        self.set_buttons_state("disabled")
        self.batch_btn.config(text="批次下載中...")
        self.progress_var.set(0)

        thread = threading.Thread(target=self.run_batch_download, args=(pairs,), daemon=True)
        thread.start()

    def run_batch_download(self, pairs):
        total = len(pairs)
        ok, fail = 0, 0
        for i, (title, url) in enumerate(pairs, start=1):
            self.root.after(0, self.status_var.set, f"({i}/{total}) 下載中：{title}")
            safe_title = sanitize_filename(title)
            outtmpl = os.path.join(self.output_dir.get(), f"{safe_title}.%(ext)s")
            try:
                self.download_one(url, outtmpl)
                ok += 1
                self.root.after(0, self.log_msg, f"[完成] {safe_title}.mp3")
            except Exception as e:
                fail += 1
                self.root.after(0, self.log_msg, f"[錯誤] {title}：{friendly_error(e)}")
            self.root.after(0, self.progress_var.set, i / total * 100)

        def finish():
            self.status_var.set(f"批次下載完成：成功 {ok}，失敗 {fail}")
            self.set_buttons_state("normal")
            self.batch_btn.config(text="批次下載 (匯入清單 .txt)")
            messagebox.showinfo("批次下載完成", f"成功 {ok} 首，失敗 {fail} 首")

        self.root.after(0, finish)

    def start_normalize(self):
        src_dir = self.output_dir.get()
        if not os.path.isdir(src_dir):
            messagebox.showwarning("提醒", "儲存資料夾不存在，請先下載一些歌曲")
            return
        files = sorted(
            f for f in os.listdir(src_dir)
            if f.lower().endswith(".mp3") and os.path.isfile(os.path.join(src_dir, f))
        )
        if not files:
            messagebox.showwarning("提醒", "這個資料夾裡沒有找到 mp3 檔案")
            return
        if not messagebox.askyesno(
            "確認",
            f"找到 {len(files)} 首歌，要對它們做音量校正嗎？\n"
            f"結果會輸出到「{NORMALIZED_SUBDIR}」子資料夾，不會動到原始檔案。"
        ):
            return

        out_dir = os.path.join(src_dir, NORMALIZED_SUBDIR)
        os.makedirs(out_dir, exist_ok=True)
        self.set_buttons_state("disabled")
        self.normalize_btn.config(text="音量校正中...")
        self.progress_var.set(0)

        thread = threading.Thread(
            target=self.run_normalize, args=(files, src_dir, out_dir), daemon=True
        )
        thread.start()

    def run_normalize(self, files, src_dir, out_dir):
        total = len(files)
        ok, fail = 0, 0
        for i, name in enumerate(files, start=1):
            self.root.after(0, self.status_var.set, f"({i}/{total}) 校正中：{name}")
            try:
                fn = FFmpegNormalize(
                    normalization_type="ebu",
                    target_level=-14.0,
                    true_peak=-2.0,
                    keep_loudness_range_target=True,  # 強制線性增益，避免逐段自動調整造成的呼吸感
                    audio_codec="libmp3lame",
                    audio_bitrate=192000,
                    extension="mp3",
                    progress=False,
                )
                fn.add_media_file(os.path.join(src_dir, name), os.path.join(out_dir, name))
                fn.run_normalization()
                ok += 1
                self.root.after(0, self.log_msg, f"[完成] {name}")
            except Exception as e:
                fail += 1
                self.root.after(0, self.log_msg, f"[錯誤] {name}：{e}")
            self.root.after(0, self.progress_var.set, i / total * 100)

        def finish():
            self.status_var.set(f"音量校正完成：成功 {ok}，失敗 {fail}")
            self.set_buttons_state("normal")
            self.normalize_btn.config(text="音量校正 (整批，輸出到「已校正」資料夾)")
            messagebox.showinfo("音量校正完成", f"成功 {ok} 首，失敗 {fail} 首\n輸出於：{out_dir}")

        self.root.after(0, finish)


if __name__ == "__main__":
    root = tk.Tk()
    app = DownloaderApp(root)
    check_for_update(root)
    root.mainloop()
