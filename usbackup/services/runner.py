import os
import logging
import datetime
import uuid

import usbackup.libraries.cmd_exec as cmd_exec
from usbackup.libraries.cleanup_queue import CleanupQueue
from usbackup.models.version import UsBackupVersionModel
from usbackup.models.retention_policy import UsBackupRetentionPolicyModel
from usbackup.services.context import UsBackupContext
from usbackup.exceptions import UsbackupRuntimeError
from usbackup.handlers import handler_factory

__all__ = ['UsBackupRunner']

class UsBackupRunner:
    def __init__(self, context: UsBackupContext, *, cleanup: CleanupQueue, logger: logging.Logger) -> None:
        self._context: UsBackupContext = context
        
        self._cleanup: CleanupQueue = cleanup
        self._logger: logging.Logger = logger
        
        self._id: str = str(uuid.uuid4())
        
    async def backup(self, retention_policy: UsBackupRetentionPolicyModel) -> None:
        if await self._context.lock_file_exists():
            raise UsbackupRuntimeError(f'Backup already running')
        
        # test connection to host
        if not await cmd_exec.is_host_reachable(self._context.source.host):
            raise UsbackupRuntimeError(f'Host" {self._context.source.host}" is not reachable')
            
        await self._context.create_lock_file()
        self._cleanup.add_job(f'remove_lock_{self._id}', self._context.remove_lock_file)
    
        version = await self._context.generate_version()
        latest_version = self._context.get_latest_version()

        for handler_model in self._context.source.handlers:
            handler_logger = self._logger.getChild(handler_model.handler)
            
            handler = handler_factory('backup', handler_model.handler, handler_model, self._context.source.host, cleanup=self._cleanup, logger=handler_logger)
           
            handler_dest = os.path.join(version.path, handler.handler)
            handler_dest_link = None
            
            if latest_version:
                self._logger.info(f'Using "{latest_version.path}" as dest link for "{handler.handler}" handler')
                handler_dest_link = os.path.join(latest_version.path, handler.handler)
                
            if not os.path.isdir(handler_dest):
                self._logger.info(f'Creating handler directory "{handler_dest}"')
                await cmd_exec.mkdir(handler_dest)
            
            self._logger.info(f'Performing backup via "{handler.handler}" handler')
            await handler.backup(handler_dest, handler_dest_link)
                
        await self._apply_retention_policy(retention_policy)

        await self._cleanup.run_job(f'remove_lock_{self._id}')
    
    # this function will delete backup versions according to the retention policy: e.g. {'last': 3, 'daily': 7, 'weekly': 4, 'monthly': 12, 'yearly': 1}
    async def _apply_retention_policy(self, retention_policy: UsBackupRetentionPolicyModel) -> int:
        if not retention_policy:
            return -1
        
        self._logger.info(f'Applying retention policy: {retention_policy}')
        
        versions = self._context.get_versions()
        
        if not versions:
            self._logger.info(f'No backup versions found. Nothing to prune')
            return 0
        
        protected = self._get_protected_versions(versions, retention_policy)
        versions_cnt = len(protected)
        
        if not versions_cnt:
            raise UsbackupRuntimeError(f'No protected versions generated. Pruning not possible')
        
        # exclude protected versions from the list
        prune = [version for version in versions if version.version not in protected]
        
        for version in prune:
            self._logger.info(f'Removing {version.path} based on retention policy')
            await self._context.remove_version(version)
            
        return versions_cnt
        
    def _get_protected_versions(self, versions: list[UsBackupVersionModel], retention_policy: UsBackupRetentionPolicyModel) -> list:
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
            policy = getattr(retention_policy, category)
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
            self._logger.debug(f'{category} protected versions: {attr["versions"]}')
            protected += attr['versions']
            
        # always protect latest version
        protected.append(versions[-1].version)
        self._logger.debug(f'Last version protected: {versions[-1].version}')
        
        protected = list(set(protected))
        protected.sort()
                
        return protected

