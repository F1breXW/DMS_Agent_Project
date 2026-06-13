"""
DMS 数字工程师 Agent — FastAPI 服务端

启动方式: uvicorn server:app --reload --port 8000
"""
from __future__ import annotations

import asyncio
import re
import shutil
import threading
import traceback
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.websockets import WebSocket, WebSocketDisconnect
from pydantic import BaseModel

import sys

ROOT_DIR = Path(__file__).resolve().parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.config import LOGGER, UPLOAD_DIR, DMS_PORT
from src.session_kb import SessionKnowledgeBase

# Lazy import — DMSAgent is heavy (~13s for ML dependencies)
DMSAgent = None

# ---------------------------------------------------------------------------
# FastAPI application
# ---------------------------------------------------------------------------

app = FastAPI(title="DMS Evaluator", docs_url=None, redoc_url=None)


@app.on_event("startup")
async def on_startup():
    LOGGER.info("DMS Agent server starting on http://127.0.0.1:%d", DMS_PORT)


@app.on_event("shutdown")
async def on_shutdown():
    LOGGER.info("DMS Agent server shutting down — closing all sessions")
    for sid in list(session_manager._sessions.keys()):
        session_manager.remove(sid)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _ws_send(ws: WebSocket, data: dict) -> bool:
    """Send JSON over WebSocket, return False if disconnected."""
    try:
        await ws.send_json(data)
        return True
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Session management
# ---------------------------------------------------------------------------

@dataclass
class Session:
    session_id: str
    upload_dir: Path
    local_session_id: str | None = None  # Persisted across server sessions
    uploaded_files: list[str] = field(default_factory=list)
    modified_files: list[dict] = field(default_factory=list)
    chat_messages: list[dict] = field(default_factory=list)
    agent: object = None              # DMSAgent instance, set after lazy init
    agent_ready: bool = False
    agent_error: str | None = None
    knowledge_dir: Path | None = None  # User knowledge documents storage
    knowledge_kb: object = None        # SessionKnowledgeBase instance
    reports: list[dict] = field(default_factory=list)  # Generated evaluation reports


class SessionManager:
    """简单的内存会话管理器。Agent 延迟初始化以加快 session 创建。"""

    def __init__(self) -> None:
        self._sessions: dict[str, Session] = {}

    def create(self, local_session_id: str | None = None) -> Session:
        global DMSAgent
        sid = uuid.uuid4().hex[:12]
        # Use local_session_id for upload dir if provided (persists across server sessions)
        dir_key = local_session_id or sid
        upload_dir = UPLOAD_DIR / dir_key
        upload_dir.mkdir(parents=True, exist_ok=True)
        session = Session(session_id=sid, upload_dir=upload_dir,
                          local_session_id=local_session_id)
        self._sessions[sid] = session

        # Lazy-init agent in background thread
        def _init_agent():
            global DMSAgent
            try:
                if DMSAgent is None:
                    from src.agent_core import DMSAgent as _DMSAgent
                    DMSAgent = _DMSAgent

                # Ensure global KB is loaded before creating session KB
                from src.tools import _get_kb
                global_kb = _get_kb()

                # Create session knowledge base
                session.knowledge_dir = upload_dir / "knowledge"
                session.knowledge_dir.mkdir(parents=True, exist_ok=True)
                session.knowledge_kb = SessionKnowledgeBase(
                    knowledge_dir=session.knowledge_dir,
                    global_kb=global_kb,
                )

                session.agent = DMSAgent(session_kb=session.knowledge_kb)
                session.agent_ready = True
                LOGGER.info("Session %s: agent ready (KB: %d docs)",
                            sid, len(session.knowledge_kb.files))
            except Exception as exc:
                session.agent_error = str(exc)
                LOGGER.error("Session %s: agent init failed: %s", sid, exc)

        threading.Thread(target=_init_agent, daemon=True).start()

        LOGGER.info("Session %s created (agent initializing in background)", sid)
        return session

    def get(self, session_id: str) -> Session | None:
        return self._sessions.get(session_id)

    def remove(self, session_id: str) -> bool:
        session = self._sessions.pop(session_id, None)
        if session is None:
            return False
        # Only delete upload dir if it's a server-only session.
        # local_session_id dirs persist across server sessions.
        if not session.local_session_id and session.upload_dir.exists():
            shutil.rmtree(session.upload_dir, ignore_errors=True)
        LOGGER.info("Session %s removed", session_id)
        return True

    def export(self, session_id: str, format: str = "md") -> str:
        import json as _json
        session = self.get(session_id)
        if session is None:
            return ""
        if format == "json":
            return _json.dumps(session.chat_messages, ensure_ascii=False, indent=2)
        lines = ["# DMS Agent Conversation\n"]
        for m in session.chat_messages:
            role = "**User**" if m["role"] == "user" else "**Agent**"
            lines.append(f"### {role} ({m.get('timestamp', '')})\n")
            lines.append(m["content"] + "\n")
        return "\n".join(lines)


