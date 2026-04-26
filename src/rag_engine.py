from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

# 运行脚本时把项目根目录加入 sys.path，确保可以导入 src.*
ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

# 提前加载 .env，确保 HF_HUB_OFFLINE 等变量在导入时生效
load_dotenv(dotenv_path=ROOT_DIR / ".env", override=False)

# 强制同步离线环境变量，避免库在导入时联网
if os.getenv("HF_HUB_OFFLINE") == "1":
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"

from src.config import LOGGER

from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.document_loaders import PyPDFLoader
from langchain_community.vectorstores import FAISS

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
            embeddings = self._build_embeddings()
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
            embeddings = self._build_embeddings()
            vectorstore = FAISS.from_documents(chunks, embeddings)
            self.index_dir.mkdir(parents=True, exist_ok=True)
            vectorstore.save_local(str(self.index_dir))
            LOGGER.info("FAISS index saved to %s", self.index_dir)
            return vectorstore
        except Exception as exc:  # noqa: BLE001
            LOGGER.error("Failed to build FAISS index: %s", exc)
            return None

    def _build_embeddings(self) -> HuggingFaceEmbeddings:
        """根据环境变量初始化本地 Embeddings，避免联网请求。"""

        model_kwargs = {}
        model_name = self.embedding_model
        if os.getenv("HF_HUB_OFFLINE") == "1":
            model_kwargs["local_files_only"] = True
            local_path = self._resolve_local_model_path()
            if local_path:
                model_name = local_path
            else:
                LOGGER.warning("HF_HUB_OFFLINE is set but local model not found.")
        return HuggingFaceEmbeddings(
            model_name=model_name,
            model_kwargs=model_kwargs or None,
        )

    def _resolve_local_model_path(self) -> Optional[str]:
        """尝试从本地 Hugging Face 缓存中解析模型快照路径。"""

        cache_root = Path.home() / ".cache" / "huggingface" / "hub"
        model_dir_name = "models--" + self.embedding_model.replace("/", "--")
        snapshots_dir = cache_root / model_dir_name / "snapshots"
        if not snapshots_dir.exists():
            return None

        snapshots = sorted([p for p in snapshots_dir.iterdir() if p.is_dir()])
        if not snapshots:
            return None

        # 取最新的快照目录
        latest = snapshots[-1]
        if (latest / "config.json").exists():
            return str(latest)
        return str(latest)

    def search_standard(self, query: str, k: int = 3) -> str:
        """根据查询语句返回最相关的国标条款文本（Top-K）。"""

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

        parts = []
        for idx, doc in enumerate(results, start=1):
            parts.append(f"【条款 {idx}】\n{doc.page_content}")
        return "\n\n".join(parts)


if __name__ == "__main__":
    kb = StandardKnowledgeBase()
    text = kb.search_standard("报警延迟")
    print("Search result:\n", text)
