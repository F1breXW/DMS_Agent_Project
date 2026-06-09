# DMS Agent NotebookLM Redesign — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Redesign DMS Agent frontend from dark 2-column industrial theme to light 3-column NotebookLM style, add thinking/done status indicator, inline diff cards, right action panel, language switcher, and backend download endpoints.

**Architecture:** Single-file `static/index.html` rewrite (CSS + HTML + JS), plus 3 new endpoints in `server.py`. No new files created. CSS variables shift from dark `#1a1d23` palette to warm `#faf8f5` palette. HTML restructures from `#sidebar` + `#chat-area` to `#left-nav` + `#chat-area` + `#right-panel`. JS adds i18n system, diff card renderer, thinking indicator, and action panel handlers.

**Tech Stack:** FastAPI (Python), Vanilla HTML/CSS/JS, WebSocket, Google Fonts (Source Serif 4 + Inter + JetBrains Mono)

---

### Task 1: Server — Add download/export endpoints

**Files:**
- Modify: `server.py:140-170`

- [ ] **Step 1: Add download endpoint for single file**

After the `list_files` endpoint, add:

```python
@app.get("/api/session/{session_id}/download/{filename}")
async def download_file(session_id: str, filename: str):
    """下载会话中修改后的文件。"""
    from fastapi.responses import FileResponse as FR
    session = session_manager.get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    file_path = session.upload_dir / filename
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found")
    return FR(file_path, filename=filename, media_type="application/octet-stream")
```

- [ ] **Step 2: Add export conversation endpoint**

```python
@app.get("/api/session/{session_id}/export")
async def export_conversation(session_id: str, format: str = "md"):
    """导出对话记录为 Markdown 或 JSON。"""
    from fastapi.responses import Response
    session = session_manager.get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    if format not in ("md", "json"):
        raise HTTPException(status_code=400, detail="Format must be md or json")
    content = session.export(format)
    mime = "text/markdown" if format == "md" else "application/json"
    ext = "md" if format == "md" else "json"
    return Response(content, media_type=mime, headers={
        "Content-Disposition": f"attachment; filename=conversation.{ext}"
    })
```

- [ ] **Step 3: Add ZIP download-all endpoint**

```python
@app.get("/api/session/{session_id}/download-all")
async def download_all_files(session_id: str):
    """打包下载会话中所有文件。"""
    import zipfile
    import io
    from fastapi.responses import StreamingResponse
    session = session_manager.get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for fname in session.uploaded_files:
            fpath = session.upload_dir / fname
            if fpath.exists():
                zf.write(fpath, fname)
    buf.seek(0)
    return StreamingResponse(buf, media_type="application/zip", headers={
        "Content-Disposition": f"attachment; filename=session_{session_id}.zip"
    })
```

- [ ] **Step 4: Add Session.chat_history to server.py SessionManager**

In the Session dataclass, add:
```python
chat_messages: list[dict] = field(default_factory=list)  # {role, content, timestamp}
```

In SessionManager, add export method:
```python
def export(self, format: str = "md") -> str:
    if format == "json":
        return json.dumps(self.chat_messages, ensure_ascii=False, indent=2)
    lines = ["# DMS Agent Conversation\n"]
    for m in self.chat_messages:
        role = "**User**" if m["role"] == "user" else "**Agent**"
        lines.append(f"### {role} ({m.get('timestamp', '')})\n")
        lines.append(m["content"] + "\n")
    return "\n".join(lines)
```

In the WebSocket handler, after receiving a chat message and after the stream completes, append to session.chat_messages.

- [ ] **Step 5: Verify endpoints with curl**

Run: start server, then
```bash
curl -s http://localhost:8000/api/session/TESTID/download/test.py  # expect 404 for now
```

- [ ] **Step 6: Commit**

```bash
git add server.py
git commit -m "feat: add download/export endpoints for session files"
```

---

### Task 2: Server — Add diff_card and action_result WS messages

**Files:**
- Modify: `server.py:235-260` (WebSocket handler)

- [ ] **Step 1: Add chat_messages recording in WS handler**

In the WebSocket `while True` loop, after `await ws.send_json({"type": "done"})`, add:

```python
session.chat_messages.append({"role": "user", "content": user_text, "timestamp": datetime.now().isoformat()})
session.chat_messages.append({"role": "agent", "content": agent_response_text, "timestamp": datetime.now().isoformat()})
```

Add `from datetime import datetime` at top of server.py.

- [ ] **Step 2: Track agent_response_text during streaming**

Before the `async for event` loop, add:
```python
agent_full_response: list[str] = []
```

