"""html_exporter 功能测试：独立 HTML 构建与导出（正常路径 + 边界）。"""

from core.html_exporter import build_standalone_html, export_to_file


def test_build_contains_shell_and_body():
    """构建结果包含 DOCTYPE、样式与正文片段，正文位于 main 容器内。"""
    html = build_standalone_html("测试标题", "<h1>正文</h1>")
    assert html.startswith("<!DOCTYPE html>")
    assert "<title>测试标题</title>" in html
    assert "<style>" in html and "background:#f6f7f9" in html
    assert "<h1>正文</h1>" in html


def test_build_with_base_dir():
    """提供基准目录时生成 <base>，指向该目录的 file URI。"""
    html = build_standalone_html("t", "<p>x</p>", base_dir=r"D:\docs\notes")
    assert '<base href="file:///D:/docs/notes/">' in html


def test_build_without_base_dir():
    """不提供基准目录时不生成 <base> 标签。"""
    assert "<base " not in build_standalone_html("t", "<p>x</p>")


def test_export_to_file_roundtrip(tmp_path):
    """导出到磁盘后读回内容与构建结果一致。"""
    out = tmp_path / "out.html"
    result = export_to_file(str(out), "标题", "<p>内容</p>", base_dir=str(tmp_path))
    assert result.ok
    text = out.read_text(encoding="utf-8")
    assert "<p>内容</p>" in text
    assert f'<base href="{tmp_path.as_uri()}/">' in text


def test_export_to_invalid_path_fails():
    """边界：输出路径的父目录不存在时返回失败与原因。"""
    result = export_to_file(r"Z:\__no_such__\out.html", "t", "<p>x</p>")
    assert not result.ok
    assert "导出失败" in result.error
