/* md-viewer 前端交互逻辑（多标签版）。
 * 职责：界面状态与交互（标签条、文件树、模式切换、保存、导出、状态提示），
 * 全部实际工作通过 window.pywebview.api 调用后端完成。
 */

const state = {
  tags: [],           // 打开的标签：{path, name, content, diskContent}
  activeIndex: -1,    // 当前激活标签下标；-1 表示无标签
  mode: "preview",    // preview | edit（全局模式，内容按标签独立保存）
  folderPath: null,   // 当前浏览的文件夹
  loaded: false,      // pywebview 桥是否就绪
};

const SIDEBAR_DEFAULT_WIDTH = 260;
const SIDEBAR_MIN_WIDTH = 160;
const SIDEBAR_MAX_WIDTH = 520;

const PREVIEW_PLACEHOLDER =
  '<p class="preview-placeholder">把 .md 文件拖进窗口，或点击顶部按钮打开。<br>' +
  "Ctrl+O 打开文件 · Ctrl+B 隐藏/显示导航栏 · 支持多标签。</p>";

function $(id) {
  return document.getElementById(id);
}

function escapeHtml(text) {
  return String(text)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

/* Windows 路径判重用归一：分隔符统一、忽略大小写 */
function normPath(path) {
  return String(path).replace(/\//g, "\\").toLowerCase();
}

function dirOf(path) {
  const i = Math.max(path.lastIndexOf("\\"), path.lastIndexOf("/"));
  return i > 0 ? path.slice(0, i) : null;
}

function nameOf(path) {
  const i = Math.max(path.lastIndexOf("\\"), path.lastIndexOf("/"));
  return i >= 0 ? path.slice(i + 1) : path;
}

function activeTag() {
  return state.tags[state.activeIndex] || null;
}

function isDirty(tag) {
  return Boolean(tag) && tag.content !== tag.diskContent;
}

function setStatus(text, isError) {
  const el = $("status-text");
  el.textContent = text;
  el.className = isError ? "error" : "";
}

/* ---------- 拖放守卫（必须在脚本顶层立即注册） ----------
 * HTML5 规范：dragover 不阻止默认行为，drop 事件不会触发；
 * 且 WebView2 默认会把拖入文件当作页面导航打开、顶掉整个界面。
 * 这里只阻止默认行为，真正的文件路径由 Python 侧 dom drop 订阅通道获取。 */
window.addEventListener("dragover", (event) => event.preventDefault());
window.addEventListener("drop", (event) => event.preventDefault());

/* ---------- 初始化 ---------- */
window.addEventListener("pywebviewready", () => {
  state.loaded = true;
  init();
});

async function init() {
  bindToolbar();
  bindKeyboard();
  bindEditor();
  bindFindbar();
  initSidebarResizer();
  // 供 Python 侧调用（拖拽 / 单实例 IPC 转发）
  window.app = {
    loadFromPath: (path, isDir) => openPath(path, isDir),
    setStatus: (text, isError) => setStatus(text, isError),
  };
  setStatus("就绪");
  const result = await window.pywebview.api.get_initial_target();
  if (result.ok && result.target) {
    await openPath(result.target, result.is_dir);
  }
}

/* 命令行 / 拖拽 / IPC 的统一入口：目录打开导航树，文件开标签 */
async function openPath(path, isDir) {
  if (isDir) {
    await openFolder(path);
  } else {
    await loadFile(path);
  }
}

/* ---------- 编辑器（行号栏 + 滚动同步 + Tab 缩进） ---------- */
const EDITOR_TAB_WIDTH = 4;

function bindEditor() {
  const editor = $("editor");
  editor.addEventListener("input", updateGutter);
  // 行号栏跟随源码框垂直滚动，保持同一行对齐
  editor.addEventListener("scroll", () => {
    $("editor-gutter").scrollTop = editor.scrollTop;
  });
  // Tab 缩进（Notepad++ 惯例）：无选区插入 4 空格；有选区整体缩进；Shift+Tab 反缩进。
  // 回车自动缩进：新行继承上一行的行首空白（主流编辑器惯例）；
  // 若上一行是"纯空白+符号"（如列表 "- "），同时补一个同款列表符号
  editor.addEventListener("keydown", (event) => {
    if (event.key === "Enter" && !event.shiftKey && !event.ctrlKey) {
      if (handleEnterKey(editor, event)) return;
    }
    if (event.key !== "Tab") return;
    event.preventDefault();
    const start = editor.selectionStart;
    const end = editor.selectionEnd;
    const value = editor.value;
    if (start === end && !event.shiftKey) {
      // 无选区：插入 4 空格
      editor.setRangeText(" ".repeat(EDITOR_TAB_WIDTH), start, end, "end");
    } else {
      // 有选区（或 Shift+Tab）：对选中行做缩进/反缩进
      const line_start = value.lastIndexOf("\n", start - 1) + 1;
      const line_end = value.indexOf("\n", end) === -1 ? value.length : value.indexOf("\n", end);
      const block = value.slice(line_start, line_end);
      const lines = block.split("\n");
      const updated = lines
        .map((line) => {
          if (event.shiftKey) {
            const cut = line.match(/^ {1,4}/);
            return cut ? line.slice(cut[0].length) : line;
          }
          return line.length ? " ".repeat(EDITOR_TAB_WIDTH) + line : line;
        })
        .join("\n");
      editor.setRangeText(updated, line_start, line_end, "end");
      // 重选整块，支持连续按 Tab/Shift+Tab
      const new_end = line_start + updated.length;
      editor.setSelectionRange(line_start, new_end);
    }
    updateGutter();
  });
}

/* 回车自动缩进：取光标所在行的行首空白作为新行缩进。
 * 返回 true 表示已处理（阻止默认换行）。列表行（- / * / 1. 等）额外补同款符号；
 * 上一行只有列表符号没有内容时，回车改为清除缩进（清空列表项，符合主流编辑器行为）。 */
function handleEnterKey(editor, event) {
  const start = editor.selectionStart;
  const end = editor.selectionEnd;
  if (start !== end) return false; // 有选区时走系统默认（覆盖选区换行）
  const value = editor.value;
  const line_start = value.lastIndexOf("\n", start - 1) + 1;
  const current_line = value.slice(line_start, start);
  const indent = current_line.match(/^[ \t]*/)[0];
  const after_indent = current_line.slice(indent.length);
  const list_marker = after_indent.match(/^([-*+]|\d+[.)])\s+/);
  let insert = "\n" + indent;
  if (list_marker) {
    // 列表行有内容：新行补同款符号（有序列表序号 +1）
    if (/^\d/.test(list_marker[1])) {
      const num = parseInt(list_marker[1], 10) + 1;
      insert += num + list_marker[1].slice(String(num - 1).length + 1) + " ";
    } else {
      insert += list_marker[1] + " ";
    }
  } else if (after_indent === "") {
    // 上一行只有缩进/列表符号没有内容：清空该行缩进，取消列表（插入换行到行首）
    editor.setRangeText("\n", line_start, start, "end");
    updateGutter();
    event.preventDefault();
    return true;
  }
  editor.setRangeText(insert, start, end, "end");
  updateGutter();
  event.preventDefault();
  return true;
}

function updateGutter() {
  const line_count = $("editor").value.split("\n").length;
  const numbers = new Array(line_count);
  for (let i = 0; i < line_count; i++) numbers[i] = i + 1;
  $("editor-gutter").textContent = numbers.join("\n");
  $("editor-gutter").scrollTop = $("editor").scrollTop;
}

/* ---------- 顶栏 ---------- */
function bindToolbar() {
  $("btn-open-folder").addEventListener("click", async () => {
    const chosen = await window.pywebview.api.open_folder_dialog();
    if (chosen.ok) await openFolder(chosen.path);
  });

  $("btn-new-file").addEventListener("click", newFile);
  $("btn-open-file").addEventListener("click", async () => {
    const chosen = await window.pywebview.api.open_file_dialog();
    if (chosen.ok) await loadFile(chosen.path);
  });

  $("btn-refresh").addEventListener("click", async () => {
    // 刷新语义：① 重新扫描导航树；② 重新读取当前标签（外部更新后回到磁盘版本）
    if (state.folderPath) await openFolder(state.folderPath);
    const tag = activeTag();
    if (tag && !isDirty(tag)) await reloadTag(state.activeIndex);
  });

  $("btn-sidebar").addEventListener("click", toggleSidebar);
  $("btn-mode-preview").addEventListener("click", () => switchMode("preview"));
  $("btn-mode-edit").addEventListener("click", () => switchMode("edit"));
  $("btn-save").addEventListener("click", saveCurrent);
  $("btn-export").addEventListener("click", exportCurrent);
}

function bindKeyboard() {
  document.addEventListener("keydown", (event) => {
    const key = event.key.toLowerCase();
    if ((event.ctrlKey || event.metaKey) && key === "s") {
      event.preventDefault();
      saveCurrent();
    }
    if ((event.ctrlKey || event.metaKey) && key === "b") {
      event.preventDefault();
      toggleSidebar();
    }
    if ((event.ctrlKey || event.metaKey) && key === "o") {
      event.preventDefault();
      $("btn-open-file").click();
    }
    if ((event.ctrlKey || event.metaKey) && key === "n") {
      event.preventDefault();
      newFile();
    }
    if ((event.ctrlKey || event.metaKey) && key === "f" && state.mode === "edit") {
      event.preventDefault();
      openFind(false);
    }
    if ((event.ctrlKey || event.metaKey) && key === "h" && state.mode === "edit") {
      event.preventDefault();
      openFind(true);
    }
    if ((event.ctrlKey || event.metaKey) && key === "w") {
      event.preventDefault();
      closeTag(state.activeIndex);
    }
    if (event.ctrlKey && event.key === "Tab") {
      event.preventDefault();
      if (state.tags.length > 1) {
        activateTag((state.activeIndex + 1) % state.tags.length);
      }
    }
  });
}

/* ---------- 多标签 ---------- */
async function loadFile(path) {
  const normalized = normPath(path);
  const existing = state.tags.findIndex((tag) => normPath(tag.path) === normalized);
  if (existing >= 0) {
    // 同一文件已打开：只激活，不重复加载
    activateTag(existing);
    setStatus("已切换到已打开的标签");
    return;
  }
  const read = await window.pywebview.api.read_file(path);
  if (!read.ok) {
    setStatus("读取失败：" + read.error, true);
    return;
  }
  const tag = {
    path: read.path,
    name: nameOf(read.path),
    content: read.content,
    diskContent: read.content,
  };
  state.tags.push(tag);
  activateTag(state.tags.length - 1);
  setStatus("已加载（" + read.encoding + "）");
}

/* 切换前把编辑器中的最新内容写回旧标签，保证编辑内容不丢失 */
function storeEditingState() {
  const tag = activeTag();
  if (tag && state.mode === "edit") {
    tag.content = $("editor").value;
  }
}

/* 重新读取磁盘上的文件并覆盖指定标签内容（外部更新刷新用）。
 * 有未保存修改时询问：确定 → 放弃本地修改读入新内容；取消 → 保留现状。 */
async function reloadTag(index) {
  const tag = state.tags[index];
  if (!tag) return false;
  if (isDirty(tag) && !window.confirm('"' + tag.name + '" 有未保存的修改，重新读取将放弃这些修改，确定？')) {
    return false;
  }
  const read = await window.pywebview.api.read_file(tag.path);
  if (!read.ok) {
    setStatus("重新读取失败：" + read.error, true);
    return false;
  }
  tag.content = read.content;
  tag.diskContent = read.content;
  if (index === state.activeIndex) {
    $("editor").value = tag.content;
    updateGutter();
    renderTabs();
    renderPreview(tag.content, dirOf(tag.path));
  } else {
    renderTabs();
  }
  setStatus("已重新读入：" + tag.name);
  return true;
}

/* 对比磁盘版本检测指定标签是否已被外部修改（返回 Promise<bool>） */
async function tagChangedOnDisk(tag) {
  const read = await window.pywebview.api.read_file(tag.path);
  if (!read.ok) return false;
  return read.content !== tag.diskContent;
}

function activateTag(index) {
  if (index < 0 || index >= state.tags.length) return;
  storeEditingState();
  const switching_to = state.tags[index];
  // 切换（含首次激活）时检测外部修改：磁盘内容与最近读入版本不一致即提示重读
  tagChangedOnDisk(switching_to).then((changed) => {
    if (changed && index === state.activeIndex && state.tags[index] === switching_to) {
      const stale = isDirty(switching_to)
        ? '"' + switching_to.name + '" 已被外部修改，且本地有未保存的修改。\n重新读取将放弃本地修改，确定？\n（取消则保留本地内容，可稍后点刷新按钮重读）'
        : '"' + switching_to.name + '" 已被外部修改，重新读取最新内容？';
      if (window.confirm(stale)) {
        reloadTag(index);
        return;
      }
      setStatus("已保留本地内容（该文件外部有更新）", true);
    }
  });
  state.activeIndex = index;
  const tag = state.tags[index];
  $("current-file").textContent = tag.path;
  $("current-file").title = tag.path;
  $("editor").value = tag.content;
  updateGutter();
  $("btn-save").disabled = false;
  $("btn-export").disabled = false;
  renderTabs();
  markTreeActive(tag.path);
  renderPreview(tag.content, dirOf(tag.path));
}

function closeTag(index) {
  if (index < 0 || index >= state.tags.length) return;
  const tag = state.tags[index];
  if (isDirty(tag) && !window.confirm('"' + tag.name + '" 有未保存的修改，确定关闭？')) {
    return;
  }
  state.tags.splice(index, 1);
  if (state.tags.length === 0) {
    state.activeIndex = -1;
    $("current-file").textContent = "未打开文件";
    $("current-file").title = "";
    $("editor").value = "";
    updateGutter();
    $("preview").innerHTML = PREVIEW_PLACEHOLDER;
    $("btn-save").disabled = true;
    $("btn-export").disabled = true;
    renderTabs();
    markTreeActive("");
    setStatus("已关闭全部标签");
    return;
  }
  // 调整活动标签下标：关闭项之前的活动标签左移一位；越界则取最后一个
  if (index < state.activeIndex) {
    state.activeIndex -= 1;
  } else if (state.activeIndex >= state.tags.length) {
    state.activeIndex = state.tags.length - 1;
  }
  renderTabs();
  activateTag(state.activeIndex);
}

function renderTabs() {
  const bar = $("tabbar");
  bar.innerHTML = "";
  state.tags.forEach((tag, index) => {
    const el = document.createElement("div");
    el.className = "tab" + (index === state.activeIndex ? " active" : "");
    el.title = tag.path + (isDirty(tag) ? "（未保存）" : "");
    const title = document.createElement("span");
    title.className = "tab-title" + (isDirty(tag) ? " dirty" : "");
    title.textContent = tag.name + (isDirty(tag) ? " ●" : "");
    const close = document.createElement("span");
    close.className = "tab-close";
    close.textContent = "×";
    close.addEventListener("click", (event) => {
      event.stopPropagation();
      closeTag(index);
    });
    el.appendChild(title);
    el.appendChild(close);
    el.addEventListener("click", () => activateTag(index));
    // 鼠标中键关闭（浏览器标签惯例）
    el.addEventListener("mousedown", (event) => {
      if (event.button === 1) {
        event.preventDefault();
        closeTag(index);
      }
    });
    bar.appendChild(el);
  });
}

/* ---------- 模式切换 ---------- */
function switchMode(mode) {
  if (mode === state.mode) return;
  if (mode === "preview") {
    // 从编辑切回预览：用编辑器当前内容刷新渲染（不落盘），
    // 并滚动到光标所在的源行对应的渲染块（而不是从头显示）
    storeEditingState();
    const tag = activeTag();
    const caret_line = caretSourceLine();
    if (tag) renderPreview(tag.content, dirOf(tag.path), caret_line);
  } else {
    const tag = activeTag();
    $("editor").value = tag ? tag.content : "";
    updateGutter();
  }
  state.mode = mode;
  $("preview").hidden = mode !== "preview";
  $("editor-wrap").hidden = mode !== "edit";
  $("btn-mode-preview").className = "icon-btn mode" + (mode === "preview" ? " active" : "");
  $("btn-mode-edit").className = "icon-btn mode" + (mode === "edit" ? " active" : "");
}

/* 光标所在的源文件行号（1-based；取光标前最近的换行计数） */
function caretSourceLine() {
  const editor = $("editor");
  return editor.value.slice(0, editor.selectionStart).split("\n").length;
}

/* ---------- 文件加载 / 保存 / 导出 ---------- */
async function renderPreview(content, baseDir, scroll_to_line) {
  const result = await window.pywebview.api.convert_markdown(content, baseDir || null);
  if (!result.ok) {
    $("preview").innerHTML = '<p class="error">' + escapeHtml(result.error) + "</p>";
    return;
  }
  $("preview").innerHTML = result.html;
  if (scroll_to_line) {
    scrollToSourceLine(scroll_to_line);
  } else {
    $("preview").scrollTop = 0;
  }
  await renderMermaidBlocks();
}

/* 滚动预览区到指定源行对应的渲染块：块元素带有解析期注入的 data-source-line，
 * 找到"起始行 ≤ 目标行的最后一个块"，把目标行置于预览区顶部附近（留 2 块上下文）。 */
function scrollToSourceLine(line) {
  const blocks = document.querySelectorAll("#preview [data-source-line]");
  let target = null;
  for (const block of blocks) {
    const start = parseInt(block.getAttribute("data-source-line"), 10);
    if (start <= line) {
      target = block;
    } else {
      break;
    }
  }
  if (target) {
    const top = target.offsetTop - $("preview").offsetTop - 40;
    $("preview").scrollTop = Math.max(0, top);
  }
}

/* 渲染后裁字校正：mermaid 节点高度按默认字体度量，中文多行文字常溢出矩形节点框。
 * 仅校正 rect 节点（菱形/圆形等 polygon 几何不适用扩高，显式字体初始化后其度量已准）；
 * 比较文字实际高度与矩形高度，把差值补到 rect 高度并上移形状与文字容器各一半，保持中心不变。 */
function fixMermaidClip(root) {
  root.querySelectorAll(".node").forEach((node) => {
    const label = node.querySelector(".nodeLabel");
    const rect = node.querySelector("rect");
    if (!label || !rect) return;
    const text_height = label.getBoundingClientRect().height;
    const shape_height = parseFloat(rect.getAttribute("height") || "0");
    if (!text_height || !shape_height) return;
    const overflow = text_height + 12 - shape_height; // 12px 上下余量
    if (overflow > 0) {
      rect.setAttribute("height", (shape_height + overflow).toFixed(1));
      const y = parseFloat(rect.getAttribute("y") || "0");
      if (!Number.isNaN(y)) rect.setAttribute("y", (y - overflow / 2).toFixed(1));
      const foreign = node.querySelector("foreignObject");
      if (foreign) {
        const fy = parseFloat(foreign.getAttribute("y") || "0");
        if (!Number.isNaN(fy)) foreign.setAttribute("y", (fy - overflow / 2).toFixed(1));
        foreign.setAttribute("height", (text_height + 8).toFixed(1));
      }
    }
  });
}

/* ---------- Mermaid 图形渲染 ----------
 * ```mermaid 代码块替换为 SVG 图形（mermaid.min.js 本地离线渲染）；
 * 渲染失败（语法错误等）回退为普通代码块原文显示，并附错误提示。 */
let mermaidSeq = 0;

async function renderMermaidBlocks() {
  if (typeof mermaid === "undefined") return;
  const blocks = document.querySelectorAll("#preview pre > code[class*='mermaid']");
  for (const code of blocks) {
    const pre = code.parentElement;
    const source = code.textContent;
    const holder = document.createElement("div");
    holder.className = "mermaid-figure";
    const id = "mermaid-d" + ++mermaidSeq;
    try {
      // v10 手动渲染前必须显式初始化（startOnLoad 关闭避免双重渲染；loose 允许节点内 HTML 如 <br/>）。
      // fontFamily/fontSize 显式指定：默认按系统字体度量节点高度，中文多行文本实测会超出节点框被裁剪；
      // 统一字体后测量与渲染一致，配合 CSS 行高修正节点文字完整显示
      mermaid.initialize({
        startOnLoad: false,
        securityLevel: "loose",
        theme: "default",
        fontFamily: '"Microsoft YaHei", "Segoe UI", sans-serif',
        themeVariables: { fontSize: "14px" },
        flowchart: { htmlLabels: true, curve: "basis", padding: 10 },
      });
      const render = await mermaid.render(id, source);
      holder.innerHTML = render.svg;
      // 渲染后校正：遍历本图节点，把实际文字高度回写到节点容器（解决度量偏差导致的裁字）
      requestAnimationFrame(() => fixMermaidClip(holder));
    } catch (err) {
      holder.className = "mermaid-figure mermaid-error";
      const tip = document.createElement("p");
      tip.className = "error";
      tip.textContent = "Mermaid 语法错误：" + (err && err.message ? err.message : err);
      const restore = document.createElement("pre");
      const restoreCode = document.createElement("code");
      restoreCode.textContent = source;
      restore.appendChild(restoreCode);
      holder.appendChild(tip);
      holder.appendChild(restore);
      setStatus("Mermaid 渲染失败：" + (err && err.message ? err.message : err), true);
    }
    pre.replaceWith(holder);
  }
}

async function saveCurrent() {
  const tag = activeTag();
  if (!tag) return;
  storeEditingState();
  const result = await window.pywebview.api.save_file(tag.path, tag.content);
  if (!result.ok) {
    setStatus("保存失败：" + result.error, true);
    return;
  }
  tag.diskContent = tag.content;
  renderTabs();
  if (state.mode === "preview") {
    renderPreview(tag.content, dirOf(tag.path));
  }
  setStatus("已保存并刷新预览");
}

async function exportCurrent() {
  const tag = activeTag();
  if (!tag) return;
  // 编辑中未保存的内容不参与导出，先保存保证所见即所得
  if (isDirty(tag)) {
    setStatus("当前标签有未保存的修改，请先保存再导出", true);
    return;
  }
  setStatus("正在导出…");
  const result = await window.pywebview.api.export_html(tag.path);
  if (!result.ok) {
    setStatus("导出失败：" + result.error, true);
    return;
  }
  setStatus("已导出：" + result.path);
}

/* ---------- 新建文件 ---------- */
/* 保存对话框选路径 → 建空文件 → 开成新标签。文件由后端立即落盘（content 为空、
 * diskContent 一致），Ctrl+S 随时可安全写回。 */
async function newFile() {
  const window_api = window.pywebview.api;
  const chosen = await window_api.new_file_dialog();
  if (!chosen.ok) {
    if (chosen.error !== "已取消") setStatus("新建失败：" + chosen.error, true);
    return;
  }
  await openFolderIfInside(chosen.dir);
  const tag = {
    path: chosen.path,
    name: nameOf(chosen.path),
    content: "",
    diskContent: "",
  };
  state.tags.push(tag);
  activateTag(state.tags.length - 1);
  switchMode("edit");
  setStatus("已新建：" + chosen.path);
}

/* 新建文件位于当前浏览文件夹内时静默刷新导航树（否则不动树） */
async function openFolderIfInside(dir) {
  if (state.folderPath && dir && normPath(dir).startsWith(normPath(state.folderPath))) {
    const result = await window.pywebview.api.scan_folder(state.folderPath);
    if (result.ok) {
      const tree = $("file-tree");
      tree.innerHTML = "";
      tree.appendChild(buildTreeList(result.root.children));
      $("file-count").textContent = result.truncated
        ? result.file_count + "+（已截断）"
        : result.file_count + " 个文件";
    }
  }
}

/* ---------- 查找替换（编辑/预览双模式，Notepad++ 风格） ----------
 * 编辑模式：textarea 选区定位 + 替换；
 * 预览模式：对渲染 DOM 做文本搜索（隐藏标记恢复 + 高亮 span），替换不可用。 */
const find_state = { matches: [], current: -1, preview_spans: [], preview_matches: [] };

function findIsPreview() {
  return state.mode === "preview";
}

function openFind(withReplace) {
  const bar = $("findbar");
  bar.hidden = false;
  const preview_mode = findIsPreview();
  // 替换控件仅编辑模式有意义（预览是只读渲染结果）
  $("replace-input").hidden = !withReplace || preview_mode;
  $("btn-replace").hidden = !withReplace || preview_mode;
  $("btn-replace-all").hidden = !withReplace || preview_mode;
  const editor = $("editor");
  const selected = preview_mode
    ? String(window.getSelection())
    : editor.value.slice(editor.selectionStart, editor.selectionEnd);
  if (selected && selected.length < 200 && !selected.includes("\n")) {
    $("find-input").value = selected;
  }
  $("find-input").focus();
  $("find-input").select();
  runFind();
}

function closeFind() {
  clearPreviewHighlights();
  $("findbar").hidden = true;
  if (!findIsPreview()) $("editor").focus();
}

function findCaseSensitive() {
  return $("find-case").checked;
}

/* 清除预览模式的高亮标记 */
function clearPreviewHighlights() {
  for (const span of find_state.preview_spans) {
    const parent = span.parentNode;
    if (parent) {
      parent.replaceChild(document.createTextNode(span.textContent), span);
      parent.normalize();
    }
  }
  find_state.preview_spans = [];
}

/* 预览模式：在渲染 DOM 的文本节点里收集匹配（返回匹配元素与文本位置） */
function collectPreviewMatches(needle) {
  clearPreviewHighlights();
  const lower = !findCaseSensitive();
  const target = lower ? needle.toLowerCase() : needle;
  const walker = document.createTreeWalker($("preview"), NodeFilter.SHOW_TEXT, {
    acceptNode: (node) =>
      node.parentElement.closest(".mermaid-figure") ? NodeFilter.FILTER_REJECT : NodeFilter.FILTER_ACCEPT,
  });
  const hits = [];
  let node;
  while ((node = walker.nextNode())) {
    const text = lower ? node.textContent.toLowerCase() : node.textContent;
    let idx = text.indexOf(target);
    while (idx !== -1) {
      hits.push({ node, idx, len: target.length });
      idx = text.indexOf(target, idx + target.length);
    }
  }
  return hits;
}

function highlightPreviewMatch(hit) {
  const range = document.createRange();
  range.setStart(hit.node, hit.idx);
  range.setEnd(hit.node, hit.idx + hit.len);
  const span = document.createElement("span");
  span.className = "find-highlight";
  span.textContent = hit.node.textContent.substr(hit.idx, hit.len);
  try {
    range.deleteContents();
    range.insertNode(span);
    find_state.preview_spans.push(span);
    span.scrollIntoView({ block: "center" });
    return span;
  } catch (err) {
    return null;
  }
}

/* 计算全部匹配位置（每次输入/开关变化后重算；模式不同实现不同） */
function runFind() {
  find_state.matches = [];
  find_state.current = -1;
  clearPreviewHighlights();
  find_state.preview_matches = [];
  const needle = $("find-input").value;
  if (!needle) {
    updateFindCount();
    return;
  }
  if (findIsPreview()) {
    find_state.preview_matches = collectPreviewMatches(needle);
  } else {
    const editor = $("editor");
    const haystack = findCaseSensitive() ? editor.value : editor.value.toLowerCase();
    const target = findCaseSensitive() ? needle : needle.toLowerCase();
    let pos = haystack.indexOf(target);
    while (pos !== -1) {
      find_state.matches.push([pos, pos + target.length]);
      pos = haystack.indexOf(target, pos + target.length);
    }
  }
  updateFindCount();
  if (find_state.matches.length || find_state.preview_matches.length) {
    findNext(false);
  }
}

function updateFindCount() {
  const el = $("find-count");
  const total = findIsPreview() ? find_state.preview_matches.length : find_state.matches.length;
  if (total === 0) {
    const needle = $("find-input").value;
    el.textContent = needle ? "无结果" : "0/0";
    el.className = needle ? "no-match" : "";
    return;
  }
  el.className = "";
  el.textContent = find_state.current + 1 + "/" + total;
}

function selectMatch(index) {
  const editor = $("editor");
  const [s, e] = find_state.matches[index];
  editor.focus();
  editor.setSelectionRange(s, e);
  // 滚动到匹配可见位置：利用 textarea 的滚动随选区（浏览器自动）+ 行号栏同步
  updateGutter();
}

function findNext(backward) {
  const preview_mode = findIsPreview();
  const total = preview_mode ? find_state.preview_matches.length : find_state.matches.length;
  if (total === 0) {
    runFind();
    return;
  }
  find_state.current = (find_state.current + (backward ? -1 : 1) + total) % total;
  updateFindCount();
  if (preview_mode) {
    // 预览模式：重新做一次匹配（避免前次高亮破坏文本节点定位），只保留当前高亮
    const needle = $("find-input").value;
    const hits = collectPreviewMatches(needle);
    if (hits.length) {
      highlightPreviewMatch(hits[find_state.current % hits.length]);
    }
  } else {
    selectMatch(find_state.current);
  }
}

function replaceCurrent() {
  const editor = $("editor");
  if (!find_state.matches.length) return;
  if (find_state.current < 0) find_state.current = 0;
  const [s, e] = find_state.matches[find_state.current];
  editor.setRangeText($("replace-input").value, s, e, "end");
  // 触发脏标记与渲染刷新
  storeEditingState();
  renderTabs();
  updateGutter();
  runFind();
}

function replaceAllMatches() {
  const editor = $("editor");
  const needle = $("find-input").value;
  if (!needle || !find_state.matches.length) return;
  const replacement = $("replace-input").value;
  // 从后往前替换避免位置失效
  for (let i = find_state.matches.length - 1; i >= 0; i--) {
    const [s, e] = find_state.matches[i];
    editor.setRangeText(replacement, s, e, "end");
  }
  storeEditingState();
  renderTabs();
  updateGutter();
  runFind();
  setStatus("已替换 " + find_state.matches.length + " 处（替换后剩余）");
}

function bindFindbar() {
  $("find-input").addEventListener("input", runFind);
  $("find-input").addEventListener("keydown", (event) => {
    if (event.key === "Enter") {
      event.preventDefault();
      findNext(event.shiftKey);
    }
    if (event.key === "Escape") closeFind();
  });
  $("replace-input").addEventListener("keydown", (event) => {
    if (event.key === "Enter") {
      event.preventDefault();
      replaceCurrent();
    }
    if (event.key === "Escape") closeFind();
  });
  $("find-case").addEventListener("change", runFind);
  $("btn-find-next").addEventListener("click", () => findNext(false));
  $("btn-find-prev").addEventListener("click", () => findNext(true));
  $("btn-replace").addEventListener("click", replaceCurrent);
  $("btn-replace-all").addEventListener("click", replaceAllMatches);
  $("btn-find-close").addEventListener("click", closeFind);
}

/* ---------- 文件树 ---------- */
async function openFolder(path) {
  const result = await window.pywebview.api.scan_folder(path);
  if (!result.ok) {
    setStatus("扫描失败：" + result.error, true);
    return;
  }
  state.folderPath = path;
  const tree = $("file-tree");
  tree.innerHTML = "";
  tree.appendChild(buildTreeList(result.root.children));
  $("file-count").textContent = result.truncated
    ? result.file_count + "+（已截断）"
    : result.file_count + " 个文件";
  setStatus("已打开文件夹：" + path);
}

function buildTreeList(children) {
  const ul = document.createElement("ul");
  for (const node of children) {
    if (node.is_dir) {
      const li = document.createElement("li");
      const details = document.createElement("details");
      details.open = true;
      const summary = document.createElement("summary");
      summary.innerHTML = '<span class="icon">📁</span>' + escapeHtml(node.name);
      details.appendChild(summary);
      details.appendChild(buildTreeList(node.children));
      li.appendChild(details);
      ul.appendChild(li);
    } else {
      const li = document.createElement("li");
      li.className = "file-item";
      li.dataset.path = node.path;
      li.innerHTML = '<span class="icon">📄</span>' + escapeHtml(node.name);
      li.addEventListener("click", () => loadFile(node.path));
      ul.appendChild(li);
    }
  }
  return ul;
}

function markTreeActive(path) {
  document.querySelectorAll("#file-tree li.file-item").forEach((item) => {
    item.className = item.dataset.path === path ? "file-item active" : "file-item";
  });
}

/* ---------- 侧栏开关与宽度调节 ---------- */
function toggleSidebar() {
  const hidden = document.body.classList.toggle("no-sidebar");
  $("btn-sidebar").className = "icon-btn" + (hidden ? "" : " active");
}

function initSidebarResizer() {
  const resizer = $("sidebar-resizer");
  const sidebar = $("sidebar");

  resizer.addEventListener("dblclick", () => {
    sidebar.style.width = SIDEBAR_DEFAULT_WIDTH + "px";
  });

  resizer.addEventListener("mousedown", (startEvent) => {
    startEvent.preventDefault();
    const start_x = startEvent.clientX;
    const start_width = sidebar.getBoundingClientRect().width;
    resizer.className = "dragging";
    document.body.classList.add("resizing");

    const on_move = (moveEvent) => {
      const width = Math.min(
        SIDEBAR_MAX_WIDTH,
        Math.max(SIDEBAR_MIN_WIDTH, start_width + (moveEvent.clientX - start_x))
      );
      sidebar.style.width = width + "px";
    };
    const on_up = () => {
      resizer.className = "";
      document.body.classList.remove("resizing");
      document.removeEventListener("mousemove", on_move);
      document.removeEventListener("mouseup", on_up);
    };
    document.addEventListener("mousemove", on_move);
    document.addEventListener("mouseup", on_up);
  });
}