In the `on_chat_model_stream` handler, after `await ws.send_json({"type": "token", "content": content})`, add:
```python
agent_full_response.append(content)
```

After the loop, join: `agent_response_text = "".join(agent_full_response)`

- [ ] **Step 3: Detect modify_code tool output and emit diff_card**

In the `on_tool_end` handler, when `tool_name == "modify_code"` and the output starts with `[OK]`, parse the output to extract filename and diff, then send:

```python
if event.get("name") == "modify_code" and output.startswith("[OK]"):
    # Extract filename from output: "[OK] 已修改 retinaface.py\n..."
    fname_match = output.split("\n")[0] if "\n" in output else ""
    fname = fname_match.replace("[OK] 已修改 ", "").strip()
    await ws.send_json({
        "type": "diff_card",
        "filename": fname,
        "diff_text": output,
        "download_url": f"/api/session/{session_id}/download/{fname}",
    })
```

- [ ] **Step 4: Add action_result broadcast**

After `save_report` tool completes successfully, emit:
```python
if event.get("name") == "save_report" and output.startswith("[OK]"):
    report_path = output.replace("[OK] 报告已保存到: ", "").strip()
    report_name = Path(report_path).name
    await ws.send_json({
        "type": "action_result",
        "action": "report_generated",
        "filename": report_name,
        "download_url": f"/api/session/{session_id}/download/{report_name}",
    })
```

Need to add `from pathlib import Path` at top of server.py (already there).

- [ ] **Step 5: Commit**

```bash
git add server.py
git commit -m "feat: add diff_card and action_result WS messages + chat history tracking"
```

---

### Task 3: Frontend — CSS theme rewrite (dark → light NotebookLM)

**Files:**
- Modify: `static/index.html` — replace entire `<style>` block

- [ ] **Step 1: Replace CSS variables**

Replace the `:root` block. Find:
```css
:root {
  --bg-root: #1a1d23;
  ...
}
```
Replace with:
```css
:root {
  --bg-root: #faf8f5;
  --bg-surface: #f5f1eb;
  --bg-raised: #ffffff;
  --bg-hover: #efe9e0;
  --text-primary: #3d392f;
  --text-secondary: #6b5f4f;
  --text-muted: #9c8b74;
  --accent: #4a7c59;
  --accent-soft: rgba(74, 124, 89, 0.08);
  --accent-glow: rgba(74, 124, 89, 0.15);
  --border-subtle: #e8e3db;
  --border-visible: #e0d8cc;
  --success: #4a7c59;
  --danger: #b34a4a;
  --warning: #c9954a;
  --radius-sm: 4px;
  --radius-md: 8px;
  --font-mono: 'JetBrains Mono', 'Cascadia Code', 'Consolas', monospace;
  --font-sans: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
  --font-serif: 'Source Serif 4', Georgia, 'Times New Roman', serif;
  --transition: 180ms ease;
}
```

- [ ] **Step 2: Update Google Fonts link**

Replace the existing font import:
```html
<link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
```
With:
```html
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&family=Source+Serif+4:wght@500;600&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
```

- [ ] **Step 3: Update body + global styles**

Replace the body rule:
```css
body {
  background: var(--bg-root);
  color: var(--text-primary);
  font-family: var(--font-sans);
  -webkit-font-smoothing: antialiased;
  height: 100vh;
  overflow: hidden;
}
```

- [ ] **Step 4: Update all component CSS to use new vars**

This is a find-and-replace throughout the entire stylesheet. All existing CSS rules already reference `var(--bg-root)`, `var(--text-primary)`, etc. The variable VALUES change, but the variable NAMES stay the same. So after Step 1, all components automatically pick up the new colors.

Specific overrides still needed:
- `.msg-agent` heading styles: change `font-family: var(--font-mono)` to `font-family: var(--font-serif)` for h1, h2
- `.msg-agent h2` color: change `color: var(--accent)` to `color: var(--text-primary)`
- `.msg-agent h1` border-bottom: change to `var(--border-subtle)`
- `.tool-call` background: change from `#1c1f26` to `var(--bg-surface)`
- Selection: change `--accent-soft` already handles this
- `.msg-agent pre` background: change from `#1c1f26` to `var(--bg-surface)`, border to `var(--border-subtle)`
- Welcome message `.brand-name`: change font to `var(--font-serif)`, color to `var(--text-primary)`

