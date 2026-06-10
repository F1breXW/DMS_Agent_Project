# Panel File Tree — 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**目标：** 将右侧面板的扁平文件列表替换为可嵌套文件夹、可拖拽、可单独删除的树形文件管理器。

**架构：** 单文件 HTML 改动，集中在 `static/index.html`。新增 `fileTree` 数据模型替代旧的 `uploadedFiles: string[]`，递归渲染树形 UI，HTML5 Drag & Drop 实现文件移动。无后端改动。

**技术栈：** Vanilla JS (DOM API + HTML5 DnD + localStorage)，CSS 沿用现有 NotebookLM 变量系统。

---

### 涉及文件

| 文件 | 变更类型 |
|------|----------|
| `static/index.html` | 多处修改（CSS + HTML + JS） |

---

### Task 1：数据层 — fileTree 辅助函数 + localStorage 迁移

**修改：** `static/index.html` 的 JS 区域（约 800-920 行，session 管理函数附近）

- [ ] **Step 1：添加 fileTree 辅助函数**

在 `getUploadedFilenames()` 函数之后插入以下代码：

```javascript
// ═══════════════════════════════════════════════════════════
// File tree helpers
// ═══════════════════════════════════════════════════════════

/** 获取当前 active session 的 fileTree 引用 */
function getFileTree() {
  const data = loadSessions();
  if (!data || !data.activeId) return null;
  const active = data.sessions.find(s => s.id === data.activeId);
  if (!active) return null;
  // 迁移旧 uploadedFiles 格式
  if (active.uploadedFiles && !active.fileTree) {
    active.fileTree = active.uploadedFiles.map(f => ({ type: 'file', name: f }));
    delete active.uploadedFiles;
    saveSessions(data);
  }
  if (!active.fileTree) active.fileTree = [];
  return active.fileTree;
}

/** 展平树为文件路径数组 */
function flattenTree(tree) {
  const result = [];
  for (const node of tree) {
    if (node.type === 'file') {
      result.push(node.name);
    } else if (node.type === 'folder' && node.children) {
      result.push(...flattenTree(node.children));
    }
  }
  return result;
}

/** 在树中查找节点，返回 { node, parentArray, index } */
function findNodeInTree(tree, name) {
  for (let i = 0; i < tree.length; i++) {
    if (tree[i].name === name) return { node: tree[i], parentArray: tree, index: i };
    if (tree[i].type === 'folder' && tree[i].children) {
      const found = findNodeInTree(tree[i].children, name);
      if (found) return found;
    }
  }
  return null;
}

/** 添加文件到根级别，去重 */
function addToRoot(tree, name) {
  if (!tree.some(n => n.type === 'file' && n.name === name)) {
    tree.push({ type: 'file', name });
  }
}

/** 从树中删除节点（文件或空文件夹） */
function removeFromTree(tree, name) {
  for (let i = 0; i < tree.length; i++) {
    if (tree[i].name === name) {
      if (tree[i].type === 'folder' && tree[i].children && tree[i].children.length > 0) {
        return false; // 文件夹非空，拒绝删除
      }
      tree.splice(i, 1);
      return true;
    }
    if (tree[i].type === 'folder' && tree[i].children) {
      if (removeFromTree(tree[i].children, name)) return true;
    }
  }
  return false;
}

/** 将文件移动到指定文件夹 */
function moveToFolder(tree, srcName, dstFolderName) {
  const src = findNodeInTree(tree, srcName);
  if (!src || src.node.type !== 'file') return false;
  const dst = findNodeInTree(tree, dstFolderName);
  if (!dst || dst.node.type !== 'folder') return false;
  // 不能移到同一个文件夹
  if (src.parentArray === dst.node.children) return false;
  // 从原位置移除
  src.parentArray.splice(src.index, 1);
  // 添加到目标文件夹
  dst.node.children.push(src.node);
  return true;
}

/** 持久化 fileTree 到 localStorage */
function saveFileTree(tree) {
  const data = loadSessions();
  if (!data || !data.activeId) return;
  const active = data.sessions.find(s => s.id === data.activeId);
  if (active) {
    active.fileTree = tree;
    delete active.uploadedFiles;
    saveSessions(data);
  }
}
```

- [ ] **Step 2：替换所有读取 uploadedFiles 的地方为使用 fileTree**

将所有 `active.uploadedFiles` 改为 `flattenTree(active.fileTree)`（或直接使用 `getFileTree()`）。涉及改动点：

