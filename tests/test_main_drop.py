"""main 模块拖拽分发逻辑单测（不启动 GUI，mock 窗口对象）。"""

from unittest.mock import MagicMock, patch

import main


def _make_window() -> MagicMock:
    window = MagicMock()
    window.evaluate_js.return_value = None
    return window


def _event(files) -> dict:
    return {"dataTransfer": {"files": files}}


def test_drop_markdown_calls_load_from_path():
    """拖入 .md 文件：通知前端按完整路径加载。"""
    window = _make_window()
    with patch.object(main.webview, "windows", [window]):
        main._on_files_dropped(_event([{"pywebviewFullPath": r"D:\docs\note.md"}]))
    js = window.evaluate_js.call_args[0][0]
    assert "loadFromPath" in js
    assert "note.md" in js


def test_drop_markdown_uppercase_extension():
    """边界：扩展名大小写混合（.MD）同样被接受。"""
    window = _make_window()
    with patch.object(main.webview, "windows", [window]):
        main._on_files_dropped(_event([{"pywebviewFullPath": r"D:\docs\NOTE.MD"}]))
    js = window.evaluate_js.call_args[0][0]
    assert "loadFromPath" in js


def test_drop_non_markdown_shows_hint():
    """拖入非 Markdown 文件：前端收到提示而不加载。"""
    window = _make_window()
    with patch.object(main.webview, "windows", [window]):
        main._on_files_dropped(_event([{"pywebviewFullPath": r"D:\docs\pic.txt"}]))
    js = window.evaluate_js.call_args[0][0]
    assert "setStatus" in js
    assert "loadFromPath" not in js


def test_drop_empty_or_missing_files_noop():
    """边界：无文件数据（空列表 / 缺 dataTransfer）时不产生任何前端调用。"""
    window = _make_window()
    with patch.object(main.webview, "windows", [window]):
        main._on_files_dropped(_event([]))
        main._on_files_dropped({"dataTransfer": {}})
    window.evaluate_js.assert_not_called()


def test_drop_skips_non_md_takes_first_md():
    """边界：混合拖入时跳过非 md，取第一个 md 文件。"""
    window = _make_window()
    files = [
        {"name": "a.txt", "pywebviewFullPath": r"D:\x\a.txt"},
        {"name": "b.md", "pywebviewFullPath": r"D:\x\b.md"},
        {"name": "c.md", "pywebviewFullPath": r"D:\x\c.md"},
    ]
    with patch.object(main.webview, "windows", [window]):
        main._on_files_dropped(_event(files))
    js = window.evaluate_js.call_args[0][0]
    assert "b.md" in js
    assert "a.txt" not in js and "c.md" not in js


def test_drop_without_path_attribute_ignored():
    """边界：事件项缺少 pywebviewFullPath（路径通道未生效）时不崩溃不加载。"""
    window = _make_window()
    with patch.object(main.webview, "windows", [window]):
        main._on_files_dropped(_event([{"name": "note.md"}]))
    window.evaluate_js.assert_not_called()
