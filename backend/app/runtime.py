"""Per-action budgets shared by generation, tool loops and verification."""
import time
from contextvars import ContextVar
from functools import wraps

budget = ContextVar("teaching_budget", default=None)


def bounded_action(fn):
    @wraps(fn)
    async def wrapped(*args, **kwargs):
        token = budget.set({"deadline": time.monotonic() + 180, "requests": 0, "tools": 0})
        try:
            return await fn(*args, **kwargs)
        finally:
            budget.reset(token)
    return wrapped


def remaining():
    current = budget.get()
    return max(.001, current["deadline"] - time.monotonic()) if current else 180


def spend(kind):
    current = budget.get()
    if current is None:
        return
    current[kind] += 1
    if current[kind] > (4 if kind == "tools" else 10):
        from .model import ModelError
        raise ModelError("本轮调用预算已用完，请缩小问题范围后重试")