Make these specific replacements:
1. `.msg-agent h1 { font-family: var(--font-mono);` → `font-family: var(--font-serif);`
2. `.msg-agent h2 { font-family: var(--font-mono);` → `font-family: var(--font-sans); font-weight: 600;`
3. `.msg-agent h2 { color: var(--accent);` → `color: var(--text-primary);`
4. `.msg-agent h1 { border-bottom: 1px solid var(--accent-soft);` → `border-bottom: 1px solid var(--border-subtle);`
5. `.tool-call { background: #1c1f26;` → `background: var(--bg-surface);`
6. `.msg-agent pre { background: #1c1f26;` → `background: var(--bg-surface);`
7. `#welcome-msg .brand-name { font-family: var(--font-mono); color: var(--accent);` → `font-family: var(--font-serif); color: var(--text-primary);`

- [ ] **Step 5: Commit**

```bash
git add static/index.html
git commit -m "style: rewrite CSS from dark industrial to light NotebookLM theme"
```

---

### Task 4: Frontend — HTML restructure (3-column layout)

**Files:**
- Modify: `static/index.html` — replace HTML body structure

- [ ] **Step 1: Replace HTML structure**

Find the `<div id="app">` block (lines 539-577) and replace with:

```html
<div id="app">
  <!-- ── Left Nav (72px) ── -->
  <nav id="left-nav">
    <div id="nav-brand">DMS</div>
    <button id="nav-upload-btn" class="nav-btn" title="Upload files">
      <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="17 8 12 3 7 8"/><line x1="12" y1="3" x2="12" y2="15"/></svg>
    </button>
    <button id="nav-chat-btn" class="nav-btn active" title="Chat">
      <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>
    </button>
    <button id="nav-files-btn" class="nav-btn" title="Files">
      <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/></svg>
    </button>
    <div style="flex:1;"></div>
    <button id="nav-settings-btn" class="nav-btn" title="Settings">
      <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/></svg>
    </button>
  </nav>

  <!-- ── Upload overlay (hidden by default) ── -->
  <div id="upload-overlay" style="display:none;">
    <div id="upload-overlay-content">
      <h2 data-i18n="upload_title">Upload Files</h2>
      <div id="upload-drop-zone">
        <div class="icon">+</div>
        <span id="upload-label">Drag files here or click to browse</span>
        <input type="file" id="file-input" multiple accept=".py,.csv,.txt,.log,.md" disabled>
      </div>
      <ul id="file-list"><li id="no-files">No files</li></ul>
      <button id="upload-close-btn" data-i18n="close">Close</button>
    </div>
  </div>

  <!-- ── Chat Area ── -->
  <main id="chat-area">
    <!-- Top bar -->
    <div id="top-bar">
      <h1 id="top-title" data-i18n="app_title">DMS Evaluator</h1>
      <div id="lang-switcher">
        <button class="lang-btn active" data-lang="zh-CN">中文</button>
        <button class="lang-btn" data-lang="en">EN</button>
      </div>
    </div>
    <div id="messages-container">
      <div id="welcome-msg">
        <div class="brand-name">DMS Evaluator</div>
        <p data-i18n="welcome_text">Driver Monitoring System performance evaluation and optimization agent</p>
        <p class="hint" data-i18n="welcome_hint">Upload log CSV or source code files, then tell me what you need</p>
      </div>
    </div>
    <div id="input-area">
      <textarea id="user-input" rows="1" data-i18n-placeholder="input_placeholder" placeholder="Ask a question about your DMS system..." onkeydown="handleKeyDown(event)"></textarea>
      <button id="send-btn" onclick="sendMessage()"><span data-i18n="send">Send</span></button>
    </div>
  </main>

  <!-- ── Right Panel (260px) ── -->
  <aside id="right-panel">
    <div class="panel-section">
      <h3 data-i18n="actions">Actions</h3>
      <button class="action-btn" onclick="actionGenerateReport()" data-i18n="gen_report">Generate Report</button>
      <button class="action-btn" onclick="actionExportChat()" data-i18n="export_chat">Export Chat</button>
      <button class="action-btn" onclick="actionSavePDF()" data-i18n="save_pdf">Save as PDF</button>
      <button class="action-btn" onclick="actionDownloadAll()" data-i18n="download_all">Download All Files</button>
      <button class="action-btn" onclick="actionCompareMetrics()" data-i18n="compare_metrics">Compare Metrics</button>
      <button class="action-btn" onclick="actionChangeSummary()" data-i18n="change_summary">Code Change Summary</button>
      <button class="action-btn" onclick="actionShareLink()" data-i18n="share_link">Share Link</button>
      <button class="action-btn danger" onclick="actionClearSession()" data-i18n="clear_session">Clear Session</button>
    </div>
    <div class="panel-section">
      <h3 data-i18n="session_files">Session Files</h3>
      <ul id="panel-file-list"><li class="no-files" data-i18n="no_files">No files</li></ul>
    </div>
    <div class="panel-section">
      <h3 data-i18n="modified_files">Modified Files</h3>
      <ul id="panel-modified-list"><li class="no-files" data-i18n="no_modifications">No modifications</li></ul>
    </div>
  </aside>
</div>
```

