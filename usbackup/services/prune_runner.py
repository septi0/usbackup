from usbackup.libraries.fs_adapter import FsAdapter
from usbackup.services.runner import Runner
from usbackup.exceptions import UsBackupRuntimeError

__all__ = ['PruneRunner']

class PruneRunner(Runner):
    async def run(self, *, dry_run: bool = False) -> None:
        if not await FsAdapter.exists(self._context.destination, 'd'):
            self._logger.info(f'No backup versions found. Nothing to prune')
            return
        
        # a dry run only reads the versions, so it never waits for or blocks a running backup
        if dry_run:
            await self.apply_retention_policy(dry_run=True)
            return
        
        if not await self._acquire_lock():
            raise UsBackupRuntimeError(f'Backup already running')
        
        try:
            await self.apply_retention_policy()
        finally:
            await self._release_lock()