```javascript
// updatePanelFileList 函数 → 改为 renderPanelTree
// 原：updatePanelFileList(active.uploadedFiles)
// 新：renderPanelTree()
```

```javascript
// session 恢复时（约 1065-1077 行）
// 原：if (active.uploadedFiles) { updatePanelFileList(active.uploadedFiles); }
// 新：renderPanelTree();（内部自动读 fileTree）
```

```javascript
// 保存会话时更新文件列表（约 820 行）
// 原：data.sessions[idx].uploadedFiles = getUploadedFilenames();
// 新：data.sessions[idx].fileTree = getFileTree();
```

```javascript
// 新建会话初始化（约 846 行）
// 原：uploadedFiles: [],
// 新：fileTree: [],
```

```javascript
// 清除会话（约 1740 行）
// 原：data.sessions[idx].uploadedFiles = [];
// 新：data.sessions[idx].fileTree = [];
// 原：updatePanelFileList([])
// 新：renderPanelTree()
```

- [ ] **Step 3：验证数据迁移**

手动测试：
1. 浏览器打开页面，F12 → Application → localStorage → 找到 `dms_sessions`
2. 如果有旧 session 带 `uploadedFiles`，刷新页面后检查是否自动转为 `fileTree`
3. 新创建的 session 应该初始化 `fileTree: []`

---

### Task 2：UI 渲染 — 递归树形 + CSS

**修改：** `static/index.html` 的 `<style>` 区域和 HTML 面板区域

- [ ] **Step 1：添加 CSS 样式**

在 `static/index.html` 的 `<style>` 区块末尾（`</style>` 之前）添加：

```css
/* ═══════════════════════════════════════════════════════════
   Panel File Tree
   ═══════════════════════════════════════════════════════════ */

.file-tree { list-style: none; padding: 0; margin: 0; }
.ft-item { display: flex; align-items: center; gap: 4px; padding: 3px 6px; border-radius: var(--radius-sm); cursor: default; font-size: 12px; color: var(--text-secondary); transition: background var(--transition); }
.ft-item:hover { background: var(--bg-hover); color: var(--text-primary); }
.ft-item .ft-toggle { cursor: pointer; width: 14px; font-size: 10px; color: var(--text-muted); user-select: none; flex-shrink: 0; }
.ft-item .ft-toggle:hover { color: var(--text-primary); }
.ft-item .ft-icon { width: 16px; text-align: center; flex-shrink: 0; }
.ft-item .ft-name { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.ft-item .ft-delete { cursor: pointer; width: 16px; text-align: center; opacity: 0; color: var(--accent); font-size: 11px; flex-shrink: 0; transition: opacity var(--transition); }
.ft-item:hover .ft-delete { opacity: 0.6; }
.ft-item:hover .ft-delete:hover { opacity: 1; color: #b34a4a; }
.ft-item .ft-drag-handle { cursor: grab; color: var(--text-muted); opacity: 0; flex-shrink: 0; }
.ft-item:hover .ft-drag-handle { opacity: 0.5; }

.ft-children { list-style: none; padding-left: 18px; margin: 0; }
.ft-folder.collapsed > .ft-children { display: none; }

/* Drag states */
.ft-item.dragging { opacity: 0.4; }
.ft-item.drag-target { background: var(--accent-soft); outline: 1px dashed var(--accent); border-radius: var(--radius-sm); }

/* New folder button */
#panel-new-folder-btn { width: 100%; padding: 6px; margin-top: 8px; background: transparent; border: 1px dashed var(--border-visible); border-radius: var(--radius-sm); cursor: pointer; font-family: var(--font-sans); font-size: 12px; color: var(--text-muted); transition: all var(--transition); }
#panel-new-folder-btn:hover { border-color: var(--accent); color: var(--accent); background: var(--accent-soft); }
```

- [ ] **Step 2：替换 HTML 面板文件区域**

找到右侧面板中的文件列表区域（约 716-719 行），将：

```html
<ul id="panel-file-list"><li class="no-files" data-i18n="no_files">No files</li></ul>
```

替换为：

```html
<div id="panel-files-section">
  <ul id="panel-file-tree" class="file-tree"></ul>
  <button id="panel-new-folder-btn">+ New Folder</button>
</div>
```

- [ ] **Step 3：实现递归渲染函数**

在 JS 区域添加：