- [ ] **Step 2: Add left nav CSS**

Add to `<style>`:
```css
#left-nav {
  width: 56px;
  min-width: 56px;
  background: var(--bg-surface);
  border-right: 1px solid var(--border-subtle);
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 12px 0;
  gap: 4px;
}

#nav-brand {
  font-family: var(--font-serif);
  font-size: 11px;
  font-weight: 600;
  color: var(--text-primary);
  writing-mode: vertical-rl;
  letter-spacing: 0.08em;
  padding: 12px 0;
}

.nav-btn {
  width: 36px;
  height: 36px;
  border: none;
  background: transparent;
  border-radius: var(--radius-sm);
  color: var(--text-muted);
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all var(--transition);
}

.nav-btn:hover { background: var(--bg-hover); color: var(--text-primary); }
.nav-btn.active { background: var(--accent-soft); color: var(--accent); }
```

- [ ] **Step 3: Add right panel CSS**

```css
#right-panel {
  width: 240px;
  min-width: 240px;
  background: var(--bg-surface);
  border-left: 1px solid var(--border-subtle);
  padding: 16px 12px;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.panel-section h3 {
  font-family: var(--font-sans);
  font-size: 11px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: var(--text-muted);
  margin-bottom: 8px;
}

.action-btn {
  display: block;
  width: 100%;
  padding: 8px 12px;
  margin-bottom: 4px;
  background: var(--bg-raised);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-sm);
  font-family: var(--font-sans);
  font-size: 12px;
  color: var(--text-primary);
  cursor: pointer;
  text-align: left;
  transition: all var(--transition);
}

.action-btn:hover { background: var(--bg-hover); border-color: var(--border-visible); }
.action-btn.danger { color: var(--danger); }
.action-btn.danger:hover { background: rgba(179, 74, 74, 0.06); border-color: var(--danger); }

#panel-file-list, #panel-modified-list {
  list-style: none;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

#panel-file-list li, #panel-modified-list li {
  font-size: 11px;
  color: var(--text-secondary);
  padding: 3px 0;
  font-family: var(--font-mono);
  cursor: pointer;
}

#panel-file-list li:hover, #panel-modified-list li:hover {
  color: var(--accent);
}

#panel-modified-list li a {
  color: var(--accent);
  text-decoration: none;
}

.no-files {
  color: var(--text-muted) !important;
  font-family: var(--font-sans) !important;
  font-style: italic;
  cursor: default !important;
}
```

- [ ] **Step 4: Add top bar CSS**

```css
#top-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 24px;
  border-bottom: 1px solid var(--border-subtle);
  background: var(--bg-raised);
}

#top-title {
  font-family: var(--font-serif);
  font-size: 16px;
  font-weight: 600;
  color: var(--text-primary);
}

#lang-switcher {
  display: flex;
  gap: 2px;
  background: var(--bg-surface);
  border-radius: var(--radius-sm);
  padding: 2px;
}

.lang-btn {
  border: none;
  background: transparent;
  padding: 4px 10px;
  font-size: 11px;
  font-family: var(--font-sans);
  color: var(--text-muted);
  border-radius: 3px;
  cursor: pointer;
  transition: all var(--transition);
}

.lang-btn.active { background: var(--bg-raised); color: var(--text-primary); box-shadow: 0 1px 2px rgba(0,0,0,0.04); }
.lang-btn:hover:not(.active) { color: var(--text-secondary); }
```

- [ ] **Step 5: Add upload overlay CSS**

```css
#upload-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0,0,0,0.3);
  z-index: 50;
  display: flex;
  align-items: center;
  justify-content: center;
}

#upload-overlay-content {
  background: var(--bg-raised);
  border-radius: var(--radius-md);
  padding: 32px;
  max-width: 420px;
  width: 90%;
  box-shadow: 0 4px 24px rgba(0,0,0,0.08);
}

#upload-overlay-content h2 {
  font-family: var(--font-serif);
  font-size: 18px;
  margin-bottom: 16px;
}

#upload-drop-zone {
  border: 2px dashed var(--border-visible);
  border-radius: var(--radius-md);
  padding: 24px;
  text-align: center;
  color: var(--text-muted);
  cursor: pointer;
  transition: all var(--transition);
}

#upload-drop-zone:hover, #upload-drop-zone.dragover {
  border-color: var(--accent);
  background: var(--accent-soft);
}

#upload-close-btn {
  margin-top: 16px;
  width: 100%;
  padding: 8px;
  background: var(--bg-surface);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-sm);
  cursor: pointer;
}

/* Update chat area to fill between left nav and right panel */
#chat-area {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-width: 0;
  background: var(--bg-root);
}
```

