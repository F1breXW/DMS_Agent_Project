"""Session-level knowledge base for user-uploaded documents (PDF/TXT/MD).

Each session gets its own FAISS index built from uploaded documents.
The global GB/T standards index is shared across all sessions.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.document_loaders import PyPDFLoader, TextLoader
from langchain_community.vectorstores import FAISS

from src.config import LOGGER


class SessionKnowledgeBase:
    """Per-session vector store for user-uploaded documents.

    Shares the embedding model with the global StandardKnowledgeBase to
    avoid loading the model twice.  Documents are persisted to disk so
    the index survives server restarts.
    """

    _CHUNK_SIZE = 500
    _CHUNK_OVERLAP = 50

    def __init__(
        self,
        knowledge_dir: Path | str,
        global_kb,  # StandardKnowledgeBase instance (shared)
    ) -> None:
        self.knowledge_dir = Path(knowledge_dir)
        self.knowledge_dir.mkdir(parents=True, exist_ok=True)
        self.global_kb = global_kb

        self._index: FAISS | None = None
        self._files: list[str] = []
        self._splitter = RecursiveCharacterTextSplitter(
            chunk_size=self._CHUNK_SIZE, chunk_overlap=self._CHUNK_OVERLAP
        )

        self._rebuild_from_disk()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def files(self) -> list[str]:
        """Return the list of filenames currently in the session index."""
        return list(self._files)

    @property
    def embeddings(self):
        """Reuse the global KB's embedding model (shared instance)."""
        return self.global_kb.embeddings

    def add_document(self, file_path: Path | str, filename: str) -> str | None:
        """Load, chunk, embed a document and merge it into the session index.

        The file is copied to knowledge_dir for persistence across restarts.
        Returns None on success, or an error string on failure.
        """
        file_path = Path(file_path)
        if not file_path.exists():
            return f"文件不存在: {file_path}"

        # --- 0. Copy to knowledge dir for persistence ---
        dest = self.knowledge_dir / filename
        if file_path.resolve() != dest.resolve():
            import shutil
            shutil.copy2(file_path, dest)
            file_path = dest

        # --- 1. Load document ---
        suffix = file_path.suffix.lower()
        try:
            if suffix == ".pdf":
                loader = PyPDFLoader(str(file_path))
                docs = loader.load()
            elif suffix in (".txt", ".md", ".markdown"):
                loader = TextLoader(str(file_path), encoding="utf-8")
                docs = loader.load()
            else:
                return f"不支持的文档格式: {suffix}（支持 .pdf / .txt / .md）"
        except Exception as exc:
            return f"加载文档失败: {exc}"

        if not docs:
            return "文档为空，无法索引。"

        # --- 2. Chunk ---
        chunks = self._splitter.split_documents(docs)
        if not chunks:
            return "文档切分后无有效内容。"

        # Tag each chunk with source filename for later filtering
        for c in chunks:
            c.metadata["source_file"] = filename

        # --- 3. Embed & merge ---
        try:
            if self._index is None:
                self._index = FAISS.from_documents(chunks, self.embeddings)
            else:
                self._index.add_documents(chunks)
        except Exception as exc:
            return f"向量化失败: {exc}"

        # --- 4. Track ---
        if filename not in self._files:
            self._files.append(filename)

        LOGGER.info(
            "Session KB: added '%s' (%d chunks, index now has %d docs)",
            filename, len(chunks), len(self._files),
        )
        return None

    def remove_document(self, filename: str) -> str | None:
        """Remove a document from the session index.

        FAISS does not support single-document deletion, so we rebuild
        the entire session index from remaining files on disk.
        Returns None on success, or an error string.
        """
        if filename not in self._files:
            return f"文档不在知识库中: {filename}"

        # Delete from disk
        doc_path = self.knowledge_dir / filename
        if doc_path.exists():
            try:
                doc_path.unlink()
            except OSError as exc:
                return f"删除文件失败: {exc}"

        # Rebuild index from remaining files
        self._rebuild_from_disk()
        LOGGER.info("Session KB: removed '%s', rebuilt index", filename)
        return None

    def search(self, query: str, k: int = 3) -> str:
        """Search both global GB/T standards and session documents.

        Returns merged results with source labels.
        """
        parts: list[str] = []

        global_result = self._search_global(query, k)
        if global_result:
            parts.append(global_result)

        session_result = self._search_session(query, k)
        if session_result:
            parts.append(session_result)

        return "\n\n---\n\n".join(parts) if parts else "未在国标库和用户知识库中找到相关内容。"

    def _search_global(self, query: str, k: int) -> str:
        """Search global GB/T standards KB."""
        if not self.global_kb or not hasattr(self.global_kb, 'search_standard'):
            return ""
        result = self.global_kb.search_standard(query, k=k)
        return f"【国标 GB/T】\n{result}" if result else ""

    def _search_session(self, query: str, k: int) -> str:
        """Search session user documents KB."""
        if self._index is None:
            return ""
        try:
            results = self._index.similarity_search(query, k=k)
        except Exception as exc:
            LOGGER.error("Session KB search failed: %s", exc)
            return ""
        if not results:
            return ""
        lines = []
        for idx, doc in enumerate(results, start=1):
            src = doc.metadata.get("source_file", "未知")
            lines.append(f"【用户文档 · {src} · 条款 {idx}】\n{doc.page_content}")
        return "\n\n".join(lines)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _rebuild_from_disk(self) -> None:
        """Rebuild the FAISS index from all documents in knowledge_dir."""
        self._index = None
        self._files = []

        supported = {".pdf", ".txt", ".md", ".markdown"}
        doc_paths = sorted(
            p for p in self.knowledge_dir.iterdir()
            if p.is_file() and p.suffix.lower() in supported
        )
        if not doc_paths:
            return

        all_chunks = []

        for doc_path in doc_paths:
            try:
                suffix = doc_path.suffix.lower()
                if suffix == ".pdf":
                    loader = PyPDFLoader(str(doc_path))
                    docs = loader.load()
                else:
                    loader = TextLoader(str(doc_path), encoding="utf-8")
                    docs = loader.load()
            except Exception:
                LOGGER.warning("Session KB: failed to load %s, skipping", doc_path.name)
                continue

            if not docs:
                continue

            chunks = self._splitter.split_documents(docs)
            for c in chunks:
                c.metadata["source_file"] = doc_path.name
            all_chunks.extend(chunks)
            self._files.append(doc_path.name)

        if all_chunks:
            try:
                self._index = FAISS.from_documents(all_chunks, self.embeddings)
                LOGGER.info(
                    "Session KB: rebuilt index from %d files (%d chunks)",
                    len(self._files), len(all_chunks),
                )
            except Exception as exc:
                LOGGER.error("Session KB: failed to rebuild index: %s", exc)
                self._index = None
                self._files = []
