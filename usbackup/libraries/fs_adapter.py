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
    # exit code ssh returns when the connection itself fails
    _ssh_connection_error: int = 255
    # exit code used by create_exclusive when the file already exists
    _exists_error: int = 17
    
    @classmethod
    async def mkdir(cls, path: PathModel) -> None:
        """
        Create a directory at the specified path.
        """
        await cls._exec(path, ["mkdir", "-p", path.path])
    
    @classmethod
    async def ls(cls, path: PathModel) -> list[str]:
        """
        List the contents of a directory at the specified path.
        """
        try:
            list = await cls._exec(path, ["ls", path.path])
        except CmdExecProcessError as e:
            cls._raise_connection_error(path, e)
            list = ''
        
        return list.splitlines()
    
    @classmethod
    async def rm(cls, path: PathModel) -> None:
        """
        Remove a directory at the specified path.
        """
        await cls._exec(path, ["rm", "-rf", path.path])
        
    @classmethod
    async def mv(cls, src: PathModel, dst: PathModel) -> None:
        """
        Rename a file or directory. Fails instead of moving src inside dst if dst is an existing directory.
        """
        if src.host != dst.host:
            raise FsAdapterError("Source and destination must be on the same host")
        
        await cls._exec(src, ["mv", "-T", src.path, dst.path])
        
    @classmethod
    async def touch(cls, path: PathModel) -> None:
        """
        Create an empty file at the specified path.
        """
        await cls._exec(path, ["touch", path.path])

    @classmethod
    async def remove_atomically(cls, path: PathModel, staging: PathModel) -> None:
        """
        Remove a directory by renaming it to staging first, so an interrupted removal never leaves a partial directory at path.
        """
        if await cls.exists(path, 'd'):
            await cls.mv(path, staging)
        
        await cls.rm(staging)
    
    @classmethod
    async def read_text(cls, path: PathModel) -> str | None:
        """
        Return the content of the file at the specified path, or None if it cannot be read.
        """
        try:
            return await cls._exec(path, ["cat", path.path])
        except CmdExecProcessError as e:
            cls._raise_connection_error(path, e)
            return None
    
    @classmethod
    async def remove_if_content(cls, path: PathModel, content: str) -> None:
        """
        Remove the file at the specified path only if it holds exactly content.
        """
        await cls._exec(path, ["sh", "-c", 'if [ "$(cat "$1" 2>/dev/null)" = "$2" ]; then rm -f "$1"; fi', "sh", path.path, content])
    
    @classmethod
    async def create_exclusive(cls, path: PathModel, content: str = '') -> bool:
        """
        Atomically create a file holding content at the specified path. Returns False if the file already exists.
        """
        # the content is written to a temporary file and hard linked into place, so the file never exists partially written
        script = f'printf "%s" "$2" > "$1.$$" || exit 1; ln "$1.$$" "$1" 2>/dev/null; linked=$?; rm -f "$1.$$"; if [ $linked -eq 0 ]; then exit 0; elif [ -e "$1" ]; then exit {cls._exists_error}; else echo "cannot create $1" >&2; exit 1; fi'
        
        try:
            await cls._exec(path, ["sh", "-c", script, "sh", path.path, content])
        except CmdExecProcessError as e:
            if e.code == cls._exists_error:
                return False
            
            raise
        
        return True

    @classmethod
    async def exists(cls, path: PathModel, type: str | None = None) -> bool:
        """
        Check if a file or directory exists at the specified path.
        """
        try:
            if type == 'd':
                await cls._exec(path, ["test", "-d", path.path])
            elif type == 'f':
                await cls._exec(path, ["test", "-f", path.path])
            else:
                await cls._exec(path, ["test", "-e", path.path])
        except CmdExecProcessError as e:
            cls._raise_connection_error(path, e)
            return False
        
        return True
    
    @classmethod
    async def symlink(cls, path: PathModel, target: str) -> None:
        """
        Create or replace a symlink at the specified path pointing to target.
        """
        await cls._exec(path, ["ln", "-sfn", target, path.path])

    @classmethod
    async def readlink(cls, path: PathModel) -> str | None:
        """
        Return the target of the symlink at the specified path, or None if it is not a symlink.
        """
        try:
            return await cls._exec(path, ["readlink", path.path])
        except CmdExecProcessError as e:
            cls._raise_connection_error(path, e)
            return None

    @classmethod
    @contextmanager
    def open(
        cls,
        path: PathModel,
        mode: Literal["r", "w", "x", "a", "rb", "wb", "xb", "ab", "r+", "w+", "x+", "a+"] = 'r'
    ) -> Generator[IO[Any], None, None]:
        """Context manager that opens a file at the specified path."""
        if path.protocol != 'local_fs':
            raise FsAdapterError("Local files only")
        
        f = open(path.path, mode)
        try:
            yield f
        finally:
            f.close()
    
    @classmethod
    async def _exec(cls, path: PathModel, cmd: list) -> str:
        if path.protocol not in ('local_fs', 'ssh'):
            raise FsAdapterError(f'Unsupported protocol "{path.protocol}"')
        
        # remote paths reuse ssh connections since storage operations run many short commands
        return await CmdExec.exec(cmd, host=path.host, reuse_ssh=True)
    
    @classmethod
    def _raise_connection_error(cls, path: PathModel, error: CmdExecProcessError) -> None:
        # a failed command means the answer is negative, a failed connection means there is no answer
        if path.protocol == 'ssh' and error.code == cls._ssh_connection_error:
            raise error