"""md_converter 功能测试：覆盖 GFM 常用元素的渲染（正常路径 + 边界）。"""

from core.md_converter import convert


def test_convert_headings_h1_to_h6():
    """六级标题分别渲染为 h1~h6 标签。"""
    md_text = "\n".join(f"{'#' * level} 标题{level}" for level in range(1, 7))
    html = convert(md_text)
    for level in range(1, 7):
        assert f"<h{level}>标题{level}</h{level}>" in html


def test_convert_bold_italic_strikethrough():
    """粗体、斜体、删除线渲染为对应标签（markdown-it 删除线输出 HTML5 的 s 标签）。"""
    html = convert("**粗体** *斜体* ~~删除~~")
    assert "<strong>粗体</strong>" in html
    assert "<em>斜体</em>" in html
    assert "<s>删除</s>" in html


def test_convert_inline_code_and_code_block():
    """行内代码与围栏代码块渲染，代码内容不被当作 Markdown 解析。"""
    html = convert(
        "行内 `code_here` 代码\n\n```python\n# not_heading = 1\nprint(1)\n```\n"
    )
    assert "<code>code_here</code>" in html
    assert "<pre>" in html
    assert "# not_heading = 1" in html


def test_convert_blockquote_nested():
    """引用块渲染，嵌套引用保留层级。"""
    html = convert("> 第一层\n>> 第二层")
    assert "<blockquote>" in html
    assert "第一层" in html
    assert "第二层" in html


def test_convert_lists_ordered_unordered_nested():
    """有序、无序与嵌套列表渲染为嵌套 ul/ol。"""
    html = convert("- 甲\n- 乙\n  - 乙一\n\n1. 第一\n2. 第二")
    assert "<ul>" in html and "<ol>" in html
    assert "乙一" in html


def test_convert_task_list():
    """任务列表渲染为带复选框的任务项。"""
    html = convert("- [x] 已完成\n- [ ] 未完成")
    assert "task-list-item" in html
    assert "已完成" in html and "未完成" in html


def test_convert_table():
    """GFM 管道表格渲染为 table/thead/tbody。"""
    html = convert("| 列A | 列B |\n| --- | --- |\n| 1 | 2 |")
    assert "<table>" in html
    assert "<th>列A</th>" in html
    assert "<td>1</td>" in html


def test_convert_link_and_autolink():
    """显式链接渲染为 a 标签；裸 URL 自动转为链接。"""
    html = convert("[文本](https://example.com) 与 https://auto.link")
    assert '<a href="https://example.com">文本</a>' in html
    assert '<a href="https://auto.link"' in html


def test_convert_image():
    """图片语法渲染为 img 标签并保留相对路径。"""
    html = convert("![截图](images/shot.png)")
    assert '<img src="images/shot.png"' in html
    assert 'alt="截图"' in html


def test_convert_horizontal_rule():
    """水平线渲染为 hr 标签。"""
    assert "<hr" in convert("上\n\n---\n\n下")


def test_convert_embedded_html_rendered():
    """内嵌 HTML 标签按原样渲染（html=True，查看器体验优先）。"""
    assert "<b>加粗</b>" in convert("<b>加粗</b>")


def test_convert_empty_and_blank():
    """边界：空字符串与纯空白文本都返回空或纯空白 HTML，不抛异常。"""
    assert convert("") == ""
    assert convert("   \n  \n") == ""


def test_convert_no_trailing_newline():
    """边界：结尾无换行符的文本正常渲染。"""
    assert "<h1>尾行</h1>" in convert("# 尾行")