- [ ] **Step 6: Remove old sidebar CSS**

Remove `#sidebar`, `#sidebar .brand`, `#session-info`, `#upload-zone`, `#clear-btn` CSS blocks. The old file-list CSS can stay but will be updated.

- [ ] **Step 7: Commit**

```bash
git add static/index.html
git commit -m "refactor: restructure HTML to 3-column layout with left nav + right panel"
```

---

### Task 5: Frontend — Thinking/Done status indicator

**Files:**
- Modify: `static/index.html` — JS `handleWSMessage` + CSS

- [ ] **Step 1: Add status indicator CSS**

Add to `<style>`:
```css
.status-indicator {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 0 0 0;
  font-size: 12px;
  color: var(--text-muted);
  border-top: 1px solid var(--border-subtle);
  margin-top: 8px;
}

.status-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--text-muted);
  flex-shrink: 0;
}

.status-indicator.thinking .status-dot {
  background: var(--text-muted);
  animation: statusPulse 1.2s ease-in-out infinite;
}

.status-indicator.done .status-dot { background: var(--success); }
.status-indicator.done .status-text { color: var(--success); }
.status-indicator.error .status-dot { background: var(--danger); }
.status-indicator.error .status-text { color: var(--danger); }

@keyframes statusPulse {
  0%, 100% { opacity: 0.3; }
  50% { opacity: 1; }
}
```

- [ ] **Step 2: Update createAgentBubble to include status indicator**

Find `createAgentBubble()` and replace:
```javascript
function createAgentBubble() {
  const container = document.getElementById('messages-container');
  const div = document.createElement('div');
  div.className = 'msg-bubble msg-agent';
  const loader = document.createElement('div');
  loader.className = 'loading-dots';
  loader.innerHTML = '<span></span><span></span><span></span>';
  div.appendChild(loader);
  container.appendChild(div);
  return div;
}
```

With:
```javascript
function createAgentBubble() {
  const container = document.getElementById('messages-container');
  const div = document.createElement('div');
  div.className = 'msg-bubble msg-agent';
  // Content area
  const content = document.createElement('div');
  content.className = 'agent-content';
  // Loading dots
  content.innerHTML = '<div class="loading-dots"><span></span><span></span><span></span></div>';
  div.appendChild(content);
  // Status indicator
  const status = document.createElement('div');
  status.className = 'status-indicator thinking';
  status.innerHTML = '<span class="status-dot"></span><span class="status-text">Thinking...</span>';
  div.appendChild(status);
  container.appendChild(div);
  return div;
}
```

- [ ] **Step 3: Update renderMarkdown to target .agent-content**

In `renderMarkdown`, change references from `container` to `agentContent`:
```javascript
function renderMarkdown(container, raw) {
  const content = container.querySelector('.agent-content');
  if (!content) return;
  const loader = content.querySelector('.loading-dots');
  if (loader) loader.remove();
  // ... rest of function uses 'content' instead of 'container'
}
```

- [ ] **Step 4: Update handleWSMessage for done/error status**

In `handleWSMessage`:
```javascript
case 'done':
  if (currentAgentBubble) {
    const status = currentAgentBubble.querySelector('.status-indicator');
    if (status) {
      status.className = 'status-indicator done';
      status.querySelector('.status-text').textContent = 'Response complete';
      setTimeout(() => { status.style.display = 'none'; }, 3000);
    }
  }
  setInputEnabled(true);
  currentAgentBubble = null;
  streamBuffer = '';
  break;

case 'error':
  if (currentAgentBubble) {
    const status = currentAgentBubble.querySelector('.status-indicator');
    if (status) {
      status.className = 'status-indicator error';
      status.querySelector('.status-text').textContent = msg.message;
    }
  }
  setInputEnabled(true);
  currentAgentBubble = null;
  break;
```

- [ ] **Step 5: Commit**

```bash
git add static/index.html
git commit -m "feat: add thinking/done/error status indicator in agent bubbles"
```

---

### Task 6: Frontend — Inline Diff Cards

**Files:**
- Modify: `static/index.html` — JS `handleWSMessage` + CSS + HTML

- [ ] **Step 1: Add diff card CSS**

