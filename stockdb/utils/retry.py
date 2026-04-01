"""重试装饰器（基于 tenacity）"""
import time
from functools import wraps
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
)
from stockdb.utils.logger import log


def api_retry(max_attempts: int = 3, min_wait: float = 2, max_wait: float = 10):
    """API 调用重试：指数退避，最多 max_attempts 次"""
    return retry(
        stop=stop_after_attempt(max_attempts),
        wait=wait_exponential(multiplier=1, min=min_wait, max=max_wait),
        retry=retry_if_exception_type(Exception),
        before_sleep=lambda rs: log.warning(
            f"API调用失败，{rs.next_action.sleep:.1f}s后重试 "
            f"(第{rs.attempt_number}次): {rs.outcome.exception()}"
        ),
    )


def with_rate_limit(interval: float = 0.4):
    """在函数执行后等待 interval 秒，控制调用频率"""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            result = func(*args, **kwargs)
            time.sleep(interval)
            return result
        return wrapper
    return decorator
