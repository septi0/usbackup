__all__ = ['JobsQueue']

class JobsQueue:
    def __init__(self):
        self._jobs = []

    def add_job(self, id: str, handler: callable, *args, **kwargs):
        self._jobs.append((id, handler, args, kwargs))

    def remove_job(self, id: str):
        self._jobs = [job for job in self._jobs if job[0] != id]

    def run_jobs(self):
        if not self._jobs:
            return
        
        for (id, handler, args, kwargs) in self._jobs:
            handler(*args, **kwargs)

            self.remove_job(id)