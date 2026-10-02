"""独立 HTML 导出模块。

职责：把渲染好的 Markdown 正文包装成一个"双击即可在浏览器打开"的
完整独立 HTML 文件：内联浅色阅读样式，不依赖任何外部资源。
"""

import logging
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

# 导出页的阅读样式：与主界面浅色主题一致的字体、代码块与表格观感。
# 内联在 <style> 中，保证导出文件单文件自包含
_READER_CSS = """\
body{margin:0;background:#f6f7f9;color:#24292f;
font-family:"Microsoft YaHei","Segoe UI",-apple-system,sans-serif;
font-size:15px;line-height:1.75;}
main{max-width:860px;margin:0 auto;padding:40px 32px;background:#ffffff;
min-height:100vh;box-sizing:border-box;}
h1,h2,h3,h4,h5,h6{line-height:1.4;margin:1.2em 0 0.6em;font-weight:600;}
h1{font-size:1.9em;border-bottom:1px solid #e1e4e8;padding-bottom:0.3em;}
h2{font-size:1.5em;border-bottom:1px solid #e1e4e8;padding-bottom:0.3em;}
code{background:#f0f1f3;border-radius:4px;padding:0.15em 0.4em;
font-family:Consolas,"Courier New",monospace;font-size:0.9em;}
pre{background:#f6f8fa;border:1px solid #e1e4e8;border-radius:6px;
padding:12px 14px;overflow:auto;}
pre code{background:none;padding:0;}
blockquote{margin:0.8em 0;padding:0.2em 1em;border-left:4px solid #d0d7de;
color:#57606a;background:#fafbfc;}
table{border-collapse:collapse;margin:1em 0;}
th,td{border:1px solid #d0d7de;padding:6px 12px;}
th{background:#f6f8fa;}
img{max-width:100%;}
a{color:#0969da;text-decoration:none;}
a:hover{text-decoration:underline;}
hr{border:none;border-top:1px solid #e1e4e8;margin:1.5em 0;}
li.task-list-item{list-style:none;margin-left:-1.4em;}
"""


@dataclass
class ExportResult:
    """导出结果。

    Attributes:
        ok: 是否导出成功。
        error: 失败原因描述；成功时为空字符串。
    """

    ok: bool
    error: str = ""


def build_standalone_html(
    title: str, body_html: str, base_dir: str | None = None
) -> str:
    """构建完整独立 HTML 文档文本。

    Args:
        title: 文档标题（显示在浏览器标签页，一般取文件名）。
        body_html: Markdown 渲染出的正文 HTML 片段。
        base_dir: 正文内相对路径（图片等）的基准目录；None 时不写 <base>。

    Returns:
        完整 HTML 文档字符串（UTF-8 文本）。
    """
    base_tag = ""
    if base_dir:
        # <base> 指向源 Markdown 所在目录，导出文件里的相对图片仍可正常显示
        base_tag = f'<base href="{Path(base_dir).as_uri()}/">'
    return (
        "<!DOCTYPE html>\n"
        '<html lang="zh-CN">\n'
        "<head>\n"
        '<meta charset="utf-8">\n'
        f"<title>{title}</title>\n"
        f"{base_tag}\n"
        f"<style>\n{_READER_CSS}</style>\n"
        "</head>\n"
        "<body>\n<main>\n"
        f"{body_html}\n"
        "</main>\n</body>\n</html>\n"
    )


def export_to_file(
    out_path: str, title: str, body_html: str, base_dir: str | None = None
) -> ExportResult:
    """把独立 HTML 写入磁盘文件。

    Args:
        out_path: 输出文件路径（一般来自保存对话框）。
        title: 文档标题。
        body_html: 正文 HTML 片段。
        base_dir: 相对路径基准目录；None 时不写 <base>。

    Returns:
        ExportResult：ok 表示是否成功，失败时 error 说明原因。
    """
    try:
        Path(out_path).write_text(
            build_standalone_html(title, body_html, base_dir), encoding="utf-8"
        )
    except OSError as exc:
        logger.exception("导出 HTML 失败 %s", out_path)
        return ExportResult(False, error=f"导出失败：{exc}")
    logger.info("导出 HTML 成功 %s", out_path)
    return ExportResult(True)
