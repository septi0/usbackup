import asyncio
from usbackup.models.host import HostModel
from usbackup.libraries.cmd_exec import CmdExec, CmdExecProcessError
from typing import IO, Any

__all__ = ['RemoteCmd', 'RemoteCmdError']

class RemoteCmdError(Exception):
    """
    Custom exception for remote filesystem adapter errors.
    """
    pass

class RemoteCmd:
    @classmethod
    async def exec(
        cls, cmd: list,
        host: HostModel,
        *,
        input: str | None = None,
        env=None,
        stdin: int | IO[Any] | None = asyncio.subprocess.PIPE,
        stdout: int | IO[Any] | None = asyncio.subprocess.PIPE,
        stderr: int | IO[Any] | None = asyncio.subprocess.PIPE
    ) -> str:
        """
        Execute a command on a remote host using SSH.
        """
        if host.local:
            raise RemoteCmdError("Cannot execute command on a local host")
        
        return await CmdExec.exec(
            cmd,
            host=host,
            input=input,
            env=env,
            stdin=stdin,
            stdout=stdout,
            stderr=stderr
        )