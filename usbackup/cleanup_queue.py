import asyncio

__all__ = ['CleanupQueue']

class CleanupQueue:
    def __init__(self):
        self._jobs = {}

    def add_job(self, id: str, handler: callable, *args, **kwargs) -> None:
        if id in self._jobs:
            raise ValueError(f"Job with id {id} already exists")
        
        self._jobs[id] = (handler, args, kwargs)

    def remove_job(self, id: str) -> None:
        if id not in self._jobs:
            return
        
        del self._jobs[id]

    def _pop_job(self) -> tuple:
        if not self._jobs:
            return None
        
        return self._jobs.popitem()[1]

    async def run_jobs(self) -> None:
        if not self._jobs:
            return
        
        while self._jobs:
            (handler, args, kwargs) = self._pop_job()

            if asyncio.iscoroutinefunction(handler):
                await handler(*args, **kwargs)
            else:
                handler(*args, **kwargs)