import os
from pathlib import Path


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def ensure_file(path: Path, content: str) -> None:
    if not path.exists():
        path.write_text(content, encoding="utf-8")


def main() -> None:
    root = Path(__file__).resolve().parent

    # Project structure
    ensure_dir(root / "src")
    ensure_dir(root / "data" / "standards")
    ensure_dir(root / "data" / "logs")
    ensure_dir(root / "data" / "source_code")
    ensure_dir(root / "ui")

    # .env template
    env_template = "DEEPSEEK_API_KEY=your_key_here\n"
    ensure_file(root / ".env", env_template)

    # requirements.txt
    requirements = "\n".join(
        [
            "langchain",
            "langchain-openai",
            "gradio",
            "pandas",
            "pydantic",
            "faiss-cpu",
            "pypdf",
            "sentence-transformers",
            "python-dotenv",
        ]
    ) + "\n"
    ensure_file(root / "requirements.txt", requirements)

    print("Setup complete.")


if __name__ == "__main__":
    main()