Add to `<style>`:
```css
.diff-card {
  margin: 10px 0;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-md);
  overflow: hidden;
  font-family: var(--font-mono);
  font-size: 0.8em;
}

.diff-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 12px;
  background: var(--bg-surface);
  border-bottom: 1px solid var(--border-subtle);
}

.diff-filename { color: var(--text-primary); font-weight: 500; }
.diff-stats { color: var(--success); font-size: 0.9em; }

.diff-body { padding: 0; }

.diff-side-by-side {
  display: flex;
  border-bottom: 1px solid var(--border-subtle);
}

.diff-old, .diff-new {
  flex: 1;
  padding: 8px 12px;
  min-width: 0;
  white-space: pre-wrap;
  word-break: break-all;
  font-size: 0.9em;
  line-height: 1.5;
}

.diff-old {
  background: rgba(179, 74, 74, 0.04);
  border-right: 1px solid var(--border-subtle);
  color: var(--danger);
}

.diff-new {
  background: rgba(74, 124, 89, 0.04);
  color: var(--success);
}

.diff-unified {
  display: none;
  padding: 8px 12px;
  white-space: pre-wrap;
  font-size: 0.9em;
  line-height: 1.5;
  border-bottom: 1px solid var(--border-subtle);
}

.diff-card.show-unified .diff-side-by-side { display: none; }
.diff-card.show-unified .diff-unified { display: block; }

.diff-actions {
  display: flex;
  gap: 8px;
  padding: 8px 12px;
}

.diff-actions button {
  padding: 4px 10px;
  border: 1px solid var(--border-subtle);
  background: var(--bg-raised);
  border-radius: var(--radius-sm);
  font-family: var(--font-sans);
  font-size: 11px;
  color: var(--text-secondary);
  cursor: pointer;
  transition: all var(--transition);
}

.diff-actions button:hover { background: var(--bg-hover); color: var(--text-primary); }
.diff-actions button.primary { background: var(--accent); color: #fff; border-color: var(--accent); }
.diff-actions button.primary:hover { opacity: 0.9; }
```

- [ ] **Step 2: Add diff_card handler in handleWSMessage**

Add after the `case 'tool_end':` block:
```javascript
case 'diff_card':
  if (currentAgentBubble) {
    const content = currentAgentBubble.querySelector('.agent-content');
    if (content) {
      const card = createDiffCard(msg);
      content.appendChild(card);
      // Track modified file in right panel
      addModifiedFile(msg.filename, msg.download_url);
    }
  }
  break;

case 'action_result':
  if (msg.action === 'report_generated') {
    showToast('Report generated: ' + msg.filename);
    addModifiedFile(msg.filename, msg.download_url);
  }
  break;
```

- [ ] **Step 3: Add createDiffCard function**

```javascript
function createDiffCard(msg) {
  const div = document.createElement('div');
  div.className = 'diff-card';

  // Parse old/new from msg.diff_text - extract lines between ```diff and ```
  const diffMatch = msg.diff_text.match(/```diff\n([\s\S]*?)```/);
  let oldLines = [], newLines = [];
  if (diffMatch) {
    const diffLines = diffMatch[1].split('\n');
    for (const line of diffLines) {
      if (line.startsWith('-')) oldLines.push(line);
      else if (line.startsWith('+')) newLines.push(line);
    }
  }

  div.innerHTML = `
    <div class="diff-header">
      <span class="diff-filename">${escapeHTML(msg.filename)}</span>
      <span class="diff-stats">+${newLines.length} -${oldLines.length}</span>
    </div>
    <div class="diff-body">
      <div class="diff-side-by-side">
        <div class="diff-old">${escapeHTML(oldLines.join('\n') || '(no removals)')}</div>
        <div class="diff-new">${escapeHTML(newLines.join('\n') || '(no additions)')}</div>
      </div>
      <div class="diff-unified">${escapeHTML(diffMatch ? diffMatch[1] : msg.diff_text)}</div>
    </div>
    <div class="diff-actions">
      <button onclick="this.closest('.diff-card').classList.toggle('show-unified'); this.textContent = this.closest('.diff-card').classList.contains('show-unified') ? 'Side-by-side' : 'Unified Diff';">Unified Diff</button>
      <button class="primary" onclick="window.open('${msg.download_url}', '_blank')">Download</button>
    </div>
  `;

  return div;
}
```

- [ ] **Step 4: Add addModifiedFile helper**