session_manager = SessionManager()

# ---------------------------------------------------------------------------
# HTTP endpoints
# ---------------------------------------------------------------------------


class CreateSessionRequest(BaseModel):
    local_session_id: str | None = None
    expected_files: list[str] = []  # Filenames previously uploaded (from localStorage)


@app.post("/api/session")
async def create_session(body: CreateSessionRequest = CreateSessionRequest()):
    """创建新会话。可附带 local_session_id 以持久化上传目录。"""
    try:
        session = session_manager.create(local_session_id=body.local_session_id)
        # Restore previously uploaded files that still exist on disk
        for fname in body.expected_files:
            fpath = session.upload_dir / fname
            if fpath.exists() and fname not in session.uploaded_files:
                session.uploaded_files.append(fname)
        if body.expected_files:
            LOGGER.info("Session %s: restored %d/%d files from local session",
                        session.session_id,
                        len(session.uploaded_files),
                        len(body.expected_files))
        return {"session_id": session.session_id}
    except Exception as e:
        LOGGER.error("Failed to create session: %s", e)
        raise HTTPException(status_code=500, detail=f"Agent initialization failed: {e}")


@app.post("/api/upload")
async def upload_file(session_id: str = Form(...), file: UploadFile = File(...)):
    """上传文件到指定会话。"""
    session = session_manager.get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")

    safe_name = file.filename.replace('\\', '/')
    if not safe_name or safe_name.startswith('/'):
        raise HTTPException(status_code=400, detail="Invalid filename")
    # Prevent path traversal
    if '..' in safe_name:
        raise HTTPException(status_code=400, detail="Invalid filename (path traversal)")

    dest = session.upload_dir / safe_name
    dest.parent.mkdir(parents=True, exist_ok=True)
    content = await file.read()

    with open(dest, "wb") as f:
        f.write(content)

    if safe_name not in session.uploaded_files:
        session.uploaded_files.append(safe_name)

    LOGGER.info("Session %s: uploaded %s (%d bytes)", session_id, safe_name, len(content))
    return {"filename": safe_name, "size": len(content)}


