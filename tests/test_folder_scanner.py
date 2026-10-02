"""folder_scanner 功能测试：目录树构建、忽略规则与边界（正常路径 + 边界）。"""

from core.folder_scanner import scan_folder


def test_scan_basic_tree_sorted(tmp_path):
    """子目录与 .md 文件正确入树：目录在前、文件在后、按名称排序；非 md 文件被排除。"""
    (tmp_path / "笔记.md").write_text("# n", encoding="utf-8")
    (tmp_path / "附录.md").write_text("# a", encoding="utf-8")
    (tmp_path / "忽略.txt").write_text("x", encoding="utf-8")
    sub = tmp_path / "子目录"
    sub.mkdir()
    (sub / "深层.md").write_text("# d", encoding="utf-8")

    result = scan_folder(str(tmp_path))
    assert result.ok
    assert result.file_count == 3
    root = result.root
    assert root.is_dir
    # 排序：两个目录级（无）→ 文件按名称：笔记 / 附录（按小写拼音码点，笔<附）
    names = [child.name for child in root.children]
    assert names[0] == "子目录"  # 目录排最前
    md_names = [child.name for child in root.children if not child.is_dir]
    assert md_names == ["笔记.md", "附录.md"]
    # 深层文件可从子节点到达
    deep = [c for c in root.children if c.is_dir][0].children
    assert deep[0].name == "深层.md"


def test_scan_ignores_hidden_and_dependency_dirs(tmp_path):
    """.git / node_modules / __pycache__ 等目录中的 md 不被收集。"""
    for ignored in (".git", "node_modules", "__pycache__"):
        d = tmp_path / ignored
        d.mkdir()
        (d / "ghost.md").write_text("# x", encoding="utf-8")
    (tmp_path / "可见.md").write_text("# y", encoding="utf-8")

    result = scan_folder(str(tmp_path))
    assert result.ok and result.file_count == 1


def test_scan_empty_dir(tmp_path):
    """边界：空目录返回成功且空树。"""
    result = scan_folder(str(tmp_path))
    assert result.ok
    assert result.root.children == []
    assert result.file_count == 0


def test_scan_nonexistent_dir(tmp_path):
    """边界：不存在的目录返回失败与原因。"""
    result = scan_folder(str(tmp_path / "ghost"))
    assert not result.ok
    assert "目录不存在" in result.error


def test_scan_markdown_extension(tmp_path):
    """.markdown 扩展名同样收集，.markdn 等不收。"""
    (tmp_path / "a.markdown").write_text("# a", encoding="utf-8")
    (tmp_path / "b.markdn").write_text("# b", encoding="utf-8")
    result = scan_folder(str(tmp_path))
    assert result.file_count == 1
