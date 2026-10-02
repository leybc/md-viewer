# ARCHITECTURE — md-viewer（MD 文件查看器）

> 状态：计划已于 2026-10-02 经用户批准（ExitPlanMode）。本文件为批准计划的书面落档，编码阶段严格照此执行；变更须回到设计阶段并告知用户。

## 一、需求摘要（用户已确认版本）

自用 Windows 桌面 Markdown 查看器：

- 浅色界面；左侧文件夹树导航（递归列出所选文件夹下全部 .md，点击切换阅读）；
- 右侧渲染 Markdown：标题、段落、粗体/斜体/删除线、行内代码、围栏代码块、引用（嵌套）、有序/无序列表（嵌套）、任务列表、表格、链接、图片（相对路径）、水平线、HTML 转义；
- 源码编辑模式（编辑保存后预览自动刷新）；
- 导出为带样式的独立 HTML 文件；
- 拖拽 .md 文件打开；UTF-8（含/不含 BOM）优先、GBK 回退的编码识别；超过 10MB 的大文件拒绝加载并提示；
- 程序图标（Markdown 风格）；支持 .md"属性 → 打开方式"关联后双击直达查看；
- 运行形态：`python main.py` 或双击"启动查看器.bat"（自用，不打包）；
- 尽量零落盘：pywebview `private_mode=True`（WebView2 内存模式，已查证为默认值）。

## 二、决策表

| # | 决策项 | 结论 | 理由 / 来源 |
|---|---|---|---|
| 1 | 编程语言 | Python（3.11.9，本机 PATH 现成） | 用户确认；知识库适用版本 3.10+ 匹配 |
| 2 | GUI 方案 | pywebview 6.2.1（Windows 后端 EdgeChromium/WebView2） | 用户确认覆盖项：知识库 GUI 首选 Tkinter，但 Tkinter 无法高质量渲染 Markdown；pywebview 用系统 WebView2 渲染 HTML/CSS，最贴合"查看器"本质且安装轻量 |
| 3 | Markdown 解析 | markdown-it-py 4.2.0（commonmark preset）+ `enable(["table","strikethrough"])` + mdit-py-plugins `tasklists_plugin` | CommonMark 规范级实现，本地查证渲染输出正确 |
| 4 | 编程范式 | 逻辑层纯函数为主 + 少量类（Api 桥、服务类）；界面层薄 | 知识库默认（小型项目） |
| 5 | 界面/代码分离 | 分离：`core/` 禁止 import webview，全部逻辑可独立 pytest；`ui/` 只做输入收集与结果展示 | 知识库默认 |
| 6 | 命名风格 | snake_case（模块/函数/变量）、PascalCase（类）、UPPER_SNAKE_CASE（常量）、私有成员前缀下划线 | 知识库默认 |
| 7 | 注释 | 完整中文注释；公开模块/类/函数写 Google 风格 docstring | 用户确认 |
| 8 | 界面主色 | 浅色主题 | 用户确认 |
| 9 | 测试 | pytest（core 层全覆盖 + GUI 冒烟脚本） | 知识库默认 |
| 10 | 质量工具链 | ruff check → black --check → py_compile → pytest | 知识库 quality.md |
| 11 | 日志 | logging 标准库：控制台 + logs/app.log | 知识库默认；开发版必须有日志（第五章第 6 条） |
| 12 | Git | 开启，每阶段验收后提交 | 用户确认 |
| 13 | 打包 | **PyInstaller 6.22.2 单文件 exe（onefile + windowed + 图标）**：`dist/MD查看器.exe`（约 19MB），界面资源与运行时经 `--add-data` / `--collect-all webview clr_loader pythonnet` 打入；代码以 `sys.frozen/_MEIPASS` 适配双态路径 | **用户 2026-10-02 明确要求交付 exe**（推翻原"自用不打包"决策）；onefile 启动时向 %TEMP% 自解压、退出自动清理，已向用户如实说明 |
| 14 | 零落盘 | `webview.start(private_mode=True)`（默认值已查证）；日志文件为本机开发日志，非程序数据 | 用户诉求"不释放临时文件" |
| 15 | 程序图标 | `assets/icon.ico`（Markdown 风格 M↓ 图标），由 `tools/make_icon.py`（Pillow）生成，经 `webview.start(icon=...)` 挂载窗口 | 用户补充需求（2026-10-02） |
| 16 | 文件关联启动 | 命令行参数接收 .md 路径（`main.py <文件>`），配合 `启动查看器.bat`（`%*` 透传）；用户在 .md"属性→打开方式"中选择该 bat 后双击直达 | 用户补充需求（2026-10-02）；冒烟已覆盖参数加载链路 |