```javascript
function renderPanelTree() {
  const treeEl = document.getElementById('panel-file-tree');
  const newFolderBtn = document.getElementById('panel-new-folder-btn');
  if (!treeEl) return;

  const tree = getFileTree();
  if (!tree || tree.length === 0) {
    treeEl.innerHTML = '<li class="no-files" data-i18n="no_files">No files</li>';
    if (newFolderBtn) newFolderBtn.style.display = 'none';
    return;
  }
  if (newFolderBtn) newFolderBtn.style.display = '';

  treeEl.innerHTML = '';
  tree.forEach(node => renderTreeNode(treeEl, node, tree));

  function renderTreeNode(parent, node, treeRef) {
    const li = document.createElement('li');
    li.className = 'ft-item';

    if (node.type === 'folder') {
      li.classList.add('ft-folder');
      li.innerHTML = `<span class="ft-toggle">▼</span><span class="ft-icon">📁</span><span class="ft-name">${escapeHTML(node.name)}</span><span class="ft-delete" title="删除文件夹">✕</span>`;
      const ul = document.createElement('ul');
      ul.className = 'ft-children';
      (node.children || []).forEach(c => renderTreeNode(ul, c, treeRef));
      li.appendChild(ul);

      // 折叠/展开
      li.querySelector('.ft-toggle').addEventListener('click', (e) => {
        e.stopPropagation();
        li.classList.toggle('collapsed');
      });

      // 拖拽目标
      li.addEventListener('dragover', (e) => {
        e.preventDefault();
        li.classList.add('drag-target');
      });
      li.addEventListener('dragleave', () => li.classList.remove('drag-target'));
      li.addEventListener('drop', (e) => {
        e.preventDefault();
        li.classList.remove('drag-target');
        const srcName = e.dataTransfer.getData('text/plain');
        if (srcName && srcName !== node.name && moveToFolder(treeRef, srcName, node.name)) {
          saveFileTree(treeRef);
          renderPanelTree();
        }
      });

      // 重命名（双击）
      li.querySelector('.ft-name').addEventListener('dblclick', (e) => {
        e.stopPropagation();
        const newName = prompt('新文件夹名：', node.name);
        if (newName && newName.trim() && newName !== node.name) {
          const trimmed = newName.trim();
          if (!treeRef.some(n => n.type === 'folder' && n.name === trimmed)) {
            node.name = trimmed;
            saveFileTree(treeRef);
            renderPanelTree();
          } else {
            showToast('文件夹名已存在');
          }
        }
      });
    } else {
      li.innerHTML = `<span class="ft-drag-handle">⋮⋮</span><span class="ft-icon">📄</span><span class="ft-name">${escapeHTML(node.name)}</span><span class="ft-delete" title="删除文件">✕</span>`;
      li.draggable = true;
      li.addEventListener('dragstart', (e) => {
        li.classList.add('dragging');
        e.dataTransfer.setData('text/plain', node.name);
        e.dataTransfer.effectAllowed = 'move';
      });
      li.addEventListener('dragend', () => li.classList.remove('dragging'));
    }

    // 删除按钮
    li.querySelector('.ft-delete').addEventListener('click', (e) => {
      e.stopPropagation();
      const label = node.type === 'folder' ? '文件夹' : '文件';
      const msg = node.type === 'folder'
        ? `删除空文件夹 "${node.name}"？`
        : `删除文件 "${node.name}"？`;
      if (!confirm(msg)) return;
      if (removeFromTree(treeRef, node.name)) {
        saveFileTree(treeRef);
        renderPanelTree();
      } else {
        showToast('文件夹非空，请先移走内部文件');
      }
    });

    parent.appendChild(li);
  }
}
```

- [ ] **Step 4：初始化时调用 renderPanelTree**

在 `initServerSession` 成功回调中，将 `updatePanelFileList(active.uploadedFiles)` 替换为 `renderPanelTree()`。同时确保所有调用 `updatePanelFileList` 的地方都改为 `renderPanelTree`。

- [ ] **Step 5：验证渲染**

手动测试：
1. 启动服务，打开页面
2. 上传几个文件 → 右侧面板显示文件树
3. 点击 `+ New Folder` → 输入名称 → 文件夹出现在树中
4. 刷新页面 → 文件和文件夹保持

---

### Task 3：新建文件夹按钮功能

**修改：** `static/index.html` 的 JS 区域

