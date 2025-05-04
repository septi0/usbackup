import logging
import asyncio
import shlex
from usbackup.models.host import HostModel

__all__ = ['CmdExec', 'CmdExecError']

class CmdExecError(Exception):
    pass

class CmdExecProcessError(Exception):
    def __init__(self, message, code):
        super().__init__(message)
        self.code = code

class CmdExec:
    @classmethod
    async def exec(cls, cmd: list, *, host: HostModel = None, input: str = None, env=None, stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE) -> str:
        if host and not host.local:
            cmd = cls.gen_ssh_cmd(cmd, host)
        
        logging.debug(f'Executing command: {[*cmd]}')
        
        if not env:
            env = None

        process = await asyncio.create_subprocess_exec(*cmd, stdin=stdin, stdout=stdout, stderr=stderr, env=env)

        if input:
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
    
    def gen_ssh_cmd(cmd: list, host: HostModel) -> list:
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
            
        return [*cmd_prefix, 'ssh', *ssh_opts, f'{host.user}@{host.host}', 'exec', shlex.join(cmd)]