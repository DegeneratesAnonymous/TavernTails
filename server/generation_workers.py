"""Run synchronous generation without occupying the API event loop or worker pool."""
from functools import partial
from typing import Callable, ParamSpec, TypeVar

from anyio import CapacityLimiter, to_thread

_P = ParamSpec('_P')
_R = TypeVar('_R')
# Keep queued generation separate from FastAPI's pool for ordinary sync routes.
_GENERATION_LIMIT = CapacityLimiter(4)


async def run_generation(func: Callable[_P, _R], *args: _P.args, **kwargs: _P.kwargs) -> _R:
    return await to_thread.run_sync(partial(func, *args, **kwargs), limiter=_GENERATION_LIMIT)
