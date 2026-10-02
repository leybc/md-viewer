"""文件读写服务模块。

职责：Markdown 文件的读取与保存，包含：
- 编码识别：UTF-8（含 BOM / 不含 BOM）优先，失败回退 GBK，最终容错解码兜底；
- 大小保护：超过 MAX_FILE_BYTES 的文件拒绝加载（防止一次性载入内存卡死界面）；
- 保存：统一以 UTF-8（无 BOM）写回，Windows / Linux 通用。
"""

import codecs
import logging
import os
from dataclasses import dataclass
from pathlib import Path

# 单文件加载上限：10MB。超过该大小的 Markdown 已超出"文档"范畴，
# 强行渲染会导致 WebView 内存暴涨与界面卡顿（资源与稳定性保护铁律）
MAX_FILE_BYTES = 10 * 1024 * 1024

# 本程序可识别的 Markdown 扩展名（小写）
MARKDOWN_SUFFIXES = {".md", ".markdown"}

logger = logging.getLogger(__name__)


@dataclass
class FileReadResult:
    """文件读取结果。

    Attributes:
        ok: 是否读取成功。
        content: 文件文本内容；失败时为空字符串。
        encoding: 实际使用的解码名称；失败时为空字符串。
        size_bytes: 文件字节数；无法获取时为 0。
        error: 失败原因描述；成功时为空字符串。
    """

    ok: bool
    content: str = ""
    encoding: str = ""
    size_bytes: int = 0
    error: str = ""


@dataclass
class FileWriteResult:
    """文件写入结果。

    Attributes:
        ok: 是否写入成功。
        error: 失败原因描述；成功时为空字符串。
    """

    ok: bool
    error: str = ""


def is_markdown_file(path: str) -> bool:
    """判断给定路径是否为本程序支持的 Markdown 文件（按扩展名）。

    Args:
        path: 任意文件路径。

    Returns:
        扩展名为 .md / .markdown（不区分大小写）时返回 True。
    """
    return Path(path).suffix.lower() in MARKDOWN_SUFFIXES


def read_text_file(path: str) -> FileReadResult:
    """读取 Markdown 文本文件（带编码识别与大小保护）。

    Args:
        path: 文件路径。

    Returns:
        FileReadResult：成功时 ok=True 并携带文本与编码名；
        失败时 ok=False 且 error 说明原因（文件不存在 / 过大 / 读取错误）。
    """
    try:
        if not os.path.isfile(path):
            return FileReadResult(False, error="文件不存在")
        size = os.path.getsize(path)
        if size > MAX_FILE_BYTES:
            message = (
                f"文件过大：{size} 字节，超过 {MAX_FILE_BYTES // (1024 * 1024)}MB 上限"
            )
            logger.warning("拒绝加载大文件 %s：%s", path, message)
            return FileReadResult(False, size_bytes=size, error=message)
        raw = Path(path).read_bytes()
    except OSError as exc:
        logger.exception("读取文件失败 %s", path)
        return FileReadResult(False, error=f"读取失败：{exc}")

    encoding, text = decode_bytes(raw)
    logger.info("读取文件成功 %s（%s，%d 字节）", path, encoding, len(raw))
    return FileReadResult(True, content=text, encoding=encoding, size_bytes=len(raw))


def decode_bytes(raw: bytes) -> tuple[str, str]:
    """把原始字节按"UTF-8 优先、GBK 回退、容错兜底"策略解码为文本。

    解码后统一把 CRLF / CR 规范化为 LF：与浏览器 textarea 的 API 值规范一致，
    保证"读取 → 编辑 → 保存 → 再读取"内容完全一致，避免行尾差分噪音。

    Args:
        raw: 文件原始字节内容。

    Returns:
        (编码名, 解码后的文本) 二元组。编码名用于界面提示。
    """
    # UTF-16 带 BOM 的文件（极少见，但资源管理器导出类文本可能遇到）
    if raw.startswith((codecs.BOM_UTF16_LE, codecs.BOM_UTF16_BE)):
        encoding, text = "utf-16", raw.decode("utf-16")
    else:
        # utf-8-sig 会自动剥除 UTF-8 BOM；严格模式失败即回退 GBK
        try:
            encoding, text = "utf-8", raw.decode("utf-8-sig")
        except UnicodeDecodeError:
            try:
                encoding, text = "gbk", raw.decode("gbk")
            except UnicodeDecodeError:
                # 连 GBK 都解不了（如二进制杂讯）：容错解码保证界面不崩溃，替换符标记坏字节
                encoding, text = "gbk(容错)", raw.decode("gbk", errors="replace")
    # 行尾规范化：\r\n 与孤立 \r 统一为 \n
    return encoding, text.replace("\r\n", "\n").replace("\r", "\n")


def write_text_file(path: str, content: str) -> FileWriteResult:
    """把文本以 UTF-8（无 BOM）写回文件。

    Args:
        path: 目标文件路径（通常为当前正在查看的 .md 文件）。
        content: 要保存的完整文本。

    Returns:
        FileWriteResult：ok 表示是否成功，失败时 error 说明原因。
    """
    try:
        Path(path).write_text(content, encoding="utf-8")
    except OSError as exc:
        logger.exception("保存文件失败 %s", path)
        return FileWriteResult(False, error=f"保存失败：{exc}")
    logger.info("保存文件成功 %s（%d 字符）", path, len(content))
    return FileWriteResult(True)
