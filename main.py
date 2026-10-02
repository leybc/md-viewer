"""md-viewer 入口模块。

流程：配置日志 → 解析命令行目标（.md 文件或目录，支持"打开方式"关联启动）
→ 创建主窗口（WebView2 内存模式，零落盘）→ 订阅拖拽事件 → 进入消息循环。

用法：
    python main.py                 # 空界面启动
    python main.py 某文件.md        # 启动即加载该文件
    python main.py 某目录           # 启动即扫描该目录
"""

import json
import logging
import os
import sys
import threading
from pathlib import Path

import webview

from core import file_service
from ui.api import Api

APP_TITLE = "MD 查看器"
WINDOW_SIZE = (1200, 800)
MIN_SIZE = (820, 560)

PROJECT_ROOT = Path(__file__).resolve().parent
INDEX_HTML = PROJECT_ROOT / "ui" / "static" / "index.html"
ICON_PATH = PROJECT_ROOT / "assets" / "icon.ico"
LOG_DIR = PROJECT_ROOT / "logs"

logger = logging.getLogger(__name__)


def setup_logging() -> None:
    """初始化日志：同时输出到控制台与 logs/app.log。"""
    LOG_DIR.mkdir(exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
        handlers=[
            logging.FileHandler(LOG_DIR / "app.log", encoding="utf-8"),
            logging.StreamHandler(),
        ],
    )


def resolve_initial_target(argv: list[str]) -> tuple[str | None, bool]:
    """解析命令行第一个参数为初始加载目标。

    Args:
        argv: sys.argv[1:]。

    Returns:
        (目标路径, 是否为目录)；无参数或参数无效时返回 (None, False)。
    """
    if not argv:
        return None, False
    target = argv[0]
    if Path(target).is_dir():
        return target, True
    if Path(target).is_file():
        return target, False
    logger.warning("命令行目标无效，忽略：%s", target)
    return None, False


def _on_files_dropped(event: dict) -> None:
    """处理拖入的文件：取第一个 Markdown 文件并通知前端加载。

    pywebview 在 WebView2 后端把拖入文件的完整路径注入事件数据的
    pywebviewFullPath 字段（须在 Python 侧订阅 drop 才生效）。
    """
    window = webview.windows[0]
    files = event.get("dataTransfer", {}).get("files", [])
    for item in files:
        full_path = item.get("pywebviewFullPath")
        if full_path and file_service.is_markdown_file(full_path):
            logger.info("拖入文件：%s", full_path)
            window.evaluate_js(
                f"window.app && window.app.loadFromPath({json.dumps(full_path)})"
            )
            return
    if files:
        logger.info("拖入的内容不是 Markdown 文件，已忽略")
        window.evaluate_js(
            "window.app && window.app.setStatus && window.app.setStatus("
            "'拖入的不是 Markdown 文件', true)"
        )


def _smoke_self_check(window: "webview.Window") -> None:
    """冒烟自检：验证关键 DOM 元素与 pywebview 桥接真实就绪（能启动且能交互）。"""
    ready = window.evaluate_js(
        "!!(document.getElementById('toolbar') && document.getElementById('preview')"
        " && document.getElementById('file-tree') && window.pywebview"
        " && window.pywebview.api && window.pywebview.api.get_initial_target)"
    )
    if ready:
        logger.info("冒烟自检：DOM 与桥接就绪 — 通过")
    else:
        logger.error("冒烟自检失败：DOM 元素或 pywebview 桥未就绪")
        os._exit(3)


def _on_window_loaded() -> None:
    """窗口加载完成后的订阅与冒烟处理。"""
    window = webview.windows[0]
    # 订阅拖拽（Python 侧订阅后 WebView2 才会上报完整路径）
    window.dom.body.events.drop += _on_files_dropped
    # 冒烟模式：自检通过后 4 秒自动退出（供自动化测试验证"能启动不崩溃"）
    if os.environ.get("MD_VIEWER_SMOKE") == "1":
        _smoke_self_check(window)
        logger.info("冒烟模式：4 秒后自动退出")
        timer = threading.Timer(4.0, window.destroy)
        timer.daemon = True
        timer.start()


def main() -> None:
    """应用主入口。"""
    setup_logging()
    logger.info("md-viewer 启动")
    initial_path, initial_is_dir = resolve_initial_target(sys.argv[1:])
    api = Api(initial_path, initial_is_dir)
    window = webview.create_window(
        APP_TITLE,
        str(INDEX_HTML),
        js_api=api,
        width=WINDOW_SIZE[0],
        height=WINDOW_SIZE[1],
        min_size=(MIN_SIZE[0], MIN_SIZE[1]),
    )
    window.events.loaded += _on_window_loaded
    icon = str(ICON_PATH) if ICON_PATH.exists() else None
    if icon is None:
        logger.warning("未找到图标文件 %s，使用默认图标", ICON_PATH)
    # private_mode=True：WebView2 数据保存在内存，不在磁盘留下缓存（默认值，显式声明意图）
    webview.start(icon=icon, private_mode=True, debug=False)
    logger.info("md-viewer 退出")


if __name__ == "__main__":
    main()
