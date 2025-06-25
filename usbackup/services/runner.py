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
    def __init__(self, context: ContextService, retention_policy: RetentionPolicyModel, *, cleanup: CleanupQueue, logger: logging.Logger) -> None:
        self._context: ContextService = context
        self._retention_policy: RetentionPolicyModel = retention_policy
        
        self._cleanup: CleanupQueue = cleanup
        self._logger: logging.Logger = logger
        
        self._log_stream: io.StringIO = io.StringIO()
        self._id: str = str(uuid.uuid4())
        
        # bind stream to logger
        stream_handler = logging.StreamHandler(self._log_stream)
        stream_handler.setFormatter(NoExceptionFormatter('%(asctime)s - %(message)s'))
        self._logger.addHandler(stream_handler)
    
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
    
    def __del__(self) -> None:
        self._log_stream.close()