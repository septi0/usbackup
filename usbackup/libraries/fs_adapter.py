from contextlib import contextmanager
from typing import Literal, IO, Any, Generator
from usbackup.libraries.cmd_exec import CmdExec, CmdExecProcessError
from usbackup.models.path import PathModel

__all__ = ['FsAdapter', 'FsAdapterError']

class FsAdapterError(Exception):
    """
    Custom exception for filesystem adapter errors.
    """
    pass

class FsAdapter:
    @classmethod
    async def mkdir(cls, path: PathModel) -> None:
        """
        Create a directory at the specified path.
        """
        await CmdExec.exec(["mkdir", "-p", path.path], host=path.host)
    
    @classmethod
    async def ls(cls, path: PathModel) -> list[str]:
        """
        List the contents of a directory at the specified path.
        """
        try:
            list = await CmdExec.exec(["ls", path.path], host=path.host)
        except CmdExecProcessError as e:
            list = ''
        
        return list.splitlines()
    
    @classmethod
    async def rm(cls, path: PathModel) -> None:
        """
        Remove a directory at the specified path.
        """
        await CmdExec.exec(["rm", "-rf", path.path], host=path.host)
        
    @classmethod
    async def touch(cls, path: PathModel) -> None:
        """
        Create an empty file at the specified path.
        """
        await CmdExec.exec(["touch", path.path], host=path.host)
    
    @classmethod
    async def exists(cls, path: PathModel, type: str | None = None) -> bool:
        """
        Check if a file or directory exists at the specified path.
        """
        
        try:
            if type == 'd':
                await CmdExec.exec(["test", "-d", path.path], host=path.host)
            elif type == 'f':
                await CmdExec.exec(["test", "-f", path.path], host=path.host)
            else:
                await CmdExec.exec(["test", "-e", path.path], host=path.host)
        except CmdExecProcessError as e:
            return False
        
        return True
    
    @classmethod
    async def rsync(cls, src: PathModel, dst: PathModel, *, options: list = []) -> str:
        """
        Copy a file or directory from src to dst using rsync.
        """
        if not src.host.local and not dst.host.local:
            raise FsAdapterError("Cannot copy from remote to remote")
        
        cmd_options = CmdExec.parse_cmd_options(options)
        cmd_prefix = []
        src_path = src.path
        dst_path = dst.path
        remote = None
        
        if not src.host.local:
            src_path = f'{src.host.host}:{src_path}'
            if src.host.user is not None: src_path = f'{src.host.user}@{src_path}'
            remote = src.host
        elif not dst.host.local:
            dst_path = f'{dst.host.host}:{dst_path}'
            if dst.host.user is not None: dst_path = f'{dst.host.user}@{dst_path}'
            remote = dst.host

        if remote:
            ssh_opts = []
            
            if remote.password:
                cmd_prefix += ['sshpass', '-p', str(remote.password)]
            else:
                ssh_opts += ['-o', 'PasswordAuthentication=No', '-o', 'BatchMode=yes']
                
            if remote.port:
                ssh_opts += ['-p', str(remote.port)]

            if ssh_opts:
                cmd_options += ['--rsh', f'ssh {" ".join(ssh_opts)}']
                
        cmd_options += ['--out-format', "%t %i %f", "--stats"]

        return await CmdExec.exec([*cmd_prefix, "rsync", *cmd_options, src_path, dst_path])
    
    @classmethod
    async def scp(cls, src: PathModel, dst: PathModel) -> str:
        """
        Copy a file or directory from src to dst using SCP.
        """
        if not src.host.local and not dst.host.local:
            raise FsAdapterError("Cannot copy from remote to remote")
        
        if src.host.local and dst.host.local:
            raise FsAdapterError("Cannot copy from local to local")
        
        cmd_options = []
        cmd_prefix = []
        
        src_path = src.path
        dst_path = dst.path
        remote = None
        
        if not src.host.local:
            src_path = f'{src.host.host}:{src_path}'
            if src.host.user is not None: src_path = f'{src.host.user}@{src_path}'
            remote = src.host
        elif not dst.host.local:
            dst_path = f'{dst.host.host}:{dst_path}'
            if dst.host.user is not None: dst_path = f'{dst.host.user}@{dst_path}'
            remote = dst.host
        
        if remote:
            if remote.password:
                cmd_prefix += ['sshpass', '-p', str(remote.password)]
            else:
                cmd_options += ['-o', 'PasswordAuthentication=No', '-o', 'BatchMode=yes']
                
            if remote.port:
                cmd_options += ['-P', str(remote.port)]
                
        return await CmdExec.exec([*cmd_prefix, "scp", *cmd_options, src_path, dst_path])
    
    @classmethod
    @contextmanager
    def open(
        cls,
        path: PathModel,
        mode: Literal["r", "w", "x", "a", "rb", "wb", "xb", "ab", "r+", "w+", "x+", "a+"] = 'r'
    ) -> Generator[IO[Any], None, None]:
        """Context manager that opens a file at the specified path."""
        if not path.host.local:
            raise FsAdapterError("Local files only")
        
        f = open(path.path, mode)
        try:
            yield f
        finally:
            f.close()