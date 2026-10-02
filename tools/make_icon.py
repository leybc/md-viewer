"""生成应用图标（Markdown 风格：深色圆角底 + 白色 M + 下箭头）。

用法：
    python tools/make_icon.py

输出：
    assets/icon.ico          多尺寸 Windows 图标（256/128/64/48/32/16）
    assets/icon_preview.png  预览图（便于人工检查绘制效果）
"""

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

SIZE = 256
ASSET_DIR = Path(__file__).resolve().parent.parent / "assets"
# GitHub 风格深灰蓝底，白色图形
DARK = (36, 41, 47, 255)
WHITE = (255, 255, 255, 255)


def _load_font(size: int) -> ImageFont.FreeTypeFont:
    """加载粗体字体（Windows 标配 Arial Bold；失败时回退默认字体）。"""
    for name in ("arialbd.ttf", "arial.ttf"):
        try:
            return ImageFont.truetype(rf"C:\Windows\Fonts\{name}", size)
        except OSError:
            continue
    return ImageFont.load_default()


def build_image() -> Image.Image:
    """绘制 256x256 图标底图。

    Returns:
        RGBA 图标图像。
    """
    image = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    # 深色圆角矩形底
    draw.rounded_rectangle([6, 6, 250, 250], radius=52, fill=DARK)
    # 白色 M（左半，Markdown 官方标志布局）
    draw.text((40, 58), "M", font=_load_font(130), fill=WHITE)
    # 白色下箭头（右半）：竖杆 + 三角头
    bar_center = 178
    draw.rectangle([bar_center - 13, 56, bar_center + 13, 132], fill=WHITE)
    draw.polygon(
        [(bar_center - 44, 126), (bar_center + 44, 126), (bar_center, 198)], fill=WHITE
    )
    return image


def main() -> None:
    """生成 ico 与预览 png。"""
    ASSET_DIR.mkdir(exist_ok=True)
    image = build_image()
    image.save(
        ASSET_DIR / "icon.ico",
        sizes=[(256, 256), (128, 128), (64, 64), (48, 48), (32, 32), (16, 16)],
    )
    image.save(ASSET_DIR / "icon_preview.png")
    print(f"已生成 {ASSET_DIR / 'icon.ico'} 与 {ASSET_DIR / 'icon_preview.png'}")


if __name__ == "__main__":
    main()
