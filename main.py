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
import socket
import sys
import threading
import time
from pathlib import Path
from typing import TYPE_CHECKING

from core import file_service

# webview 与 ui.api（连带 pythonnet/.NET CLR 初始化）是启动耗时大头，
# 延迟到确认本进程是主实例后再导入：已开窗口时再双击 md 的转发路径可秒级退出
if TYPE_CHECKING:
    import webview

_PROCESS_START = time.perf_counter()


def _elapsed_ms() -> int:
    """进程启动以来的毫秒数（启动耗时分段统计用）。"""
    return int((time.perf_counter() - _PROCESS_START) * 1000)


APP_TITLE = "MD 查看器"
WINDOW_SIZE = (1200, 800)
MIN_SIZE = (820, 560)

# 单实例 IPC：第一个实例监听本机回环端口，后续实例把目标路径转发后退出。
# 只监听 127.0.0.1，仅供本机内部通信
IPC_HOST = "127.0.0.1"
IPC_PORT = 47513

PROJECT_ROOT = Path(__file__).resolve().parent


def _resource_root() -> Path:
    """界面资源根目录：开发态为源码目录；PyInstaller 打包后为自解压目录。"""
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS)
    return PROJECT_ROOT


def _app_root() -> Path:
    """应用根目录：开发态为源码目录；打包后为 exe 所在目录（日志放这里便于查找）。"""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return PROJECT_ROOT


