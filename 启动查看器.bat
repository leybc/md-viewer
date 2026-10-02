@echo off
rem 启动 MD 查看器（pythonw 静默运行，不显示控制台窗口；支持把 .md 路径作为参数传入）
start "" pythonw "%~dp0main.py" %*
