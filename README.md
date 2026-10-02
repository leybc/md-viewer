# md-viewer — MD 文件查看器

自用 Windows 桌面 Markdown 查看器：左侧文件夹树导航、右侧渲染预览、源码编辑、导出 HTML、拖拽打开、双击 .md 关联直达。

技术栈：Python 3.10+ / pywebview（系统 WebView2 渲染）/ markdown-it-py（CommonMark + GFM 扩展）。

## 环境要求

- Windows 10 / 11（需自带 WebView2 Runtime，系统一般已内置；缺失时从微软官网"Evergreen WebView2 Runtime"安装）
- Python 3.10 及以上（本机 3.11.9 验证通过）

## 安装

```bat
cd projects\md-viewer
pip install -r requirements.txt
```

依赖安装建议使用国内镜像（阿里源）：

```bat
pip install -r requirements.txt -i https://mirrors.aliyun.com/pypi/simple/
```

## 使用方法

### 启动（三选一）

- **双击 `dist\MD查看器.exe`**（推荐；单文件约 19MB，无需 Python 环境）；
- 双击 `启动查看器.bat`（开发态源码运行，需要 Python 环境）；
- 命令行：`python main.py [文件.md 或 目录]`——启动即加载。

> 单文件 exe 每次启动会在系统临时目录（%TEMP%）自解压一次，程序退出**自动删除**；程序自身目录零残留。exe 的运行日志在 exe 旁边的 `logs\app.log`。

### 双击 .md 文件直达（文件关联，一次设置）

1. 右键任意 `.md` 文件 → **属性** → **打开方式**右侧的**更改**；
2. 选择"在这台电脑上查找其他应用"，浏览到 `dist\MD查看器.exe`；
3. 确定后，以后**双击任意 .md 文件**即直接用本程序打开查看。

（也可以在"打开方式 → 选择其他应用"里完成同样的选择。）

### 界面操作

| 操作 | 说明 |
|---|---|
| 打开文件夹 | 左侧树列出该文件夹全部 .md（含子目录），点击切换阅读 |
| 打开文件 / 拖拽 | `Ctrl+O` 打开单个文件；把 .md 文件拖进窗口任意位置同样直接打开 |
| 侧栏开关 | 顶栏"侧栏"按钮或 `Ctrl+B` 隐藏/显示导航栏，隐藏后预览占满全宽 |
| 侧栏调宽 | 拖动侧栏右缘的手柄（160~520px），双击手柄恢复默认宽度 |
| 预览 / 编辑 | 顶栏切换模式；编辑模式保存后预览自动刷新 |
| 保存 | 顶栏"保存"按钮或 `Ctrl+S`（统一以 UTF-8 无 BOM 写回） |
| 导出 HTML | 把当前文件导出为双击即可在浏览器打开的独立 HTML（相对图片仍指向原文档目录） |

### 特性与限制

- 编码识别：UTF-8（含 / 不含 BOM）优先，GBK 回退；保存统一 UTF-8 无 BOM、LF 行尾；
- 超过 10MB 的文件拒绝加载（防卡顿）；
- 运行数据保存在内存（WebView2 private mode），不在磁盘留下缓存；仅日志写入 `logs/app.log`；
- Markdown 内嵌 HTML 会被渲染（查看器体验优先），请只用它查看可信来源的文件。

## 目录结构

```
md-viewer/
├── main.py               # 入口：日志、命令行参数、拖拽订阅、窗口创建
├── ui/
│   ├── api.py            # pywebview 桥接层（前端 ↔ core 的薄桥）
│   └── static/           # 界面（index.html / style.css / app.js，浅色主题）
├── core/                 # 逻辑层（可独立测试，禁止依赖界面库）
│   ├── md_converter.py   # Markdown → HTML
│   ├── file_service.py   # 读取 / 保存 / 编码识别 / 大小保护
│   ├── folder_scanner.py # 目录扫描 → 文件树
│   └── html_exporter.py  # 独立 HTML 导出
├── tests/                # pytest 功能测试 + GUI 冒烟脚本
├── tools/make_icon.py    # 图标生成工具（Pillow）
├── assets/icon.ico       # 程序图标
├── requirements.txt / ARCHITECTURE.md / README.md
└── backup/ logs/         # 修改前备份 / 运行日志（均不入库）
```

## 测试方法

```bat
python -m pytest tests\ -v          :: 功能测试（33 项）
python tests\smoke_gui.py           :: GUI 冒烟（启动 + DOM/桥接自检 + 参数加载）
ruff check . && black --check .     :: 静态检查
```

## 构建 exe

```bat
pip install pyinstaller -i https://mirrors.aliyun.com/pypi/simple/
pyinstaller --noconfirm --clean --onefile --windowed --icon "assets\icon.ico" --name "MD查看器" ^
  --add-data "ui/static;ui/static" --add-data "assets/icon.ico;assets" ^
  --collect-all webview --collect-all clr_loader --collect-all pythonnet main.py
```

产物：`dist\MD查看器.exe`（改动源码或图标后需重新构建）。

## 问题反馈

- 日志位置：`logs/app.log`（关键流程与异常均有记录）；
- 反馈问题时请附：日志尾部、复现步骤（打开方式 / 文件内容特征，如特殊编码、超大文件）、现象截图。
