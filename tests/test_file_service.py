"""file_service 功能测试：编码识别、大小保护、读写回环（正常路径 + 边界）。"""

from core.file_service import (
    MAX_FILE_BYTES,
    decode_bytes,
    is_markdown_file,
    read_text_file,
    write_text_file,
)


def test_read_utf8_no_bom(tmp_path):
    """无 BOM 的 UTF-8 中文文件正确读取。"""
    target = tmp_path / "a.md"
    target.write_text("# 中文标题\n正文", encoding="utf-8")
    result = read_text_file(str(target))
    assert result.ok
    assert result.content == "# 中文标题\n正文"
    assert result.encoding == "utf-8"


def test_read_utf8_with_bom(tmp_path):
    """带 BOM 的 UTF-8 文件读取后内容不含 BOM 字符。"""
    target = tmp_path / "b.md"
    target.write_bytes(b"\xef\xbb\xbf# BOM \xe6\xa0\x87\xe9\xa2\x98\n")
    result = read_text_file(str(target))
    assert result.ok
    assert result.content == "# BOM 标题\n"
    assert result.encoding == "utf-8"


def test_read_gbk_fallback(tmp_path):
    """GBK 编码中文文件（UTF-8 严格解码必失败）回退为 GBK 读取。"""
    target = tmp_path / "c.md"
    target.write_bytes("# GBK 文档\n".encode("gbk"))
    result = read_text_file(str(target))
    assert result.ok
    assert result.content == "# GBK 文档\n"
    assert result.encoding == "gbk"


def test_read_file_not_exist(tmp_path):
    """边界：不存在的路径返回失败与原因。"""
    result = read_text_file(str(tmp_path / "ghost.md"))
    assert not result.ok
    assert "文件不存在" in result.error


def test_read_directory_path_rejected(tmp_path):
    """边界：传入目录路径返回失败。"""
    result = read_text_file(str(tmp_path))
    assert not result.ok


def test_read_oversize_file_rejected(tmp_path):
    """边界：超过 10MB 的文件拒绝加载并提示，避免内存暴涨。"""
    target = tmp_path / "big.md"
    target.write_bytes(b"x" * (MAX_FILE_BYTES + 1))
    result = read_text_file(str(target))
    assert not result.ok
    assert "文件过大" in result.error


def test_decode_bytes_invalid_gbk_tolerated():
    """边界：既非 UTF-8 也非严格 GBK 的字节流走容错解码，不抛异常。

    说明：不能用 \\xff\\xfe 开头的序列做用例——那会撞上 UTF-16LE BOM 分支。
    """
    encoding, text = decode_bytes(b"abc\xff\x10def")
    assert text  # 有输出（可能含替换符）
    assert encoding.startswith("gbk")


def test_write_and_read_roundtrip_utf8_no_bom(tmp_path):
    """保存后再读取内容一致，且写盘为 UTF-8 无 BOM。"""
    target = tmp_path / "round.md"
    write_result = write_text_file(str(target), "# 回环测试\n内容")
    assert write_result.ok
    raw = target.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf")  # 无 BOM
    read_result = read_text_file(str(target))
    assert read_result.ok and read_result.content == "# 回环测试\n内容"


def test_write_to_invalid_path_fails():
    """边界：写入不存在目录中的文件返回失败与原因。"""
    result = write_text_file("Z:\\__no_such_dir__\\out.md", "内容")
    assert not result.ok
    assert "保存失败" in result.error


def test_is_markdown_file():
    """扩展名判断：.md / .markdown 不区分大小写，其他扩展名返回 False。"""
    assert is_markdown_file("a.md")
    assert is_markdown_file("B.MD")
    assert is_markdown_file("c.Markdown")
    assert not is_markdown_file("d.txt")
    assert not is_markdown_file("e")
