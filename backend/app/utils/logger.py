"""
日志配置 - 使用loguru
"""
import sys
from loguru import logger
from app.config import get_settings


def setup_logger(name: str = None):
    """配置日志"""
    settings = get_settings()
    
    # 移除默认处理器
    logger.remove()
    
    # 添加控制台输出
    log_format = (
        "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
        "<level>{level: <8}</level> | "
        "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | "
        "<level>{message}</level>"
    )
    
    logger.add(
        sys.stdout,
        format=log_format,
        level="DEBUG" if settings.DEBUG else "INFO",
        colorize=True,
    )
    
    # 添加文件输出
    logger.add(
        "logs/app_{time:YYYY-MM-DD}.log",
        rotation="00:00",
        retention="7 days",
        format=log_format,
        level="INFO",
    )
    
    return logger
