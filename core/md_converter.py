"""Markdown 转 HTML 模块。

基于 markdown-it-py（CommonMark 规范级解析器），启用 GFM 常用扩展：
表格、删除线、任务列表、自动链接。仅做文本 → HTML 片段的纯转换，
不涉及任何界面与文件 I/O。
"""

import threading

from markdown_it import MarkdownIt
from mdit_py_plugins.tasklists import tasklists_plugin

# 解析器全局选项：
# html=True   —— 渲染 Markdown 内嵌的 HTML 标签（查看器体验优先，仅用于打开本地可信文件）
# linkify=True —— 自动把裸 URL 转为链接（GFM 行为）
_PARSER_OPTIONS = {"html": True, "linkify": True, "typographer": False}

# 模块级共享解析器（初始化一次，避免每次渲染重复构建规则链）
_converter: MarkdownIt | None = None
# markdown-it-py 官方未承诺 render 跨线程安全，pywebview 的 js_api 在后台线程调用，
# 加一把轻量锁串行化渲染，稳定性优先
_lock = threading.Lock()


def create_converter() -> MarkdownIt:
    """创建并配置 MarkdownIt 解析器实例。

    Returns:
        配置好 GFM 扩展（表格 / 删除线 / 任务列表）的解析器。
    """
    parser = MarkdownIt("commonmark", _PARSER_OPTIONS)
    # commonmark 预设下 table/strikethrough/linkify 规则默认关闭，须显式启用
    # （linkify 仅设 options 不生效，必须 enable 规则链）
    parser.enable(["table", "strikethrough", "linkify"])
    parser.use(tasklists_plugin)
    return parser


def convert(markdown_text: str) -> str:
    """把 Markdown 文本渲染为 HTML 片段。

    Args:
        markdown_text: 原始 Markdown 文本。

    Returns:
        渲染后的 HTML 片段字符串（不含 <html>/<body> 外壳）。
        空文本返回空字符串，不会抛出异常。
    """
    global _converter
    if _converter is None:
        _converter = create_converter()
    with _lock:
        return _converter.render(markdown_text)
