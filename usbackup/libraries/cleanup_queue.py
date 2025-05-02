import asyncio

__all__ = ['CleanupQueue']

class CleanupQueue:
    def __init__(self):
        self._jobs: dict = {}

    def add_job(self, id: str, handler: callable, *args, **kwargs) -> None:
        if id in self._jobs:
            raise ValueError(f"Job with id {id} already exists")
        
        self._jobs[id] = (handler, args, kwargs)

    def remove_job(self, id: str) -> None:
        if id not in self._jobs:
            return
        
        del self._jobs[id]
    
    async def run_job(self, id: str) -> None:
        if id not in self._jobs:
            raise ValueError(f"Job with id {id} does not exist")
        
        (handler, args, kwargs) = self._jobs[id]
        
        if asyncio.iscoroutinefunction(handler):
            await handler(*args, **kwargs)
        else:
            handler(*args, **kwargs)
            
        self.remove_job(id)

    async def run_jobs(self) -> None:
        if not self._jobs:
            return
        
        for id in list(self._jobs.keys()):
            await self.run_job(id)