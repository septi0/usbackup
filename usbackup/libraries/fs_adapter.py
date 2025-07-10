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
        if not path.host.local:
            raise FsAdapterError("Local files only")
        
        await CmdExec.exec(["mkdir", "-p", path.path])
    
    @classmethod
    async def ls(cls, path: PathModel) -> list[str]:
        """
        List the contents of a directory at the specified path.
        """
        if not path.host.local:
            raise FsAdapterError("Local files only")
        
        try:
            list = await CmdExec.exec(["ls", path.path])
        except CmdExecProcessError as e:
            list = ''
        
        return list.splitlines()
    
    @classmethod
    async def rm(cls, path: PathModel) -> None:
        """
        Remove a directory at the specified path.
        """
        if not path.host.local:
            raise FsAdapterError("Local files only")
        
        await CmdExec.exec(["rm", "-rf", path.path])
        
    @classmethod
    async def touch(cls, path: PathModel) -> None:
        """
        Create an empty file at the specified path.
        """
        if not path.host.local:
            raise FsAdapterError("Local files only")

        await CmdExec.exec(["touch", path.path])

    @classmethod
    async def exists(cls, path: PathModel, type: str | None = None) -> bool:
        """
        Check if a file or directory exists at the specified path.
        """
        if not path.host.local:
            raise FsAdapterError("Local files only")
        
        try:
            if type == 'd':
                await CmdExec.exec(["test", "-d", path.path])
            elif type == 'f':
                await CmdExec.exec(["test", "-f", path.path])
            else:
                await CmdExec.exec(["test", "-e", path.path])
        except CmdExecProcessError as e:
            return False
        
        return True
    
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