@app.delete("/api/session/{session_id}")
async def delete_session(session_id: str):
    """删除会话并清理上传文件。"""
    ok = session_manager.remove(session_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Session not found")
    return {"status": "deleted"}


@app.get("/api/session/{session_id}/status")
async def session_status(session_id: str):
    """查询 Agent 初始化状态。"""
    session = session_manager.get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    kb_files = session.knowledge_kb.files if session.knowledge_kb else []
    return {
        "agent_ready": session.agent_ready,
        "agent_error": session.agent_error,
        "files": session.uploaded_files,
        "modified_files": session.modified_files,
        "knowledge_files": kb_files,
        "reports": session.reports,
    }


@app.get("/api/session/{session_id}/modified-files")
async def list_modified_files(session_id: str):
    """列出会话中已修改的文件。"""
    session = session_manager.get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return {"modified_files": session.modified_files}


@app.get("/api/session/{session_id}/files")
async def list_files(session_id: str):
    """列出会话已上传的文件。"""
    session = session_manager.get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return {"files": session.uploaded_files}


@app.get("/api/session/{session_id}/reports")
async def list_reports(session_id: str):
    """列出会话中生成的评估报告。"""
    session = session_manager.get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return {"reports": session.reports}


# ---------------------------------------------------------------------------
# Knowledge document endpoints
# ---------------------------------------------------------------------------


@app.post("/api/session/{session_id}/knowledge")
async def upload_knowledge(session_id: str, file: UploadFile = File(...)):
    """上传知识文档（PDF/TXT/MD）到会话知识库。"""
    session = session_manager.get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")

    safe_name = file.filename.replace('\\', '/')
    if not safe_name or safe_name.startswith('/'):
        raise HTTPException(status_code=400, detail="Invalid filename")
    if '..' in safe_name:
        raise HTTPException(status_code=400, detail="Invalid filename (path traversal)")

    suffix = Path(safe_name).suffix.lower()
    if suffix not in (".pdf", ".txt", ".md", ".markdown"):
        raise HTTPException(status_code=400, detail=f"不支持的文件格式: {suffix}（支持 .pdf / .txt / .md）")

    if not session.knowledge_kb:
        raise HTTPException(status_code=503, detail="Knowledge base not ready yet")

    dest = session.knowledge_dir / Path(safe_name).name
    content = await file.read()
    with open(dest, "wb") as f:
        f.write(content)

    err = session.knowledge_kb.add_document(dest, Path(safe_name).name)
    if err:
        raise HTTPException(status_code=500, detail=err)

    LOGGER.info("Session %s: knowledge doc '%s' added (%d bytes)",
                session_id, Path(safe_name).name, len(content))
    return {"filename": Path(safe_name).name, "size": len(content)}


@app.delete("/api/session/{session_id}/knowledge/{filename:path}")
async def delete_knowledge(session_id: str, filename: str):
    """删除会话知识库中的指定文档。"""
    session = session_manager.get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    if not session.knowledge_kb:
        raise HTTPException(status_code=503, detail="Knowledge base not ready yet")

    err = session.knowledge_kb.remove_document(filename)
    if err:
        raise HTTPException(status_code=404, detail=err)

    LOGGER.info("Session %s: knowledge doc '%s' removed", session_id, filename)
    return {"status": "deleted", "filename": filename}


@app.get("/api/session/{session_id}/knowledge")
async def list_knowledge(session_id: str):
    """列出会话知识库中的所有文档。"""
    session = session_manager.get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    if not session.knowledge_kb:
        return {"knowledge_files": []}
    return {"knowledge_files": session.knowledge_kb.files}


@app.get("/api/session/{session_id}/download/{filename}")
async def download_file(session_id: str, filename: str):
    """下载会话中修改后的文件。"""
    session = session_manager.get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    file_path = session.upload_dir / filename
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(file_path, filename=filename, media_type="application/octet-stream")


@app.get("/api/session/{session_id}/export")
async def export_conversation(session_id: str, format: str = "md"):
    """导出对话记录为 Markdown 或 JSON。"""
    from fastapi.responses import Response
    session = session_manager.get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    if format not in ("md", "json"):
        raise HTTPException(status_code=400, detail="Format must be md or json")
    content = session_manager.export(session_id, format)
    mime = "text/markdown" if format == "md" else "application/json"
    ext = "md" if format == "md" else "json"
    return Response(content, media_type=mime, headers={
        "Content-Disposition": f"attachment; filename=conversation.{ext}"
    })


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


# ---------------------------------------------------------------------------
# WebSocket — 核心对话流
# ---------------------------------------------------------------------------


@app.websocket("/ws/{session_id}")
async def websocket_chat(ws: WebSocket, session_id: str):
    await ws.accept()

    session = session_manager.get(session_id)
    if session is None:
        await _ws_send(ws,{"type": "error", "message": "Session not found. Please refresh the page."})
        await ws.close()
        return

    # Wait for agent to be ready (with timeout)
    waited = 0
    while not session.agent_ready and not session.agent_error and waited < 60:
        await asyncio.sleep(0.5)
        waited += 0.5

    if session.agent_error:
        await _ws_send(ws,{"type": "error", "message": f"Agent init failed: {session.agent_error}"})
        await ws.close()
        return

    if not session.agent_ready:
        await _ws_send(ws,{"type": "error", "message": "Agent init timed out after 60s. Please refresh."})
        await ws.close()
        return

    await _ws_send(ws,{"type": "status", "subtype": "agent_ready"})

    agent = session.agent
    upload_dir = str(session.upload_dir)

    try:
        while True:
            raw = await ws.receive_json()
            msg_type = raw.get("type", "")

            if msg_type == "chat":
                user_text = raw.get("content", "").strip()
                if not user_text:
                    continue

                # Merge restored history from localStorage into session
                restored = raw.get("history", None)
                if restored and not session.chat_messages:
                    for m in restored:
                        role = m.get("role", "user")
                        content = m.get("content", "")
                        ts = datetime.now().isoformat()
                        session.chat_messages.append({
                            "role": "agent" if role == "agent" else "user",
                            "content": content,
                            "timestamp": ts,
                        })
                    LOGGER.info("Session %s: restored %d messages from localStorage",
                                session_id, len(restored))

                await _ws_send(ws,{"type": "status", "subtype": "started"})
                active_tool_ids: set[str] = set()

                agent_full_response: list[str] = []
                dbg_stream_count = 0
                dbg_tool_count = 0

                try:
                    kb_files = session.knowledge_kb.files if session.knowledge_kb else []
                    async for event in agent.stream_with_context(
                        message=user_text,
                        upload_dir=upload_dir,
                        files=session.uploaded_files,
                        history=session.chat_messages,
                        knowledge_files=kb_files,
                    ):
                        kind = event.get("event", "")

                        if kind == "on_chat_model_stream":
                            dbg_stream_count += 1
                            chunk = event.get("data", {}).get("chunk", {})
                            content = getattr(chunk, "content", None)
                            if content:
                                # Flag XML tokens for diagnostics
                                if re.search(r'<(?:function_calls|tool_calls|invoke)', content, re.IGNORECASE):
                                    LOGGER.warning("WS[%s] XML token detected in stream: %r",
                                                   session_id, content[:120])
                                await _ws_send(ws,{"type": "token", "content": content})
                                agent_full_response.append(content)

                        elif kind == "on_tool_start":
                            dbg_tool_count += 1
                            run_id = event.get("run_id", "")
                            active_tool_ids.add(run_id)
                            tool_input = str(event.get("data", {}).get("input", ""))[:200]
                            LOGGER.info("WS[%s] tool_start #%d: %s", session_id, dbg_tool_count, event.get("name"))
                            await _ws_send(ws,{
                                "type": "tool_start",
                                "id": run_id,
                                "tool_name": event.get("name", "unknown"),
                                "args": tool_input,
                            })

                        elif kind == "on_tool_end":
                            run_id = event.get("run_id", "")
                            active_tool_ids.discard(run_id)
                            output_raw = event.get("data", {}).get("output", "")
                            # ToolNode returns ToolMessage objects; extract .content
                            if hasattr(output_raw, 'content'):
                                output = str(output_raw.content)
                            else:
                                output = str(output_raw)
                            is_error = "[ERR]" in output[:100] or "[FAIL]" in output[:100]
                            await _ws_send(ws,{
                                "type": "tool_end",
                                "id": run_id,
                                "tool_name": event.get("name", "unknown"),
                                "result": output[:500],
                                "is_error": is_error,
                            })

                            if event.get("name") == "modify_code":
                                if output.startswith("[OK]"):
                                    fname_match = output.split("\n")[0] if "\n" in output else ""
                                    fname = fname_match.replace("[OK] 已修改 ", "").strip()
                                    durl = f"/api/session/{session_id}/download/{fname}"
                                    # Track in session
                                    session.modified_files.append({"filename": fname, "download_url": durl})
                                    await _ws_send(ws,{
                                        "type": "diff_card",
                                        "filename": fname,
                                        "diff_text": output,
                                        "download_url": durl,
                                    })
                                else:
                                    # Error or warning — still report to frontend so user sees what failed
                                    fname = "unknown"
                                    err_line = output.split("\n")[0] if "\n" in output else output
                                    m = re.search(r'(?:文件不存在|在\s+)([\w.\-]+)', err_line)
                                    if m:
                                        fname = m.group(1)
                                    elif event.get("data", {}).get("input"):
                                        inp = event["data"]["input"]
                                        if isinstance(inp, dict):
                                            fp = inp.get("file_path", "")
                                            if fp:
                                                fname = Path(fp).name
                                    await _ws_send(ws,{
                                        "type": "diff_card",
                                        "filename": fname,
                                        "diff_text": output,
                                        "is_error": True,
                                    })

                            if event.get("name") == "save_report" and output.startswith("[OK]"):
                                report_path = output.replace("[OK] 报告已保存到: ", "").strip()
                                report_name = Path(report_path).name
                                # Copy report to session upload dir so download works
                                dest = session.upload_dir / report_name
                                if Path(report_path).resolve() != dest.resolve():
                                    shutil.copy2(report_path, dest)
                                # Track in session
                                timestamp = datetime.now().isoformat()
                                session.reports.append({
                                    "filename": report_name,
                                    "timestamp": timestamp,
                                    "download_url": f"/api/session/{session_id}/download/{report_name}",
                                })
                                await _ws_send(ws,{
                                    "type": "action_result",
                                    "action": "report_generated",
                                    "filename": report_name,
                                    "timestamp": timestamp,
                                    "download_url": f"/api/session/{session_id}/download/{report_name}",
                                })

                    agent_text = "".join(agent_full_response)

                    # Diagnostic: log response tail in case XML is hiding elsewhere
                    LOGGER.info("WS[%s] response tail (last 200 chars): %r",
                                session_id, agent_text[-200:] if len(agent_text) > 200 else agent_text)

                    # Post-process: strip any XML tool-call text that leaked through streaming.
                    # Check for both opening and closing tags (DeepSeek may omit opening tags)
                    has_xml = any(tag in agent_text.lower() for tag in [
                        "<function_calls", "<function_call>",
                        "</function_calls", "</function_call>",
                        "<tool_calls", "</tool_calls",
                        "<invoke", "</invoke>",
                        "<parameter", "</parameter>",
                    ])
                    # Also log a middle snippet to find opening tags
                    if has_xml:
                        mid = len(agent_text) // 2
                        LOGGER.info("WS[%s] response mid (around pos %d): %r",
                                    session_id, mid, agent_text[mid:mid+200])
                    if has_xml:
                        LOGGER.info("WS[%s] XML detected in response (%d chars), cleaning...",
                                    session_id, len(agent_text))
                        # Pass 0: if opening <function_calls> is missing but closing tags exist,
                        # truncate from the first XML tag to end of text
                        cleaned = agent_text
                        if not re.search(r'<\s*(?:function_calls|tool_calls)\b[^>]*>', cleaned, re.IGNORECASE):
                            first_tag = re.search(
                                r'</?\s*(?:function_calls|tool_calls|invoke|parameter)\b',
                                cleaned, re.IGNORECASE)
                            if first_tag:
                                cleaned = cleaned[:first_tag.start()].rstrip()
                        # Pass 1: remove <function_calls ...> or <tool_calls ...> through closing tag or EOS
                        cleaned = re.sub(
                            r'<\s*(?:function_calls|tool_calls)\b[^>]*>[\s\S]*?(?:</\s*(?:function_calls|tool_calls)\s*>|$)',
                            '', cleaned, flags=re.IGNORECASE)
                        # Pass 2: remove any remaining orphaned open/close tags
                        cleaned = re.sub(
                            r'</?\s*(?:function_calls|tool_calls|invoke|parameter)\b[^>]*>',
                            '', cleaned, flags=re.IGNORECASE)
                        # Pass 3: catch opening tags that span to end of line (streaming fragment)
                        cleaned = re.sub(
                            r'^<\s*(?:function_calls|tool_calls|invoke|parameter)\b[^\n]*$',
                            '', cleaned, flags=re.IGNORECASE | re.MULTILINE)
                        cleaned = cleaned.strip()
                        if cleaned != agent_text:
                            LOGGER.info("WS[%s] XML cleaned: %d → %d chars",
                                        session_id, len(agent_text), len(cleaned))
                            agent_text = cleaned
                            await _ws_send(ws,{"type": "content_replace", "content": cleaned})

                    await _ws_send(ws,{"type": "done"})
                    LOGGER.info("WS[%s] stream done: %d stream chunks, %d tool calls, response=%d chars",
                                session_id, dbg_stream_count, dbg_tool_count, len(agent_text))

                    session.chat_messages.append({"role": "user", "content": user_text, "timestamp": datetime.now().isoformat()})
                    session.chat_messages.append({"role": "agent", "content": agent_text, "timestamp": datetime.now().isoformat()})

                except Exception as exc:
                    LOGGER.error("Stream error in session %s: %s\n%s",
                                 session_id, exc, traceback.format_exc())
                    await _ws_send(ws,{"type": "error", "message": str(exc)})

            elif msg_type == "cancel":
                break

    except WebSocketDisconnect:
        LOGGER.info("Session %s: WebSocket disconnected", session_id)
    except Exception as exc:
        LOGGER.error("WebSocket error in session %s: %s", session_id, exc)
    finally:
        # Always close the WebSocket to prevent TCP CLOSE_WAIT leaks
        try:
            await ws.close()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Static file serving
# ---------------------------------------------------------------------------


@app.get("/")
async def index():
    return FileResponse(ROOT_DIR / "static" / "index.html")


# Mount static directory for assets if needed
static_dir = ROOT_DIR / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")


if __name__ == "__main__":
    import uvicorn
    import signal

    def _handle_exit(signum, frame):
        LOGGER.info("Received signal %s, shutting down gracefully...", signum)
        # Give uvicorn a moment to clean up
        raise KeyboardInterrupt

    signal.signal(signal.SIGINT, _handle_exit)
    signal.signal(signal.SIGTERM, _handle_exit)
    if hasattr(signal, 'SIGBREAK'):  # Windows Ctrl+Break
        signal.signal(signal.SIGBREAK, _handle_exit)

    LOGGER.info("Starting DMS Agent on http://127.0.0.1:%d", DMS_PORT)
    try:
        uvicorn.run("server:app", host="0.0.0.0", port=DMS_PORT, reload=False)
    except KeyboardInterrupt:
        LOGGER.info("Server stopped by user")
    except Exception as exc:
        LOGGER.critical("Server crashed: %s\n%s", exc, traceback.format_exc())