INDEX_HTML = _resource_root() / "ui" / "static" / "index.html"
ICON_PATH = _resource_root() / "assets" / "icon.ico"
LOG_DIR = _app_root() / "logs"

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
    缺少该字段的项说明路径通道未生效，静默忽略，不产生误导提示。
    """
    import webview

    window = webview.windows[0]
    files = event.get("dataTransfer", {}).get("files", [])
    for item in files:
        full_path = item.get("pywebviewFullPath")
        if not full_path:
            continue
        if file_service.is_markdown_file(full_path):
            logger.info("拖入文件：%s", full_path)
            window.evaluate_js(
                f"window.app && window.app.loadFromPath({json.dumps(full_path)})"
            )
            return
    # 所有项都有路径但都不是 Markdown 时才提示（避免路径通道异常时的误导）
    if files and all(item.get("pywebviewFullPath") for item in files):
        logger.info("拖入的内容不是 Markdown 文件，已忽略")
        window.evaluate_js(
            "window.app && window.app.setStatus && window.app.setStatus("
            "'拖入的不是 Markdown 文件', true)"
        )


def _smoke_self_check(window: "webview.Window") -> None:
    """冒烟自检：验证关键 DOM 元素与 pywebview 桥接真实就绪（能启动且能交互）。"""
    ready = window.evaluate_js(
        "!!(document.getElementById('toolbar') && document.getElementById('preview')"
        " && document.getElementById('file-tree') && document.getElementById('editor-wrap')"
        " && document.getElementById('editor-gutter') && window.pywebview"
        " && window.pywebview.api && window.pywebview.api.get_initial_target)"
    )
    if ready:
        logger.info("冒烟自检：DOM 与桥接就绪 — 通过")
    else:
        logger.error("冒烟自检失败：DOM 元素或 pywebview 桥未就绪")
        os._exit(3)


def _handle_ipc_payload(window: "webview.Window", payload: bytes) -> bytes:
    """处理一条单实例 IPC 请求，返回应答（OK / ERR）。

    载荷为 JSON：{"paths": [...]}。每个路径按类型分发给前端
    （文件开标签、目录打开导航树）；空路径列表仅聚焦已有窗口。
    """
    try:
        data = json.loads(payload.decode("utf-8"))
        paths = [p for p in data.get("paths", []) if isinstance(p, str) and p.strip()]
    except (UnicodeDecodeError, ValueError):
        logger.warning("IPC 载荷解析失败")
        return b"ERR"
    for path in paths:
        is_dir = Path(path).is_dir()
        window.evaluate_js(
            f"window.app && window.app.loadFromPath({json.dumps(path)}, {str(is_dir).lower()})"
        )
    window.show()
    return b"OK"


def _start_ipc_listener(window: "webview.Window") -> None:
    """在主实例中启动后台线程，监听后续实例转发来的打开请求。"""

    def listener() -> None:
        server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            # 注意：Windows 上不设 SO_REUSEADDR（其语义会允许重复绑定同一端口）
            server.bind((IPC_HOST, IPC_PORT))
        except OSError:
            logger.warning("单实例端口 %d 绑定失败，单实例功能降级", IPC_PORT)
            return
        server.listen(4)
        logger.info("单实例监听就绪 %s:%d", IPC_HOST, IPC_PORT)
        while True:
            try:
                conn, _ = server.accept()
            except OSError:
                return  # 服务套接字已关闭（进程退出）
            with conn:
                try:
                    conn.settimeout(2.0)
                    chunks: list[bytes] = []
                    while not (chunks and chunks[-1].endswith(b"\n")):
                        chunk = conn.recv(4096)
                        if not chunk:
                            break
                        chunks.append(chunk)
                    reply = _handle_ipc_payload(window, b"".join(chunks))
                    conn.sendall(reply)
                except OSError:
                    logger.exception("IPC 连接处理异常")

    threading.Thread(target=listener, daemon=True).start()


def _try_forward_to_running_instance(targets: list[str]) -> bool:
    """把启动目标转发给已运行实例；返回 True 表示本进程应直接退出。"""
    try:
        with socket.create_connection((IPC_HOST, IPC_PORT), timeout=1.0) as sock:
            sock.settimeout(3.0)
            sock.sendall((json.dumps({"paths": targets}) + "\n").encode("utf-8"))
            reply = sock.recv(16)
            return reply.startswith(b"OK")
    except OSError:
        return False  # 无人监听：本进程即主实例


def _on_window_loaded() -> None:
    """窗口加载完成后的订阅与冒烟处理。"""
    import webview

    window = webview.windows[0]
    logger.info("窗口加载完成（%d ms）", _elapsed_ms())
    # 订阅拖拽（Python 侧订阅后 WebView2 才会上报完整路径）
    window.dom.body.events.drop += _on_files_dropped
    # 单实例：监听后续实例转发来的打开请求
    _start_ipc_listener(window)
    # 冒烟模式：自检通过后 4 秒自动退出（供自动化测试验证"能启动不崩溃"）
    if os.environ.get("MD_VIEWER_SMOKE") == "1":
        _smoke_self_check(window)
        # 编辑态冒烟（MD_VIEWER_SMOKE_EDIT=1）：切到编辑模式，供截图验证行号栏
        if os.environ.get("MD_VIEWER_SMOKE_EDIT") == "1":
            window.evaluate_js(
                "document.getElementById('btn-mode-edit') && document.getElementById('btn-mode-edit').click()"
            )
        # 自退停留时长可配（默认 4 秒；截图验证时用 MD_VIEWER_SMOKE_LINGER 拉长窗口存活期）
        linger = float(os.environ.get("MD_VIEWER_SMOKE_LINGER", "4"))
        logger.info("冒烟模式：自退停留 %g 秒", linger)
        timer = threading.Timer(linger, window.destroy)
        timer.daemon = True
        timer.start()


def main() -> None:
    """应用主入口。"""
    setup_logging()
    logger.info("md-viewer 启动（引导耗时 %d ms）", _elapsed_ms())
    targets = [item for item in sys.argv[1:] if item.strip()]
    if _try_forward_to_running_instance(targets):
        logger.info("已转发给运行中的实例，本进程退出（总耗时 %d ms）", _elapsed_ms())
        return
    # 本进程为主实例：导入 GUI 依赖（pythonnet/.NET CLR 的初始化发生在这里）
    import webview

    from ui.api import Api

    logger.info("GUI 依赖导入完成（%d ms）", _elapsed_ms())
    initial_path, initial_is_dir = resolve_initial_target(targets)
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
