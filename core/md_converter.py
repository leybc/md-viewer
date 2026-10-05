"""Markdown 转 HTML 模块。

基于 markdown-it-py（CommonMark 规范级解析器），启用 GFM 常用扩展：
表格、删除线、任务列表、自动链接。仅做文本 → HTML 片段的纯转换，
不涉及任何界面与文件 I/O。
"""

import re
import threading

from markdown_it import MarkdownIt
from mdit_py_plugins.tasklists import tasklists_plugin

# 解析器全局选项：
# html=True   —— 渲染 Markdown 内嵌的 HTML 标签（查看器体验优先，仅用于打开本地可信文件）
# linkify=True —— 自动把裸 URL 转为链接（GFM 行为）
# breaks=True —— 单个换行渲染为 <br>：笔记类文档（如课堂记录）普遍不带 Markdown 空行分段，
#                严格 CommonMark 会把整段软换行合并成一行，阅读体验极差；查看器按所见即所得处理
_PARSER_OPTIONS = {"html": True, "linkify": True, "typographer": False, "breaks": True}

# 模块级共享解析器（初始化一次，避免每次渲染重复构建规则链）
_converter: MarkdownIt | None = None
# markdown-it-py 官方未承诺 render 跨线程安全，pywebview 的 js_api 在后台线程调用，
# 加一把轻量锁串行化渲染，稳定性优先
_lock = threading.Lock()


def create_converter() -> MarkdownIt:
    """创建并配置 MarkdownIt 解析器实例。

    Returns:
        配置好 GFM 扩展（表格 / 删除线 / 任务列表）、源行号注入与
        行首缩进保留（softbreak 规则）的解析器。
    """
    parser = MarkdownIt("commonmark", _PARSER_OPTIONS)
    # commonmark 预设下 table/strikethrough/linkify 规则默认关闭，须显式启用
    # （linkify 仅设 options 不生效，必须 enable 规则链）
    parser.enable(["table", "strikethrough", "linkify"])
    parser.use(tasklists_plugin)
    _install_source_line_hook(parser)
    _install_indent_preserving_softbreak(parser)
    return parser


def _install_indent_preserving_softbreak(parser: MarkdownIt) -> None:
    """替换 inline 解析的 newline 规则：软换行后的行首空白保留进 token。

    markdown-it 原生 newline 规则在解析期就把下一行行首空格跳过丢弃
    （"skip heading spaces for next line"），渲染层无从恢复——本查看器
    场景（笔记类文档以缩进表达层级）需要保留，故用同签名规则替换：
    与原生行为一致（尾部双空格→hardbreak），唯一差异是跳过下一行行首
    空白这一步改为记录到 softbreak token.content，渲染规则据此输出。
    """
    from markdown_it.rules_inline.state_inline import StateInline
    from markdown_it.common.utils import charStrAt, isStrSpace

    def newline_keep_indent(state: StateInline, silent: bool) -> bool:
        pos = state.pos
        if state.src[pos] != "\n":
            return False
        pmax = len(state.pending) - 1
        maximum = state.posMax

        if not silent:
            if pmax >= 0 and charStrAt(state.pending, pmax) == " ":
                if pmax >= 1 and charStrAt(state.pending, pmax - 1) == " ":
                    ws = pmax - 1
                    while ws >= 1 and charStrAt(state.pending, ws - 1) == " ":
                        ws -= 1
                    state.pending = state.pending[:ws]
                    state.push("hardbreak", "br", 0)
                else:
                    state.pending = state.pending[:-1]
                    state.push("softbreak", "br", 0)
            else:
                state.push("softbreak", "br", 0)

        pos += 1
        # 与原生唯一差异：行首空白不丢弃，保存到 softbreak token（含换行符本身）
        indent_start = pos
        while pos < maximum and isStrSpace(state.src[pos]):
            pos += 1
        if state.tokens and state.tokens[-1].type == "softbreak":
            state.tokens[-1].content = "\n" + state.src[indent_start:pos]
        state.pos = pos
        return True

    parser.inline.ruler.at("newline", newline_keep_indent)

    def softbreak_with_indent(renderer, tokens, idx, options, env):
        # content 为解析期保存的 "\n + 行首空白"；无缩进时为空串（与原生一致输出 <br>）。
        # 回调签名（实测探明）：首参为 renderer 实例，次参为 token 列表
        return "<br />" + getattr(tokens[idx], "content", "")

    parser.add_render_rule("softbreak", softbreak_with_indent)


def _install_source_line_hook(parser: MarkdownIt) -> None:
    """注册源行号注入规则：给每个顶层块级元素标注其在源文本中的起始行（1-based）。

    行号经 data-source-line 属性输出，前端预览据此在块左缘显示，
    实现"渲染内容 ↔ 源码行"的对照；对纯 HTML 展示无副作用。
    代码块（fence）的属性落在其内部 code 标签上，由前端 CSS 适配。
    """

    def inject_source_lines(state) -> None:
        for token in state.tokens:
            if token.map and token.level == 0:
                token.attrSet("data-source-line", str(token.map[0] + 1))

    parser.core.ruler.push("mdviewer_source_line", inject_source_lines)


def convert(markdown_text: str) -> str:
    """把 Markdown 文本渲染为 HTML 片段。

    渲染后处理：**行首空白保留**。HTML 默认折叠行首连续空格，导致笔记类文档
    （缩进表达层级、无 Markdown 列表语法）的缩进在预览中丢失；行首空格已在
    解析期由 newline_keep_indent 规则保留，这里把 <br> 后的普通空格替换为
    不换行空格（U+00A0），预览即还原源文档的缩进层级。
    <pre><code>（代码块）内容整段豁免——pre 内 HTML 不折叠空白，保持原样。

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
        html = _converter.render(markdown_text)
    # 代码块豁免：仅对 <pre>…</pre> 之外的片段做行首空白替换
    parts = _PRE_SPLIT_RE.split(html)
    for i in range(0, len(parts), 2):  # 偶数下标为 pre 外文本
        parts[i] = _PRESERVE_LEADING_SPACES_RE.sub(_replace_leading_spaces, parts[i])
    return "".join(parts)


# 奇数下标捕获组为 <pre>…</pre> 整段（DOTALL 覆盖多行代码块）
_PRE_SPLIT_RE = re.compile(r"(<pre>.*?</pre>)", re.DOTALL)

# 匹配 <br>（含 <br/>、<br />）及其后换行符与行首空白（softbreak 规则输出 "<br />\n    "）。
# 行首空白一次性捕获（不用贪婪前缀拆分，否则待替换空格被 [ \t]* 吞掉只剩 1 个）；
# \u3000 为全角空格
_PRESERVE_LEADING_SPACES_RE = re.compile(r"(<br\s*/?>\n?)((?:[ \t]|\u00a0|\u3000)+)")


def _replace_leading_spaces(match: "re.Match[str]") -> str:
    """把行首空白统一为不换行空格序列，制表符按 4 空格宽度展开。"""
    boundary, spaces = match.group(1), match.group(2)
    expanded = spaces.replace("\t", "    ").replace(" ", "\u00a0")
    return boundary + expanded
