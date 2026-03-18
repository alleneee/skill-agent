"""API 调用重试模块.

提供指数退避重试逻辑，用于处理 LLM API 调用的临时失败。

特性:
    - 指数退避: 延迟时间随重试次数指数增长
    - 最大延迟限制: 防止延迟过长
    - 随机抖动: 避免雷群效应
    - 重试回调: 支持自定义重试通知

使用示例:
    config = RetryConfig(max_retries=3, initial_delay=1.0)

    @async_retry(config)
    async def call_api():
        ...
"""

import asyncio
import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


@dataclass
class RetryConfig:
    """重试配置.

    Attributes:
        enabled: 是否启用重试
        max_retries: 最大重试次数
        initial_delay: 初始延迟（秒）
        max_delay: 最大延迟（秒）
        exponential_base: 指数退避乘数
        jitter: 是否添加随机抖动
    """

    enabled: bool = True
    max_retries: int = 3
    initial_delay: float = 1.0  # Initial delay in seconds
    max_delay: float = 60.0  # Maximum delay in seconds
    exponential_base: float = 2.0  # Exponential backoff multiplier
    jitter: bool = True  # Add random jitter to avoid thundering herd


def async_retry(
    config: RetryConfig,
    on_retry: Callable[[int, Exception], None] | None = None,
) -> Callable:
    """Decorator for retrying async functions with exponential backoff.

    Args:
        config: Retry configuration
        on_retry: Optional callback function called on each retry
                 Receives (retry_count, exception) as arguments

    Returns:
        Decorated function with retry logic
    """

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            last_exception = None

            for attempt in range(config.max_retries + 1):
                try:
                    return await func(*args, **kwargs)
                except Exception as e:
                    last_exception = e

                    # Don't retry on last attempt
                    if attempt == config.max_retries:
                        break

                    # Call retry callback if provided
                    if on_retry:
                        on_retry(attempt + 1, e)

                    # Calculate delay with exponential backoff
                    delay = min(
                        config.initial_delay * (config.exponential_base**attempt),
                        config.max_delay,
                    )

                    # Add jitter if enabled
                    if config.jitter:
                        import random

                        delay = delay * (0.5 + random.random() * 0.5)

                    logger.warning(
                        f"Retry {attempt + 1}/{config.max_retries} after {delay:.2f}s: {e}"
                    )

                    await asyncio.sleep(delay)

            # All retries exhausted
            raise last_exception  # type: ignore

        return wrapper

    return decorator