```javascript
let modifiedFiles = [];

function addModifiedFile(filename, url) {
  if (modifiedFiles.find(f => f.filename === filename)) return;
  modifiedFiles.push({ filename, url });

  const list = document.getElementById('panel-modified-list');
  const noFiles = list.querySelector('.no-files');
  if (noFiles) noFiles.remove();

  const li = document.createElement('li');
  li.innerHTML = `<a href="${url}" download>${escapeHTML(filename)}</a>`;
  list.appendChild(li);
}
```

- [ ] **Step 5: Commit**

```bash
git add static/index.html
git commit -m "feat: add inline diff cards with side-by-side/unified toggle and download"
```

---

### Task 7: Frontend — Right Panel Actions + i18n

**Files:**
- Modify: `static/index.html` — JS functions + i18n data

- [ ] **Step 1: Add i18n strings**

At the top of `<script>`, add:
```javascript
const I18N = {
  'zh-CN': {
    app_title: 'DMS Evaluator',
    welcome_text: '驾驶员监测系统性能评估与优化 Agent',
    welcome_hint: '上传日志 CSV 或源码文件，然后告诉我需要做什么',
    input_placeholder: '输入你的问题...',
    send: 'Send',
    actions: '操作',
    gen_report: '生成评估报告',
    export_chat: '导出对话记录',
    save_pdf: '保存为 PDF',
    download_all: '下载全部文件',
    compare_metrics: '对比性能指标',
    change_summary: '代码修改摘要',
    share_link: '分享链接',
    clear_session: '清空会话',
    session_files: '会话文件',
    modified_files: '已修改文件',
    no_files: '暂无文件',
    no_modifications: '暂无修改',
    upload_title: '上传文件',
    close: '关闭',
    thinking: '正在思考...',
    done: '回答完成',
  },
  'en': {
    app_title: 'DMS Evaluator',
    welcome_text: 'Driver Monitoring System performance evaluation and optimization agent',
    welcome_hint: 'Upload log CSV or source code files, then tell me what you need',
    input_placeholder: 'Ask a question...',
    send: 'Send',
    actions: 'Actions',
    gen_report: 'Generate Report',
    export_chat: 'Export Chat',
    save_pdf: 'Save as PDF',
    download_all: 'Download All Files',
    compare_metrics: 'Compare Metrics',
    change_summary: 'Code Change Summary',
    share_link: 'Share Link',
    clear_session: 'Clear Session',
    session_files: 'Session Files',
    modified_files: 'Modified Files',
    no_files: 'No files',
    no_modifications: 'No modifications',
    upload_title: 'Upload Files',
    close: 'Close',
    thinking: 'Thinking...',
    done: 'Response complete',
  }
};

let currentLang = localStorage.getItem('dms-lang') || 'zh-CN';

function t(key) { return I18N[currentLang][key] || key; }
```

- [ ] **Step 2: Add applyLanguage function**

```javascript
function applyLanguage(lang) {
  currentLang = lang;
  localStorage.setItem('dms-lang', lang);
  // Update all data-i18n elements
  document.querySelectorAll('[data-i18n]').forEach(el => {
    el.textContent = t(el.dataset.i18n);
  });
  // Update placeholders
  document.querySelectorAll('[data-i18n-placeholder]').forEach(el => {
    el.placeholder = t(el.dataset.i18nPlaceholder);
  });
  // Update lang buttons
  document.querySelectorAll('.lang-btn').forEach(b => {
    b.classList.toggle('active', b.dataset.lang === lang);
  });
  // Update status text if currently showing
  const statusText = document.querySelector('.status-text');
  if (statusText) {
    const statusIndicator = statusText.closest('.status-indicator');
    if (statusIndicator && statusIndicator.classList.contains('thinking')) {
      statusText.textContent = t('thinking');
    }
  }
}
```

- [ ] **Step 3: Add language button handlers**

```javascript
document.querySelectorAll('.lang-btn').forEach(btn => {
  btn.addEventListener('click', () => applyLanguage(btn.dataset.lang));
});

// Apply on load
applyLanguage(currentLang);
```

- [ ] **Step 4: Add action button implementations**