## 三、模块划分与目录结构

```
projects/md-viewer/
├── main.py                  # 入口：配置日志 → 创建窗口（加载 ui/static/index.html）→ webview.start
├── ui/
│   ├── __init__.py
│   ├── api.py               # pywebview js_api 桥（薄层：收集输入 → 调 core → 返回结果字典）
│   └── static/
│       ├── index.html       # 界面骨架：顶栏 / 左侧文件树 / 右侧预览与编辑
│       ├── style.css        # 浅色主题
│       └── app.js           # 界面交互：树渲染、文件切换、编辑/预览模式、拖拽、导出与保存
├── core/
│   ├── __init__.py
│   ├── md_converter.py      # Markdown → HTML 正文（markdown-it-py 封装）
│   ├── file_service.py      # 读取/保存：编码识别（UTF-8→GBK 回退）、大小保护（MAX_FILE_BYTES=10MB）
│   ├── folder_scanner.py    # 递归扫描目录 → .md 文件树（相对路径 + 排序）
│   └── html_exporter.py     # 导出独立 HTML（内联浅色样式，双击即可在浏览器打开）
├── tests/
│   ├── test_md_converter.py
│   ├── test_file_service.py
│   ├── test_folder_scanner.py
│   ├── test_html_exporter.py
│   └── smoke_gui.py         # GUI 冒烟：子进程启动 main.py，3 秒存活即通过
├── requirements.txt         # 固定版本依赖清单
├── .gitignore               # __pycache__/ logs/ backup/ .pytest_cache/ 等
├── README.md
├── ARCHITECTURE.md
└── 启动查看器.bat
```

### 依赖（requirements.txt，阿里/清华镜像安装）

```
pywebview==6.2.1
markdown-it-py==4.2.0
mdit-py-plugins==0.6.1
```

开发工具（不入 requirements.txt，本机已装）：pytest 8.4.1、ruff 0.14.14、black 25.1.0。

## 四、数据流 / 交互说明

1. **打开文件夹**：前端 `app.js` → `window.pywebview.api.open_folder()` → `api.py` 调 pywebview `create_file_dialog(FOLDER_DIALOG)` → `core.folder_scanner.scan_folder()` 返回文件树 → 前端渲染左侧树。
2. **读取文件**：点击树节点 → `api.read_file(path)` → `core.file_service.read_text_file()`（编码识别 + 大小保护）→ 返回 `{ok, content, error}` → 前端 `core.md_converter.convert()` 经 `api.convert_markdown()` 转 HTML → 注入预览区（`<base href>` 指向 md 所在目录，解决相对图片）。
3. **编辑保存**：编辑模式 textarea → 保存（按钮 / Ctrl+S）→ `api.save_file(path, content)` → `core.file_service.write_text_file()`（UTF-8 无 BOM 写回）→ 自动重新渲染预览。
4. **导出 HTML**：`api.export_html(path)` → `core.html_exporter.export()`（完整独立 HTML：内联样式 + 正文）→ pywebview SAVE_DIALOG 选保存位置。
5. **拖拽打开**：pywebview drop 事件（`webview.settings['ALLOW_DOWNLOADS']` 无关；使用 window 级 drag 事件取文件路径）→ 走读取渲染流程。
6. **命令行参数**：`python main.py [某个.md或目录]` 启动时直接加载（关联打开场景）。

### 错误处理约定

- `core/` 各函数返回结果不抛 GUI 异常；统一返回 `(ok, data, error)` 语义（用 dataclass `Result`）。
- 界面层捕获后以界面提示呈现；异常一律 `logging.exception` 记录。
- 禁止裸 except；捕获具体异常类型（OSError、UnicodeDecodeError、PermissionError 等）。
