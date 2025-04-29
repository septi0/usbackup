import os
import shlex
import logging
import usbackup.cmd_exec as cmd_exec
from usbackup.backup_handlers.base import BackupHandler
from usbackup.remote import Remote
from usbackup.exceptions import HandlerError

class ProxmoxVmsHandler(BackupHandler):
    handler: str = 'proxmox-vms'
    
    def __init__(self, src_host: Remote, snapshot_name: str, config: dict):
        super().__init__(src_host, snapshot_name, config)
        
        self._exclude: list[str] = shlex.split(config.get("backup.proxmox-vms.exclude", ''))
        self._include: list[str] = shlex.split(config.get("backup.proxmox-vms.include", ''))
        self._bwlimit: str = config.get("backup.proxmox-vms.bwlimit", '0')
        self._mode: str = config.get("backup.proxmox-vms.mode", 'snapshot')
        self._compress: str = config.get("backup.proxmox-vms.compress", 'zstd')
        
        self._use_handler: bool = bool(config.get("backup.proxmox-vms", ''))

        self._modes = ['snapshot', 'suspend', 'stop']        
        self._compression_types = {
            'zstd': 'vma.zst',
            'gzip': 'vma.gz',
            'lzo': 'vma.lzo',
            'none': 'vma',
        }
        
        if self._mode not in self._modes:
            raise HandlerError(f'Invalid backup mode "{self._mode}"')
        
        if self._compress not in self._compression_types:
            raise HandlerError(f'Invalid compression type "{self._compress}"')

    async def backup(self, dest: str, dest_link: str = None, *, logger: logging.Logger = None) -> None:
        if not bool(self._use_handler):
            raise HandlerError(f'"proxmox-vms" handler not configured')
        
        logger = logger.getChild('proxmox-vms')
        
        logger.info(f'Fetching VM list from "{self._src_host.host}"')
        
        exec_ret = await cmd_exec.exec_cmd(['qm', 'list'], host=self._src_host)
        if not exec_ret:
            raise HandlerError(f'Failed to fetch VM list from "{self._src_host.host}"')
        
        lines = exec_ret.splitlines()
        
        vms = [int(line.split()[0]) for line in lines[1:] if line.strip()]
        
        # Filter VMs based on include/exclude lists
        if self._include:
            vms = [vm for vm in vms if str(vm) in self._include]
            
        if self._exclude:
            vms = [vm for vm in vms if str(vm) not in self._exclude]
            
        if not vms:
            logger.info(f'No VMs found to backup on "{self._src_host.host}"')
            return
        
        logger.info(f'Backing up {len(vms)} VMs on "{self._src_host.host}"')
        logger.debug(f'VMs to backup: {vms}')
        
        for vm in vms:
            await self._backup_vm(vm, dest, logger=logger)
            
    async def _backup_vm(self, vm: int, dest: str, *, logger: logging.Logger = None) -> None:
        cmd_options = [
            ('mode', self._mode),
            ('compress', self._compress),
            ('notification-policy', 'never'),
            ('bwlimit', self._bwlimit),
            'stdout',
            'quiet',
        ]
        
        cmd_options = cmd_exec.parse_cmd_options(cmd_options)
        file_name = f'vzdump-qemu-{vm}.{self._compression_types[self._compress]}'

        with open(os.path.join(dest, file_name), 'wb') as f:
            logger.info(f'Performing vzdump for VM {vm} on "{self._src_host.host}"')
            
            await cmd_exec.exec_cmd(['vzdump', str(vm), *cmd_options], stdout=f, host=self._src_host)