```javascript
function actionGenerateReport() {
  if (!ws || ws.readyState !== WebSocket.OPEN) {
    showToast('Not connected');
    return;
  }
  ws.send(JSON.stringify({ type: 'chat', content: '请为本次会话生成一份完整的 DMS 系统评估报告，包括所有已发现的问题和建议的优化方案。生成后请用 save_report 保存。' }));
}

async function actionExportChat() {
  if (!sessionId) return;
  window.open(`/api/session/${sessionId}/export?format=md`, '_blank');
}

function actionSavePDF() { window.print(); }

function actionDownloadAll() {
  if (!sessionId) return;
  window.open(`/api/session/${sessionId}/download-all`, '_blank');
}

function actionCompareMetrics() {
  if (!ws || ws.readyState !== WebSocket.OPEN) return;
  ws.send(JSON.stringify({ type: 'chat', content: '请对比分析当前会话中上传的日志文件，生成优化前后性能对比表。' }));
}

function actionChangeSummary() {
  if (modifiedFiles.length === 0) {
    showToast('No code modifications in this session.');
    return;
  }
  const summary = modifiedFiles.map(f => `- ${f.filename}`).join('\n');
  showToast('Modified files:\n' + summary);
}

function actionShareLink() {
  const url = window.location.origin + '?session=' + sessionId;
  navigator.clipboard.writeText(url).then(() => {
    showToast('Session link copied to clipboard');
  }).catch(() => {
    showToast('Failed to copy: ' + url);
  });
}

async function actionClearSession() {
  if (ws) ws.close();
  try { await fetch(`/api/session/${sessionId}`, { method: 'DELETE' }); } catch(e) {}
  document.getElementById('messages-container').innerHTML = `
    <div id="welcome-msg">
      <div class="brand-name">DMS Evaluator</div>
      <p data-i18n="welcome_text">${t('welcome_text')}</p>
      <p class="hint" data-i18n="welcome_hint">${t('welcome_hint')}</p>
    </div>
  `;
  document.getElementById('panel-file-list').innerHTML = `<li class="no-files" data-i18n="no_files">${t('no_files')}</li>`;
  document.getElementById('panel-modified-list').innerHTML = `<li class="no-files" data-i18n="no_modifications">${t('no_modifications')}</li>`;
  currentAgentBubble = null; toolBlocks = {}; streamBuffer = ''; modifiedFiles = [];
  setInputEnabled(true);
  init();
}
```

- [ ] **Step 5: Update panel file list on upload**

In `addFileToList`, also update the right panel:
```javascript
function addFileToList(filename) {
  // Update upload overlay list (if visible)
  const overlayList = document.getElementById('file-list');
  document.getElementById('no-files')?.remove();
  // ... existing overlay list code ...

  // Update right panel list
  const panelList = document.getElementById('panel-file-list');
  const noFiles = panelList.querySelector('.no-files');
  if (noFiles) noFiles.remove();
  const li = document.createElement('li');
  li.textContent = filename;
  panelList.appendChild(li);

  updateFileCount();
}
```

- [ ] **Step 6: Add nav button click handlers**

```javascript
document.getElementById('nav-upload-btn').addEventListener('click', () => {
  document.getElementById('upload-overlay').style.display = 'flex';
});
document.getElementById('upload-close-btn').addEventListener('click', () => {
  document.getElementById('upload-overlay').style.display = 'none';
});
```

- [ ] **Step 7: Update upload drop zone**

The upload overlay uses its own drop zone. Wire up the same drag-drop and click handlers as before, but targeting the overlay elements.

- [ ] **Step 8: Commit**

```bash
git add static/index.html
git commit -m "feat: add right panel actions, i18n system, and language switcher"
```

---

### Task 8: Integration — Wire everything together and verify

**Files:**
- Verify: `static/index.html`, `server.py`

- [ ] **Step 1: Update all remaining JS references from old element IDs**

Search and replace any remaining references to old IDs:
- `sid-display` → remove or use session-info text elsewhere
- `upload-zone` → `upload-drop-zone`
- `clear-btn` → handled by `actionClearSession`
- `file-count` → updated in panel list

- [ ] **Step 2: Start server and test full flow**

```bash
uvicorn server:app --port 8000
```

Manual test checklist:
- [ ] Page loads with NotebookLM light theme
- [ ] Left nav shows icons, upload button opens overlay
- [ ] Language switcher works (中文 ↔ EN)
- [ ] Upload a CSV file → appears in right panel session files
- [ ] Send chat message → agent bubble appears with thinking indicator
- [ ] Agent responds → "Thinking..." changes to "Response complete" then hides
- [ ] Right panel buttons trigger appropriate actions
- [ ] Export chat downloads a .md file
- [ ] Clear session resets everything

- [ ] **Step 3: Test diff card flow**

```bash
# Upload a .py file, then send:
"修改这个文件里的 FPS_THRESHOLD 从 15 改成 20"
# Verify: diff card appears inline in agent bubble with side-by-side view
# Verify: Unified Diff toggle works
# Verify: Download button works
# Verify: Modified file appears in right panel
```

- [ ] **Step 4: Commit final fixes**

```bash
git add static/index.html server.py
git commit -m "fix: wire up all UI elements, fix ID references, integration fixes"
```
