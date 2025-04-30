import os
import usbackup.cmd_exec as cmd_exec
from usbackup.backup_handlers.base import BackupHandler, BackupHandlerError

class ProxmoxVmsHandler(BackupHandler):
    handler: str = 'proxmox-vms'
    lexicon: dict = {
        'limit': {'type': list},
        'exclude': {'type': list},
        'bwlimit': {'type': int},
        'mode': {'type': str, 'default': 'snapshot', 'allowed': ['snapshot', 'suspend', 'stop']},
        'compress': {'type': str, 'default': 'zstd', 'allowed': ['zstd', 'gzip', 'lzo', 'none']},
    }
    
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        
        self._limit: list[int] = self._config.get("limit")
        self._exclude: list[int] = self._config.get("exclude")
        self._bwlimit: str = self._config.get("bwlimit")
        self._mode: str = self._config.get("mode")
        self._compress: str = self._config.get("compress")

        self._compression_types = {
            'zstd': 'vma.zst',
            'gzip': 'vma.gz',
            'lzo': 'vma.lzo',
            'none': 'vma',
        }

    async def backup(self, dest: str, dest_link: str = None) -> None:
        self._logger.info(f'Fetching VM list from "{self._src_host.host}"')
        
        try:
            exec_ret = await cmd_exec.exec_cmd(['qm', 'list'], host=self._src_host)
        except Exception as e:
            raise BackupHandlerError(f'Failed to fetch VM list: {e}', 1001)
        
        vms = [int(line.split()[0]) for line in exec_ret.splitlines()[1:] if line.strip()]
        
        if not vms:
            self._logger.info(f'No VMs found on "{self._src_host.host}"')
            return
        
        # Filter VMs based on limit/exclude lists
        if self._limit:
            vms = [vm for vm in vms if int(vm) in self._limit]
            
        if self._exclude:
            vms = [vm for vm in vms if int(vm) not in self._exclude]
            
        if not vms:
            self._logger.info(f'No VMs left to backup after limit/exclude filters')
            return
        
        self._logger.info(f'Backing up VMs "{vms}"')
        
        for vm in vms:
            await self._backup_vm(vm, dest)
            
    async def _backup_vm(self, vm: int, dest: str) -> None:
        cmd_options = [
            ('mode', self._mode),
            ('compress', self._compress),
            ('notification-policy', 'never'),
            'stdout',
            'quiet',
        ]
        
        if self._bwlimit:
            cmd_options.append(('bwlimit', self._bwlimit))
        
        cmd_options = cmd_exec.parse_cmd_options(cmd_options)
        file_name = f'vzdump-qemu-{vm}.{self._compression_types[self._compress]}'

        with open(os.path.join(dest, file_name), 'wb') as f:
            self._logger.info(f'Streaming vzdump for VM {vm} from "{self._src_host.host}" to "{dest}"')
            
            await cmd_exec.exec_cmd(['vzdump', str(vm), *cmd_options], stdout=f, host=self._src_host)