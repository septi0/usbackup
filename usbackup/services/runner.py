import logging
import datetime
import uuid
import io
from usbackup.libraries.cleanup_queue import CleanupQueue
from usbackup.models.version import BackupVersionModel
from usbackup.models.retention_policy import RetentionPolicyModel
from usbackup.services.context import ContextService
from usbackup.utils.logging import NoExceptionFormatter
from usbackup.exceptions import UsBackupRuntimeError

__all__ = ['Runner']

class Runner:
    def __init__(self, context: ContextService, retention_policy: RetentionPolicyModel | None, *, cleanup: CleanupQueue, logger: logging.Logger) -> None:
        self._context: ContextService = context
        self._retention_policy: RetentionPolicyModel | None = retention_policy
        
        self._cleanup: CleanupQueue = cleanup
        self._logger: logging.Logger = logger
        
        self._id: str = str(uuid.uuid4())
        self._lock_holder: str | None = None
    
    async def apply_retention_policy(self) -> int:
        if not self._retention_policy:
            return -1
        
        self._logger.info(f'Applying retention policy: {self._retention_policy}')
        
        versions = await self._context.get_versions()
        
        if not versions:
            self._logger.info(f'No backup versions found. Nothing to prune')
            return 0
        
        protected = self._get_protected_versions(versions)
        versions_cnt = len(protected)
        
        if not versions_cnt:
            raise UsBackupRuntimeError(f'No protected versions generated. Pruning not possible')
        
        # exclude protected versions from the list
        prune = [version for version in versions if version.version not in protected]
        
        for version in prune:
            await self._context.remove_version(version)
            
        return versions_cnt
        
    def _get_protected_versions(self, versions: list[BackupVersionModel]) -> list:
        categories = {
            'last': {'prev': None, 'filter': None, 'versions': []},
            'hourly': {'prev': None, 'filter': '%Y-%m-%d %H', 'versions': []},
            'daily': {'prev': None, 'filter': '%Y-%m-%d', 'versions': []},
            'weekly': {'prev': None, 'filter': '%Y-%W', 'versions': []},
            'monthly': {'prev': None, 'filter': '%Y-%m', 'versions': []},
            'yearly': {'prev': None, 'filter': '%Y', 'versions': []},
        }
        
        date_now = datetime.datetime.now()
        
        for category, attr in categories.items():
            policy = getattr(self._retention_policy, category)
            if not policy:
                continue
    
            for version in versions:
                # stop processing if we reach the current date for given filter
                if attr['filter'] and version.date.strftime(attr['filter']) == date_now.strftime(attr['filter']):
                    break
                
                if not attr['prev']:
                    # always add first version
                    categories[category]['versions'].append(version.version)
                else:
                    if attr['filter'] and version.date.strftime(attr['filter']) == attr['prev'].strftime(attr['filter']):
                        # remove last version if it is the same as previous for given filter
                        categories[category]['versions'].pop()
                    
                    # add current version
                    categories[category]['versions'].append(version.version)
                        
                if len(categories[category]['versions']) > policy:
                    # remove oldest version if we have more than retention policy
                    categories[category]['versions'].pop(0)
                
                categories[category]['prev'] = version.date
                
        protected = []
        
        for category, attr in categories.items():
            if attr["versions"]: self._logger.info(f'{category} protected versions: {attr["versions"]}')
            protected += attr['versions']
            
        # always protect latest version
        protected.append(versions[-1].version)
        self._logger.debug(f'Last version protected: {versions[-1].version}')
        
        protected = list(set(protected))
        protected.sort()
                
        return protected

    async def _acquire_lock(self) -> bool:
        holder = f'{self._cleanup.claim()}/{self._id}'
        
        # registered before the lock exists, so the lock is never seen without a pending entry and taken over by mistake
        self._cleanup.push(f'remove_lock_{self._id}', 'remove_lock', path=self._context.lock_path.model_dump(), holder=holder)
        
        try:
            acquired = await self._context.acquire_lock(holder) or await self._take_over_stale_lock(holder)
        except Exception:
            self._cleanup.pop(f'remove_lock_{self._id}')
            raise
        
        if not acquired:
            self._cleanup.pop(f'remove_lock_{self._id}')
            return False
        
        self._lock_holder = holder
        
        return True
    
    async def _take_over_stale_lock(self, holder: str) -> bool:
        # a lock left by a dead process of this host, or abandoned by this process, is taken over instead of blocking the source forever
        current_holder = await self._context.get_lock_holder()
        
        if not current_holder or not self._cleanup.is_holder_dead(current_holder):
            return False
        
        # only removed if it still holds the stale holder, so a lock just taken by another run is never touched
        self._logger.warning(f'Removing stale lock left by "{current_holder}", which is no longer in use')
        await self._context.remove_lock_file(current_holder)
        
        return await self._context.acquire_lock(holder)
    
    async def _release_lock(self) -> None:
        if self._lock_holder is None:
            return
        
        try:
            await self._context.remove_lock_file(self._lock_holder)
        except Exception as e:
            # an abandoned lock is retried later and taken over by the next run, so the source is never blocked
            self._logger.error(f'Failed to release the lock, it will be released later. {e}')
            self._cleanup.abandon(f'remove_lock_{self._id}')
        else:
            self._cleanup.pop(f'remove_lock_{self._id}')
        
        self._lock_holder = None
    
    def _track_inconsistent_version(self, version: BackupVersionModel) -> None:
        # removes the version after a crash or an interrupted run, untracked once the version is complete
        self._cleanup.push(f'remove_inconsistent_version_{self._id}', 'remove_version', path=version.path.model_dump(), staging=self._context.get_removed_version_path(version).model_dump())
    
    def _untrack_inconsistent_version(self) -> None:
        self._cleanup.pop(f'remove_inconsistent_version_{self._id}')
    
    async def _remove_inconsistent_version(self, version: BackupVersionModel) -> None:
        self._logger.warning(f'Deleting inconsistent version')

        try:
            await self._context.remove_version(version)
        except Exception as e:
            # the tracked entry stays queued as abandoned, so the removal is retried later, on exit or after a crash
            self._logger.exception(f'Failed to delete inconsistent version. {e}')
            self._cleanup.abandon(f'remove_inconsistent_version_{self._id}')
            return
        
        self._untrack_inconsistent_version()