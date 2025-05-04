from typing import Literal
from usbackup.libraries.cmd_exec import CmdExec
from usbackup.libraries.fs_adapter import FsAdapter
from usbackup.models.path import PathModel
from usbackup.handlers.backup import HandlerBaseModel, BackupHandler, BackupHandlerError

class ProxmoxVmsHandlerModel(HandlerBaseModel):
    handler: str = 'proxmox_vms'
    limit: list[int] = []
    exclude: list[int] = []
    bwlimit: int = None
    mode: Literal['snapshot', 'suspend', 'stop'] = 'snapshot'
    compress: Literal['zstd', 'gzip', 'lzo', 'none'] = 'zstd'

class ProxmoxVmsHandler(BackupHandler):
    handler: str = 'proxmox_vms'
    
    def __init__(self, model: ProxmoxVmsHandlerModel, *args, **kwargs) -> None:
        super().__init__(model, *args, **kwargs)
        
        self._limit: list[int] = model.limit
        self._exclude: list[int] = model.exclude
        self._bwlimit: str = model.bwlimit
        self._mode: str = model.mode
        self._compress: str = model.compress

        self._compression_types = {
            'zstd': 'vma.zst',
            'gzip': 'vma.gz',
            'lzo': 'vma.lzo',
            'none': 'vma',
        }

    async def backup(self, dest: PathModel, dest_link: str = PathModel) -> None:
        self._logger.info(f'Fetching VM list from "{self._host}"')
        
        try:
            exec_ret = await CmdExec.exec(['qm', 'list'], host=self._host)
        except Exception as e:
            raise BackupHandlerError(f'Failed to fetch VM list: {e}', 1001)
        
        vms = [int(line.split()[0]) for line in exec_ret.splitlines()[1:] if line.strip()]
        
        if not vms:
            self._logger.info(f'No VMs found on "{self._host}"')
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
            
    async def _backup_vm(self, vm: int, dest: PathModel) -> None:
        cmd_options = [
            ('mode', self._mode),
            ('compress', self._compress),
            ('notification-policy', 'never'),
            'stdout',
            'quiet',
        ]
        
        if self._bwlimit:
            cmd_options.append(('bwlimit', self._bwlimit))
        
        cmd_options = CmdExec.parse_cmd_options(cmd_options)
        file_name = f'vzdump-qemu-{vm}.{self._compression_types[self._compress]}'

        async with FsAdapter.open(dest.join(file_name), 'wb') as f:
            self._logger.info(f'Streaming vzdump for VM {vm} from "{self._host}" to "{dest.path}"')
            
            await CmdExec.exec(['vzdump', str(vm), *cmd_options], stdout=f, host=self._host)