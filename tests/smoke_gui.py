"""GUI 冒烟测试（独立脚本，pytest 不自动收集：文件名不以 test_ 开头）。

验证目标：主窗口能启动、pywebview 初始化不崩溃、命令行参数加载不崩溃。

用法（在项目根目录）：
    python tests/smoke_gui.py

原理：以 MD_VIEWER_SMOKE=1 环境变量启动 main.py（程序将在窗口加载后 4 秒
自动退出），等待子进程退出并检查退出码。两轮：无参数、带临时 .md 文件参数。
"""

import os
import subprocess
import sys
import tempfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SMOKE_TIMEOUT_SECONDS = 40


def run_smoke(label: str, args: list[str]) -> bool:
    """启动一轮冒烟并等待其自退出。

    Args:
        label: 本轮描述（用于输出）。
        args: 传给 main.py 的命令行参数。

    Returns:
        是否通过（进程在超时内自行退出且退出码为 0）。
    """
    # 在系统环境基础上增量覆盖：整替 env 会丢 PATH/SystemRoot，导致 .NET/WebView2 初始化失败
    env = {**os.environ, "PYTHONIOENCODING": "utf-8", "MD_VIEWER_SMOKE": "1"}
    print(f"[smoke] {label} 启动：{args or '(无参数)'}")
    process = subprocess.Popen(
        [sys.executable, str(PROJECT_ROOT / "main.py"), *args],
        cwd=str(PROJECT_ROOT),
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        code = process.wait(timeout=SMOKE_TIMEOUT_SECONDS)
    except subprocess.TimeoutExpired:
        process.kill()
        print(
            f"[smoke] {label} 失败：{SMOKE_TIMEOUT_SECONDS}s 内未自退出（窗口未启动或卡死）"
        )
        return False
    if code != 0:
        print(f"[smoke] {label} 失败：退出码 {code}")
        return False
    print(f"[smoke] {label} 通过")
    return True


def main() -> int:
    """顺序执行两轮冒烟，返回进程退出码（0 全部通过）。"""
    results = [run_smoke("无参数启动", [])]

    with tempfile.TemporaryDirectory() as temp_dir:
        sample = Path(temp_dir) / "sample.md"
        sample.write_text("# 冒烟测试\n\n- 项目一\n- 项目二\n", encoding="utf-8")
        results.append(run_smoke("带 .md 参数启动", [str(sample)]))

    all_ok = all(results)
    print(f"[smoke] 结果：{'全部通过' if all_ok else '存在失败'}")
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
