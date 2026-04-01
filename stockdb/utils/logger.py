"""日志配置"""
import sys
from pathlib import Path
from loguru import logger

LOG_DIR = Path(__file__).parent.parent.parent / "logs"
LOG_DIR.mkdir(exist_ok=True)


def setup_logger(name: str = "stockdb") -> "logger":
    logger.remove()

    # 控制台：简洁
    logger.add(
        sys.stdout,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
               "<level>{level: <8}</level> | "
               "<cyan>{name}</cyan> - <level>{message}</level>",
        level="INFO",
    )

    # 文件：详细，按日轮转
    logger.add(
        LOG_DIR / f"{name}_{{time:YYYY-MM-DD}}.log",
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}",
        level="DEBUG",
        rotation="00:00",
        retention="30 days",
        compression="gz",
    )

    return logger


log = setup_logger()
