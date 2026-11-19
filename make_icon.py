"""由 logo_gemini.jpg（雙子座 LOGO）產生 icon.ico／icon.png。執行：python make_icon.py"""
from PIL import Image, ImageDraw

SRC = Image.open("logo_gemini.jpg").convert("RGB")
# 裁出圓角方塊本體（原圖四周是純黑底），再套圓角遮罩讓四角透明
BOX = (161, 159, 861, 859)
icon = SRC.crop(BOX).resize((1024, 1024), Image.LANCZOS).convert("RGBA")
mask = Image.new("L", (1024, 1024), 0)
ImageDraw.Draw(mask).rounded_rectangle([0, 0, 1023, 1023], radius=215, fill=255)
icon.putalpha(mask)

icon.save("icon.png")
icon.save("icon.ico", sizes=[(256, 256), (128, 128), (64, 64), (48, 48), (32, 32), (16, 16)])
print("ok")
