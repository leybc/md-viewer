"""文件夹扫描模块。

职责：递归扫描指定目录，构建"仅包含子目录与 Markdown 文件"的树结构，
供左侧导航树展示。包含资源保护：跳过隐藏/系统目录、限制递归深度与文件总数。
"""

import logging
import os
from dataclasses import dataclass, field

from core.file_service import MARKDOWN_SUFFIXES

logger = logging.getLogger(__name__)

# 扫描时忽略的目录名（隐藏目录 / 系统目录 / 依赖目录——与文档浏览无关且可能巨大）
IGNORED_DIR_NAMES = {
    ".git",
    "__pycache__",
    ".venv",
    "node_modules",
    "$RECYCLE.BIN",
    "System Volume Information",
}

# 递归深度上限：防止异常深目录导致栈溢出或卡顿
MAX_SCAN_DEPTH = 12
# 文件总数上限：超过即停止收集并在结果中标记 truncated（导航树够用即可，保护界面流畅）
MAX_FILE_COUNT = 2000


@dataclass
class FileNode:
    """文件树节点。

    Attributes:
        name: 显示名称（文件或目录名，不含路径）。
        path: 绝对路径。
        is_dir: 是否为目录。
        children: 子节点（仅目录有）。
    """

    name: str
    path: str
    is_dir: bool
    children: list["FileNode"] = field(default_factory=list)

    def to_dict(self) -> dict:
        """转为可传递给前端 JSON 的字典结构。"""
        return {
            "name": self.name,
            "path": self.path,
            "is_dir": self.is_dir,
            "children": [child.to_dict() for child in self.children],
        }


@dataclass
class ScanResult:
    """目录扫描结果。

    Attributes:
        ok: 是否扫描成功。
        root: 根节点（ok=True 时有效）。
        file_count: 收集到的 Markdown 文件总数。
        truncated: 是否因达到 MAX_FILE_COUNT 而提前截断。
        error: 失败原因描述；成功时为空字符串。
    """

    ok: bool
    root: FileNode | None = None
    file_count: int = 0
    truncated: bool = False
    error: str = ""


def scan_folder(root_path: str) -> ScanResult:
    """递归扫描目录，返回仅含子目录与 Markdown 文件的树。

    Args:
        root_path: 要扫描的文件夹绝对路径。

    Returns:
        ScanResult：成功时 root 为树根（目录在前、按名称排序）；
        失败时 ok=False 且 error 说明原因。
    """
    if not os.path.isdir(root_path):
        return ScanResult(False, error="目录不存在")

    state = {"count": 0, "truncated": False}

    def build_dir(dir_path: str, depth: int) -> FileNode:
        node = FileNode(
            name=os.path.basename(dir_path) or dir_path, path=dir_path, is_dir=True
        )
        try:
            entries = list(os.scandir(dir_path))
        except OSError as exc:
            logger.warning("目录不可读 %s：%s", dir_path, exc)
            return node

        sub_dirs: list[FileNode] = []
        md_files: list[FileNode] = []
        for entry in entries:
            try:
                entry_is_dir = entry.is_dir(follow_symlinks=False)
            except OSError:
                entry_is_dir = False
            if entry_is_dir:
                # 跳过忽略目录；符号链接目录不深入（防循环）
                if entry.name in IGNORED_DIR_NAMES or entry.is_symlink():
                    continue
                if depth >= MAX_SCAN_DEPTH:
                    state["truncated"] = True
                    continue
                sub_dirs.append(build_dir(entry.path, depth + 1))
            elif os.path.splitext(entry.name)[1].lower() in MARKDOWN_SUFFIXES:
                if state["count"] >= MAX_FILE_COUNT:
                    state["truncated"] = True
                    break
                state["count"] += 1
                md_files.append(
                    FileNode(name=entry.name, path=entry.path, is_dir=False)
                )

        # 目录在前、文件在后，各自按名称排序，保证导航顺序稳定
        sub_dirs.sort(key=lambda n: n.name.lower())
        md_files.sort(key=lambda n: n.name.lower())
        node.children = sub_dirs + md_files
        return node

    logger.info("扫描目录 %s", root_path)
    root = build_dir(root_path, 0)
    if state["truncated"]:
        logger.warning(
            "目录 %s 扫描被截断（文件数达 %d 上限）", root_path, MAX_FILE_COUNT
        )
    return ScanResult(
        True, root=root, file_count=state["count"], truncated=state["truncated"]
    )
