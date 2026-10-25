import logging
import asyncio
import hashlib
import shlex
import os
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
    # private directory holding the control sockets of reusable ssh connections, None disables reuse
    _ssh_control_dir: str | None = None
    # one reusable connection per remote host, closed on exit
    _ssh_connections: dict[str, HostModel] = {}
    # idle reusable connections close themselves after this many seconds
    _ssh_control_persist: int = 60
    # unreachable hosts fail after 30 s and dead connections are detected within about a minute, instead of hanging
    ssh_timeout_opts: list[str] = ['-o', 'ConnectTimeout=30', '-o', 'ServerAliveInterval=15', '-o', 'ServerAliveCountMax=4']
    
    @classmethod
    async def exec(
        cls, cmd: list,
        *,
        host: HostModel | None = None,
        reuse_ssh: bool = False,
        input: str | None = None,
        env=None,
        stdin: int | IO[Any] | None = asyncio.subprocess.PIPE,
        stdout: int | IO[Any] | None = asyncio.subprocess.PIPE,
        stderr: int | IO[Any] | None = asyncio.subprocess.PIPE
    ) -> str:
        if host and not host.local:
            cmd = cls.gen_ssh_cmd(cmd, host, reuse=reuse_ssh)
            env = cls.gen_ssh_env(host, env)
        
        logging.debug(f'Executing command: {[*cmd]}')
        
        if not env:
            env = None

        process = await asyncio.create_subprocess_exec(*cmd, stdin=stdin, stdout=stdout, stderr=stderr, env=env)

        if input and process.stdin is not None:
            process.stdin.write(input.encode('utf-8'))
            process.stdin.close()

        try:
            out, err = await process.communicate()
        except asyncio.CancelledError:
            await cls._terminate(process)
            raise
        
        if process.returncode != 0:
            raise CmdExecProcessError(cls._gen_error_message(cmd, err, process.returncode), process.returncode)

        result = ''

        if out:
            result = out.decode('utf-8').strip()
        
        return result
    
    @classmethod
    async def pipe(cls, src_cmd: list, dst_cmd: list, *, dst_host: HostModel | None = None, reuse_ssh: bool = False) -> None:
        """
        Run src_cmd locally and pipe its stdout into stdin of dst_cmd.
        dst_cmd can optionally run on a remote host via SSH.
        """
        dst_env = None
        
        if dst_host and not dst_host.local:
            dst_cmd = cls.gen_ssh_cmd(dst_cmd, dst_host, reuse=reuse_ssh)
            dst_env = cls.gen_ssh_env(dst_host)

        logging.debug(f'Piping: {src_cmd} | {dst_cmd}')

        r_fd, w_fd = os.pipe()

        try:
            src_proc = await asyncio.create_subprocess_exec(*src_cmd, stdout=w_fd, stderr=asyncio.subprocess.PIPE)
            dst_proc = await asyncio.create_subprocess_exec(*dst_cmd, stdin=r_fd, stderr=asyncio.subprocess.PIPE, env=dst_env)
        finally:
            os.close(w_fd)
            os.close(r_fd)

        try:
            (_, src_err), (_, dst_err) = await asyncio.gather(src_proc.communicate(), dst_proc.communicate())
        except asyncio.CancelledError:
            await asyncio.gather(cls._terminate(src_proc), cls._terminate(dst_proc))
            raise

        if src_proc.returncode != 0:
            raise CmdExecProcessError(cls._gen_error_message(src_cmd, src_err, src_proc.returncode), src_proc.returncode)

        if dst_proc.returncode != 0:
            raise CmdExecProcessError(cls._gen_error_message(dst_cmd, dst_err, dst_proc.returncode), dst_proc.returncode)
    
    @classmethod
    def _gen_error_message(cls, cmd: list, stderr: bytes | None, code: int | None) -> str:
        # stderr is None when the caller did not capture it
        message = (stderr or b'').decode('utf-8').strip()
        
        # commands failing without any output still get a meaningful message
        if not message:
            message = f'Command "{cmd[0]}" exited with code {code}'
        
        return message
    
    @classmethod
    async def _terminate(cls, process: asyncio.subprocess.Process, timeout: float = 10) -> None:
        """
        Terminate a running process, killing it if it does not exit within the timeout.
        """
        if process.returncode is not None:
            return
        
        try:
            process.terminate()
        except ProcessLookupError:
            return
        
        try:
            await asyncio.wait_for(process.wait(), timeout)
        except asyncio.TimeoutError:
            try:
                process.kill()
            except ProcessLookupError:
                pass
            
            await process.wait()

    @classmethod
    async def is_host_reachable(cls, host: HostModel) -> bool:
        try:
            await cls.exec(['ping', '-c', '1', host.host])
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
    def gen_ssh_cmd(cls, cmd: list, host: HostModel, *, reuse: bool = False) -> list:
        if not cmd or not host:
            raise CmdExecError("Command or host not specified")

        if host.password:
            logging.warning('Using password in plain is insecure. Consider using ssh keys instead')
        
        cmd_prefix, ssh_opts = cls.gen_ssh_opts(host, reuse=reuse)
        
        return [*cmd_prefix, 'ssh', *ssh_opts, cls._gen_ssh_remote(host), 'exec', shlex.join(cmd)]
    
    @classmethod
    def gen_ssh_opts(cls, host: HostModel, *, reuse: bool = False) -> tuple[list, list]:
        """
        Generate the command prefix and the ssh options needed to connect to host.
        """
        cmd_prefix = []
        ssh_opts = [*cls.ssh_timeout_opts]

        # the password is passed through the environment (see gen_ssh_env), never on the command line where ps and logs can see it
        if host.password:
            cmd_prefix += ['sshpass', '-e']
        else:
            ssh_opts += ['-o', 'PasswordAuthentication=No', '-o', 'BatchMode=yes']

        if host.port:
            ssh_opts += ['-p', str(host.port)]
 
        control_path = cls._get_ssh_control_path(host) if reuse else None
        
        if control_path:
            ssh_opts += ['-o', 'ControlMaster=auto', '-o', f'ControlPath={control_path}', '-o', f'ControlPersist={cls._ssh_control_persist}']
        
        return cmd_prefix, ssh_opts
    
    @classmethod
    def gen_ssh_env(cls, host: HostModel, env: dict | None = None) -> dict | None:
        """
        Generate the environment needed to connect to host, extending env (or the current environment).
        """
        if not host.password:
            return env
        
        return {**(env or os.environ), 'SSHPASS': str(host.password)}
    
    @classmethod
    def enable_ssh_reuse(cls, control_dir: str) -> bool:
        """
        Enable reusable ssh connections with control sockets in control_dir. Returns False if the directory is not safe to use.
        """
        try:
            os.makedirs(control_dir, mode=0o700, exist_ok=True)
            stat = os.stat(control_dir)
            
            if stat.st_uid != os.getuid():
                return False
            
            # a control socket grants access to its authenticated connection, so only the owner may reach it
            if stat.st_mode & 0o077:
                os.chmod(control_dir, 0o700)
        except OSError:
            return False
        
        # unix socket paths are limited to 108 bytes, control socket names are 40 characters long
        if len(control_dir) + 41 >= 108:
            return False
        
        cls._ssh_control_dir = control_dir
        
        return True
    
    @classmethod
    async def close_ssh_connections(cls) -> None:
        """
        Close the reusable ssh connections opened by this process.
        """
        for control_path, host in list(cls._ssh_connections.items()):
            del cls._ssh_connections[control_path]
            
            if not os.path.exists(control_path):
                continue
            
            try:
                await cls.exec(['ssh', '-o', f'ControlPath={control_path}', '-O', 'exit', cls._gen_ssh_remote(host)])
            except CmdExecProcessError as e:
                logging.debug(f'Failed to close ssh connection {control_path}: {e}')
    
    @classmethod
    def _get_ssh_control_path(cls, host: HostModel) -> str | None:
        if cls._ssh_control_dir is None:
            return None
        
        # connections are per process, so a process closing its connections on exit never cuts off another one
        connection = f'{os.getpid()}/{host.user}@{host.host}:{host.port}'
        control_path = os.path.join(cls._ssh_control_dir, hashlib.sha1(connection.encode('utf-8')).hexdigest())
        
        cls._ssh_connections[control_path] = host
        
        return control_path
    
    @classmethod
    def _gen_ssh_remote(cls, host: HostModel) -> str:
        if host.user is not None:
            return f"{host.user}@{host.host}"
            
        return host.host