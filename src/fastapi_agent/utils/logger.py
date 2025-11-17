"""
Logging utilities for FastAPI Agent
"""

import logging
import sys

# 创建全局logger
logger = logging.getLogger("fastapi_agent")

# 如果还没有配置handler，则配置
if not logger.handlers:
    # 设置日志级别
    logger.setLevel(logging.INFO)

    # 创建控制台handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)

    # 创建格式器
    formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    # 设置格式器
    console_handler.setFormatter(formatter)

    # 添加handler
    logger.addHandler(console_handler)

# 防止日志传播到根logger
logger.propagate = False
