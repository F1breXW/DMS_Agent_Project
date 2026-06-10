# Panel File Tree — Design Spec

## Overview

Replace the flat file list (`<ul>`) in the right panel with a tree view supporting nested folders, drag-and-drop reorganization, and per-file deletion.

## Goals

1. Delete individual files from the panel (not just bulk clear)
2. Create nested folders to organize files
3. Drag files into folders to reorganize them
4. Tree structure persists in localStorage across sessions

## Data Model

### localStorage: `dms_sessions`

Each session replaces `uploadedFiles: string[]` with `fileTree: TreeNode[]`:

```typescript
type TreeNode =
  | { type: "folder"; name: string; children: TreeNode[] }
  | { type: "file";   name: string }
```

**Migration**: On load, if `session.uploadedFiles` exists but `session.fileTree` does not, convert each filename to `{ type: "file", name }` and delete `uploadedFiles`.

**Server files**: Files already stored on server with directory paths (e.g., `source_code/best2.py`). The tree uses the **server-side relative path** as the `name` field, which may include directory separators. When rendering, only the basename is shown; the tree's folder structure is independent of server paths.

### Helper functions

```javascript
function flattenTree(tree)      // → string[] of all file paths
function findNode(tree, name)   // → { node, parent, index } or null
function addToRoot(tree, name)  // append file to root, dedup by name
function removeNode(tree, name) // remove file/folder by name
function moveNode(tree, src, dstFolder) // move file into folder
```

## UI Structure

Replace `<ul id="panel-file-list">` with:

```html
<ul id="panel-file-tree" class="file-tree"></ul>
<button id="panel-new-folder-btn" class="panel-action-btn">+ New Folder</button>
```

### CSS classes

| Class | Purpose |
|-------|---------|
| `.file-tree` | Root `<ul>`, no bullets, compact spacing |
| `.ft-item` | `<li>` wrapper: flex row, 2px gap, hover highlight |
| `.ft-toggle` | Folder expand/collapse arrow (▶/▼) |
| `.ft-icon` | 📁 or 📄 Unicode glyph |
| `.ft-name` | Filename/foldername text |
| `.ft-delete` | ✕ button, visible on hover |
| `.ft-children` | Nested `<ul>` inside folder, hidden when collapsed |
| `.ft-folder.collapsed > .ft-children` | `display: none` |
| `.ft-dragover` | Drop target highlight (dashed border + accent background) |

### Recursive rendering

```javascript
function renderTree(container, tree) {
  container.innerHTML = '';
  tree.forEach(node => renderNode(container, node));
}

function renderNode(parent, node) {
  const li = document.createElement('li');
  li.className = 'ft-item';
  if (node.type === 'folder') {
    li.innerHTML = `<span class="ft-toggle">▼</span><span class="ft-icon">📁</span><span class="ft-name">...</span><span class="ft-delete">×</span>`;
    const ul = document.createElement('ul');
    ul.className = 'ft-children';
    node.children.forEach(c => renderNode(ul, c));
    li.appendChild(ul);
    // Toggle click
    li.querySelector('.ft-toggle').onclick = () => {
      li.classList.toggle('collapsed');
    };
  } else {
    li.innerHTML = `<span class="ft-icon">📄</span><span class="ft-name">...</span><span class="ft-delete">×</span>`;
    li.draggable = true;
    // Drag events
  }
  // Delete click
  li.querySelector('.ft-delete').onclick = () => deleteTreeNode(node);
  parent.appendChild(li);
}
```

## Interactions

### Delete file
1. Click ✕ on file row
2. `confirm('Delete filename?')` 
3. Remove from `fileTree`, save localStorage, re-render
4. Server file is NOT deleted (user may want to download it first; "Clear Session" handles bulk cleanup)

### Delete folder
1. Click ✕ on folder row
2. Only allowed if folder is empty → `confirm('Delete empty folder?')`
3. If folder has children → show toast "Folder not empty. Move or delete files inside first."

### Create folder
1. Click `+ New Folder` button
2. `prompt('Folder name:')`
3. If name not empty and not duplicate → append `{ type: "folder", name, children: [] }` to tree root
4. Save localStorage, re-render

### Rename folder
1. Right-click folder name
2. `prompt('New name:')`
3. If valid → update `node.name`, save, re-render

### Drag & Drop
1. File `dragstart`: store `e.dataTransfer.setData('text/plain', node.name)`
2. Folder `dragover`: `e.preventDefault()`, add `.ft-dragover` class
3. Folder `dragleave`: remove `.ft-dragover`
4. Folder `drop`: read source name, `moveNode(tree, srcName, targetFolderName)`, save, re-render

## Integration with Upload

- `addFileToList()` → `addToRoot(currentFileTree, filename)` → save localStorage → re-render panel tree
- Upload overlay `#file-list` keeps its flat list (separate from panel tree, for quick upload feedback)
- "Clear Session" → set `fileTree = []` → save → re-render

## Edge Cases

- **Empty tree**: Show "No files" placeholder
- **Duplicate names**: Prevent adding file/folder with same name at same level
- **Drag to self**: No-op if dropping file into its current parent folder
- **Root-level only for new folders**: Folders created via button always go to root

## Scope Boundaries

- **In scope**: Tree rendering, CRUD for files/folders, drag-and-drop, localStorage persistence
- **Out of scope**: Server-side folder creation (files stored flat on server), right-click context menu (use click interactions instead), multi-select, file rename, file preview
