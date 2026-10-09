"""pywebview js_api 桥接层（薄层）。

职责：接收前端调用 → 调用 core 层完成实际工作 → 把结果整理成
可直接 JSON 化的字典返回。禁止在此层写业务规则。
"""

import logging
import os
import re
from pathlib import Path
from urllib.parse import quote

import webview

from core import file_service, folder_scanner, html_exporter, md_converter

logger = logging.getLogger(__name__)

# 匹配 markdown-it 生成的相对路径图片标签（绝对 http/file/data/根路径不处理）
_IMG_SRC_PATTERN = re.compile(r'<img src="(?!https?://|file:|data:|/)([^"]*)"')


def _get_window() -> "webview.Window | None":
    """取主窗口实例（未创建时返回 None）。"""
    return webview.windows[0] if webview.windows else None


def _absolutize_image_srcs(html: str, base_dir: str) -> str:
    """把渲染结果中相对路径的图片补全为指向源目录的 file:// 绝对 URI。

    Args:
        html: Markdown 渲染出的 HTML 片段。
        base_dir: 源 Markdown 文件所在目录。

    Returns:
        图片路径已补全的 HTML 片段。
    """
    base_uri = Path(base_dir).as_uri().rstrip("/") + "/"

    def replace(match: "re.Match[str]") -> str:
        relative = match.group(1).replace("\\", "/")
        # file URI 要求百分号编码（中文、空格、# 等），quote 保留 / 不编码
        return f'<img src="{base_uri}{quote(relative)}"'

    return _IMG_SRC_PATTERN.sub(replace, html)


class Api:
    """暴露给前端 window.pywebview.api 的桥接类。

    Attributes:
        initial_path: 命令行传入的初始目标路径（可为空）。
        initial_is_dir: 初始目标是否为目录。
    """

    def __init__(self, initial_path: str | None = None, initial_is_dir: bool = False):
        self.initial_path = initial_path
        self.initial_is_dir = initial_is_dir

    # ---------- 启动 ----------

    def get_initial_target(self) -> dict:
        """返回命令行传入的初始加载目标（供前端启动后自动加载）。"""
        return {"ok": True, "target": self.initial_path, "is_dir": self.initial_is_dir}

    # ---------- 对话框 ----------

    def open_folder_dialog(self) -> dict:
        """弹出文件夹选择对话框。"""
        window = _get_window()
        if window is None:
            return {"ok": False, "error": "窗口未就绪"}
        chosen = window.create_file_dialog(webview.FOLDER_DIALOG)
        if not chosen:
            return {"ok": False, "error": "已取消"}
        return {"ok": True, "path": chosen[0]}

    def open_file_dialog(self) -> dict:
        """弹出 Markdown 文件选择对话框。"""
        window = _get_window()
        if window is None:
            return {"ok": False, "error": "窗口未就绪"}
        chosen = window.create_file_dialog(
            webview.OPEN_DIALOG,
            allow_multiple=False,
            file_types=("Markdown 文件 (*.md;*.markdown)", "所有文件 (*.*)"),
        )
        if not chosen:
            return {"ok": False, "error": "已取消"}
        return {"ok": True, "path": chosen[0]}

    # ---------- 文件树 ----------

    def scan_folder(self, path: str) -> dict:
        """扫描目录生成 Markdown 文件树。"""
        result = folder_scanner.scan_folder(path)
        if not result.ok:
            return {"ok": False, "error": result.error}
        return {
            "ok": True,
            "path": path,
            "root": result.root.to_dict(),
            "file_count": result.file_count,
            "truncated": result.truncated,
        }

    # ---------- 新建 ----------

    def new_file_dialog(self) -> dict:
        """弹出保存对话框创建新的 Markdown 文件（立即落盘空文件）。"""
        window = _get_window()
        if window is None:
            return {"ok": False, "error": "窗口未就绪"}
        chosen = window.create_file_dialog(
            webview.SAVE_DIALOG,
            save_filename="未命名.md",
            file_types=("Markdown 文件 (*.md;*.markdown)", "所有文件 (*.*)"),
        )
        if not chosen:
            return {"ok": False, "error": "已取消"}
        out_path = chosen[0] if isinstance(chosen, (list, tuple)) else str(chosen)
        if not out_path.lower().endswith((".md", ".markdown")):
            out_path += ".md"
        result = file_service.write_text_file(out_path, "")
        if not result.ok:
            return {"ok": False, "error": result.error}
        return {
            "ok": True,
            "path": out_path,
            "dir": os.path.dirname(os.path.abspath(out_path)),
        }

    # ---------- 读取 / 保存 ----------

    def read_file(self, path: str) -> dict:
        """读取 Markdown 文件（附所在目录，供前端处理相对图片）。"""
        result = file_service.read_text_file(path)
        if not result.ok:
            return {"ok": False, "error": result.error}
        return {
            "ok": True,
            "path": path,
            "dir": os.path.dirname(os.path.abspath(path)),
            "content": result.content,
            "encoding": result.encoding,
        }

    def save_file(self, path: str, content: str) -> dict:
        """把编辑器内容保存到当前文件（UTF-8 无 BOM）。"""
        result = file_service.write_text_file(path, content)
        if not result.ok:
            return {"ok": False, "error": result.error}
        return {"ok": True}

    # ---------- 渲染 / 导出 ----------

    def convert_markdown(self, markdown_text: str, base_dir: str | None = None) -> dict:
        """渲染 Markdown 为 HTML，相对图片补全为 file:// 绝对路径。"""
        try:
            html = md_converter.convert(markdown_text)
        except Exception as exc:  # 解析器内部异常兜底，保证界面不崩
            logger.exception("Markdown 渲染异常")
            return {"ok": False, "error": f"渲染失败：{exc}"}
        if base_dir:
            html = _absolutize_image_srcs(html, base_dir)
        return {"ok": True, "html": html}

    def export_html(self, path: str) -> dict:
        """把当前文件导出为独立 HTML（弹出保存对话框）。"""
        window = _get_window()
        if window is None:
            return {"ok": False, "error": "窗口未就绪"}
        read = file_service.read_text_file(path)
        if not read.ok:
            return {"ok": False, "error": read.error}
        suggested = Path(path).stem + ".html"
        chosen = window.create_file_dialog(webview.SAVE_DIALOG, save_filename=suggested)
        if not chosen:
            return {"ok": False, "error": "已取消"}
        # 不同平台后端返回类型不一（str 或单元素序列），统一取首个字符串
        out_path = chosen[0] if isinstance(chosen, (list, tuple)) else str(chosen)
        if not out_path.lower().endswith(".html"):
            out_path += ".html"
        export = html_exporter.export_to_file(
            out_path,
            Path(path).name,
            md_converter.convert(read.content),
            base_dir=os.path.dirname(os.path.abspath(path)),
        )
        if not export.ok:
            return {"ok": False, "error": export.error}
        return {"ok": True, "path": out_path}