- [ ] **Step 1：绑定新建文件夹按钮事件**

在 `init()` 函数的事件绑定区域中添加：

```javascript
// New folder button
const newFolderBtn = document.getElementById('panel-new-folder-btn');
if (newFolderBtn) {
  newFolderBtn.addEventListener('click', () => {
    const tree = getFileTree();
    if (!tree) return;
    const name = prompt('文件夹名称：');
    if (!name || !name.trim()) return;
    const trimmed = name.trim();
    if (tree.some(n => n.type === 'folder' && n.name === trimmed)) {
      showToast('同名文件夹已存在');
      return;
    }
    tree.push({ type: 'folder', name: trimmed, children: [] });
    saveFileTree(tree);
    renderPanelTree();
  });
}
```

- [ ] **Step 2：验证**

手动测试：
1. 点击 `+ New Folder` → 输入名称 → 文件夹出现在面板
2. 输入已存在的名称 → 提示"同名文件夹已存在"
3. 输入空格 → 不创建

---

### Task 4：上传联动 — addFileToList 接入 tree

**修改：** `static/index.html` 的 `addFileToList` 函数

- [ ] **Step 1：修改 addFileToList**

将 `addFileToList(filename)` 改为同时更新 fileTree：

```javascript
function addFileToList(filename) {
  // 移除 overlay 列表的空状态
  const overlayNoFiles = document.getElementById('no-files');
  if (overlayNoFiles) overlayNoFiles.remove();

  // 添加到 overlay 文件列表（保留原有逻辑）
  const list = document.getElementById('file-list');
  if (list) {
    const li = document.createElement('li');
    li.innerHTML = `
      <span>${escapeHTML(filename)}</span>
      <span class="remove-file" onclick="removeFile('${escapeHTML(filename)}', this.parentElement)">×</span>`;
    list.appendChild(li);
  }

  // 添加到 fileTree 并重新渲染面板
  const tree = getFileTree();
  if (tree) {
    addToRoot(tree, filename);
    saveFileTree(tree);
    renderPanelTree();
  }

  updateFileCount();
}
```

- [ ] **Step 2：修改 removeFile**

让 `removeFile` 也同步 fileTree：

```javascript
function removeFile(filename, element) {
  element.remove();

  // 从 fileTree 中移除
  const tree = getFileTree();
  if (tree) {
    removeFromTree(tree, filename);
    saveFileTree(tree);
    renderPanelTree();
  }

  updateFileCount();
}
```

- [ ] **Step 3：清空会话时重置树**

确保 `actionClearSession` 中设置 `data.sessions[idx].fileTree = []` 并调用 `renderPanelTree()`（已在 Task 1 Step 2 中涵盖）。

- [ ] **Step 4：验证联动**

手动测试：
1. 上传文件 → 面板树即时更新
2. 在 overlay 中删除文件 → 面板树同步删除
3. 清空会话 → 面板树清空

---

### Task 5：集成自检

- [ ] **Step 1：端到端测试清单**

| 操作 | 预期结果 |
|------|----------|
| 上传 3 个文件 | 面板树显示 3 个文件 |
| 点击 `+ New Folder` | 创建新文件夹 |
| 拖文件进文件夹 | 文件移入，原位置消失 |
| 折叠/展开文件夹 | 子节点隐藏/显示 |
| 删除文件（✕） | 文件从树中移除 |
| 删除空文件夹 | 文件夹移除 |
| 删除非空文件夹 | 提示错误，不删除 |
| 双击文件夹名 | prompt 重命名 |
| 刷新页面 | 状态保持 |
| 切换 session | 每个 session 独立树状态 |
| 清空会话 | 树清空 |
| 旧 `uploadedFiles` 格式 | 自动迁移为 fileTree |

- [ ] **Step 2：提交**

```bash
git add static/index.html
git commit -m "feat: 面板文件树——支持嵌套文件夹、拖拽、单独删除"
```

---

## 自检

1. **Spec 覆盖**：数据模型 ✓ | 树形渲染 ✓ | 拖拽 ✓ | CRUD ✓ | 上传联动 ✓ | 旧数据迁移 ✓
2. **无占位符**：所有步骤含完整代码，无 TBD/TODO
3. **类型一致**：`fileTree`/`tree`/`treeRef` 命名统一，`flattenTree`、`addToRoot`、`removeFromTree`、`moveToFolder` 签名一致
