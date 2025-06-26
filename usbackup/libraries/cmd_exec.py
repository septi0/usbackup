import logging
import asyncio
import shlex
from usbackup.models.host import HostModel
from typing import IO, Any

__all__ = ['CmdExec', 'CmdExecError', 'CmdExecProcessError']

class CmdExecError(Exception):
    pass

class CmdExecProcessError(Exception):
    def __init__(self, message: str, code: int | None = 0):
        super().__init__(message)
        self.code = code

class CmdExec:
    @classmethod
    async def exec(
        cls, cmd: list,
        *,
        host: HostModel | None = None,
        input: str | None = None,
        env=None,
        stdin: int | IO[Any] | None = asyncio.subprocess.PIPE,
        stdout: int | IO[Any] | None = asyncio.subprocess.PIPE,
        stderr: int | IO[Any] | None = asyncio.subprocess.PIPE
    ) -> str:
        if host and not host.local:
            cmd = cls.gen_ssh_cmd(cmd, host)
        
        logging.debug(f'Executing command: {[*cmd]}')
        
        if not env:
            env = None

        process = await asyncio.create_subprocess_exec(*cmd, stdin=stdin, stdout=stdout, stderr=stderr, env=env)

        if input and process.stdin is not None:
            process.stdin.write(input.encode('utf-8'))
            process.stdin.close()

        out, err = await process.communicate()
        
        if process.returncode != 0:
            raise CmdExecProcessError(err.decode('utf-8').strip(), process.returncode)

        result = ''

        if out:
            result = out.decode('utf-8').strip()
        
        return result
    
    @classmethod
    async def is_host_reachable(cls, host: HostModel) -> bool:
        try:
            await cls.exec(['echo', '1'], host=host)
        except CmdExecProcessError:
            return False
        
        return True
    
    @classmethod
    def parse_cmd_options(cls, options: list, *, arg_separator: str = ''):
        cmd_options = []
        
        for option in options:
            if isinstance(option, tuple):
                if arg_separator:
                    cmd_options.append(f'--{option[0]}{arg_separator}{option[1]}')
                else:
                    cmd_options.append(f'--{option[0]}')
                    cmd_options.append(option[1])
            else:
                cmd_options.append(f'--{option}')

        return cmd_options
    
    @classmethod
    def gen_ssh_cmd(cls, cmd: list, host: HostModel) -> list:
        if not cmd or not host:
            raise CmdExecError("Command or host not specified")

        cmd_prefix = []
        ssh_opts = []

        if host.password:
            cmd_prefix += ['sshpass', '-p', str(host.password)]
            logging.warning('Using password in plain is insecure. Consider using ssh keys instead')
        else:
            ssh_opts += ['-o', 'PasswordAuthentication=No', '-o', 'BatchMode=yes']

        if host.port:
            ssh_opts += ['-p', str(host.port)]
 
        remote = host.host
        
        if host.user is not None:
            remote = f"{host.user}@{remote}"
            
        return [*cmd_prefix, 'ssh', *ssh_opts, remote, 'exec', shlex.join(cmd)]