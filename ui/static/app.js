/* md-viewer 前端交互逻辑。
 * 职责：界面状态与交互（树渲染、模式切换、保存、导出、状态提示），
 * 全部实际工作通过 window.pywebview.api 调用后端完成。
 */

/* ---------- 全局状态 ---------- */
const state = {
  currentPath: null,   // 当前打开的 .md 文件绝对路径
  savedContent: "",    // 最近一次保存/加载的内容（用于脏检查）
  folderPath: null,    // 当前浏览的文件夹
  mode: "preview",     // preview | edit
  loaded: false,       // pywebview 桥是否就绪
};

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

function setStatus(text, isError) {
  const el = $("status-text");
  el.textContent = text;
  el.className = isError ? "error" : "";
}

function hasUnsavedChanges() {
  return state.mode === "edit" && $("editor").value !== state.savedContent;
}

/* ---------- 初始化 ---------- */
window.addEventListener("pywebviewready", () => {
  state.loaded = true;
  init();
});

async function init() {
  bindToolbar();
  bindKeyboard();
  // 供 Python 侧拖拽回调调用的入口（pywebview 的 dom 事件在 Python 拿到完整路径）
  window.app = {
    loadFromPath: (path) => loadFile(path),
    setStatus: (text, isError) => setStatus(text, isError),
  };
  setStatus("就绪");
  const result = await window.pywebview.api.get_initial_target();
  if (!result.ok || !result.target) return;
  if (result.is_dir) {
    await openFolder(result.target);
  } else {
    await loadFile(result.target);
  }
}

/* ---------- 顶栏 ---------- */
function bindToolbar() {
  $("btn-open-folder").addEventListener("click", async () => {
    const chosen = await window.pywebview.api.open_folder_dialog();
    if (chosen.ok) await openFolder(chosen.path);
  });

  $("btn-open-file").addEventListener("click", async () => {
    if (!confirmDiscardIfNeeded()) return;
    const chosen = await window.pywebview.api.open_file_dialog();
    if (chosen.ok) await loadFile(chosen.path);
  });

  $("btn-refresh").addEventListener("click", () => {
    if (state.folderPath) openFolder(state.folderPath);
  });

  $("btn-mode-preview").addEventListener("click", () => switchMode("preview"));
  $("btn-mode-edit").addEventListener("click", () => switchMode("edit"));
  $("btn-save").addEventListener("click", saveCurrent);
  $("btn-export").addEventListener("click", exportCurrent);
}

function bindKeyboard() {
  document.addEventListener("keydown", (event) => {
    if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "s") {
      event.preventDefault();
      if (state.mode === "edit") saveCurrent();
    }
  });
}

/* ---------- 模式切换 ---------- */
function switchMode(mode) {
  if (mode === state.mode) return;
  if (mode === "preview") {
    // 从编辑切回预览：用编辑器当前内容刷新渲染（不落盘）
    renderPreview($("editor").value);
  } else {
    $("editor").value = state.savedContent;
  }
  state.mode = mode;
  $("preview").hidden = mode !== "preview";
  $("editor").hidden = mode !== "edit";
  $("btn-mode-preview").className = "mode" + (mode === "preview" ? " active" : "");
  $("btn-mode-edit").className = "mode" + (mode === "edit" ? " active" : "");
}

/* ---------- 文件加载 / 保存 / 导出 ---------- */
async function loadFile(path) {
  if (!confirmDiscardIfNeeded()) return;
  const read = await window.pywebview.api.read_file(path);
  if (!read.ok) {
    setStatus("读取失败：" + read.error, true);
    return;
  }
  state.currentPath = read.path;
  state.savedContent = read.content;
  $("current-file").textContent = read.path;
  $("current-file").title = read.path;
  $("editor").value = read.content;
  $("btn-save").disabled = false;
  $("btn-export").disabled = false;
  markTreeActive(read.path);
  await renderPreview(read.content, read.dir);
  setStatus("已加载（" + read.encoding + "）");
}

async function renderPreview(content, baseDir) {
  const result = await window.pywebview.api.convert_markdown(content, baseDir || null);
  if (!result.ok) {
    $("preview").innerHTML = '<p class="error">' + escapeHtml(result.error) + "</p>";
    return;
  }
  $("preview").innerHTML = result.html;
  $("preview").scrollTop = 0;
}

async function saveCurrent() {
  if (!state.currentPath) return;
  const content = $("editor").value;
  const result = await window.pywebview.api.save_file(state.currentPath, content);
  if (!result.ok) {
    setStatus("保存失败：" + result.error, true);
    return;
  }
  state.savedContent = content;
  await renderPreview(content);
  setStatus("已保存并刷新预览");
}

async function exportCurrent() {
  if (!state.currentPath) return;
  // 编辑中未保存的内容不参与导出，先保存保证所见即所得
  if (hasUnsavedChanges()) {
    setStatus("编辑内容尚未保存，请先保存再导出", true);
    return;
  }
  setStatus("正在导出…");
  const result = await window.pywebview.api.export_html(state.currentPath);
  if (!result.ok) {
    setStatus("导出失败：" + result.error, true);
    return;
  }
  setStatus("已导出：" + result.path);
}

function confirmDiscardIfNeeded() {
  if (!hasUnsavedChanges()) return true;
  return window.confirm("当前编辑内容尚未保存，确定放弃修改？");
}

/* ---------- 文件树 ---------- */
async function openFolder(path) {
  if (!confirmDiscardIfNeeded()) return;
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
      summary.textContent = node.name;
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
