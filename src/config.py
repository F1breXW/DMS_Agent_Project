from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Final

from dotenv import load_dotenv

# 计算项目根目录位置，方便读取根目录下的 .env
ROOT_DIR: Final[Path] = Path(__file__).resolve().parents[1]
ENV_PATH: Final[Path] = ROOT_DIR / ".env"

# 读取 .env 配置（默认不覆盖已存在的系统环境变量）
load_dotenv(dotenv_path=ENV_PATH, override=False)

# DeepSeek 配置：地址与 Key
DEEPSEEK_API_BASE: Final[str] = os.getenv("DEEPSEEK_API_BASE", "https://api.deepseek.com")
DEEPSEEK_API_KEY: Final[str] = os.getenv("DEEPSEEK_API_KEY", "")


def get_logger(name: str = "dms") -> logging.Logger:
    """创建并返回一个可复用的日志记录器。"""

    logger = logging.getLogger(name)
    if not logger.handlers:
        # 仅在首次创建时配置处理器，避免重复输出
        logger.setLevel(logging.DEBUG)
        handler = logging.StreamHandler()
        formatter = logging.Formatter(
            "[%(asctime)s] %(levelname)s %(name)s: %(message)s"
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        logger.propagate = False
    return logger


# 统一导出一个默认 logger，便于全局使用
LOGGER: Final[logging.Logger] = get_logger()


def get_config() -> dict[str, str]:
    """将关键配置打包成字典，方便打印或传递。"""

    return {
        "DEEPSEEK_API_BASE": DEEPSEEK_API_BASE,
        "DEEPSEEK_API_KEY": DEEPSEEK_API_KEY,
    }


if __name__ == "__main__":
    # 简单自测：打印配置并输出一条调试日志
    print("Loaded config:", get_config())
    LOGGER.debug("Logger is ready.")
