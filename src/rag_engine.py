from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.document_loaders import PyPDFLoader
from langchain_community.vectorstores import FAISS

# 运行脚本时把项目根目录加入 sys.path，确保可以导入 src.*
ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.config import LOGGER

try:
    from langchain_huggingface import HuggingFaceEmbeddings
except Exception:  # noqa: BLE001
    from langchain_community.embeddings import HuggingFaceEmbeddings
    LOGGER.warning(
        "langchain-huggingface is not installed; falling back to "
        "langchain_community.embeddings.HuggingFaceEmbeddings."
    )


class StandardKnowledgeBase:
    """标准知识库：从 PDF 构建或加载本地向量索引。"""

    def __init__(
        self,
        standards_dir: Path | str = "data/standards",
        index_dir: Path | str = "data/standards/faiss_index",
        embedding_model: str = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
    ) -> None:
        # 标准文件目录与索引目录
        self.standards_dir = Path(standards_dir)
        self.index_dir = Path(index_dir)
        self.embedding_model = embedding_model

        # 初始化向量库（优先加载已有索引，避免重复解析 PDF）
        self.vectorstore = self._load_or_build_index()

    def _load_or_build_index(self) -> Optional[FAISS]:
        """加载或构建本地向量索引。"""

        index_file = self.index_dir / "index.faiss"
        if index_file.exists():
            LOGGER.info("Loading existing FAISS index from %s", self.index_dir)
            return self._load_index()

        LOGGER.info("FAISS index not found, building from PDF files...")
        return self._build_index()

    def _load_index(self) -> Optional[FAISS]:
        """从本地加载 FAISS 索引。"""

        try:
            embeddings = HuggingFaceEmbeddings(model_name=self.embedding_model)
            return FAISS.load_local(
                str(self.index_dir),
                embeddings,
                allow_dangerous_deserialization=True,
            )
        except Exception as exc:  # noqa: BLE001
            LOGGER.error("Failed to load FAISS index: %s", exc)
            return None

    def _build_index(self) -> Optional[FAISS]:
        """解析 PDF 并构建 FAISS 索引，然后保存到本地。"""

        if not self.standards_dir.exists():
            LOGGER.error("Standards directory not found: %s", self.standards_dir)
            return None

        pdf_files = sorted(self.standards_dir.glob("*.pdf"))
        if not pdf_files:
            LOGGER.error("No PDF files found in %s", self.standards_dir)
            return None

        documents = []
        for pdf_path in pdf_files:
            try:
                loader = PyPDFLoader(str(pdf_path))
                documents.extend(loader.load())
            except Exception as exc:  # noqa: BLE001
                LOGGER.error("Failed to load PDF %s: %s", pdf_path, exc)

        if not documents:
            LOGGER.error("No documents loaded from PDFs.")
            return None

        # 文本切分，提升向量检索的粒度与效果
        splitter = RecursiveCharacterTextSplitter(chunk_size=500, chunk_overlap=50)
        chunks = splitter.split_documents(documents)

        try:
            embeddings = HuggingFaceEmbeddings(model_name=self.embedding_model)
            vectorstore = FAISS.from_documents(chunks, embeddings)
            self.index_dir.mkdir(parents=True, exist_ok=True)
            vectorstore.save_local(str(self.index_dir))
            LOGGER.info("FAISS index saved to %s", self.index_dir)
            return vectorstore
        except Exception as exc:  # noqa: BLE001
            LOGGER.error("Failed to build FAISS index: %s", exc)
            return None

    def search_standard(self, query: str, k: int = 1) -> str:
        """根据查询语句返回最相关的国标条款文本。"""

        if not self.vectorstore:
            LOGGER.error("Vectorstore is not available.")
            return ""

        try:
            results = self.vectorstore.similarity_search(query, k=k)
        except Exception as exc:  # noqa: BLE001
            LOGGER.error("Search failed: %s", exc)
            return ""

        if not results:
            return ""

        return results[0].page_content


if __name__ == "__main__":
    kb = StandardKnowledgeBase()
    text = kb.search_standard("报警延迟")
    print("Search result:\n", text)
