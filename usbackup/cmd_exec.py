import logging
import asyncio
from usbackup.remote import Remote
from usbackup.exceptions import CmdExecError, ProcessError

__all__ = ['exec_cmd', 'mkdir', 'copy', 'move', 'remove', 'mount', 'mount_all', 'umount', 'umount_all', 'mounted', 'rsync', 'tar', 'ssh', 'scp', 'du']

async def exec_cmd(cmd: list, *, host: Remote = None, input: str = None, env=None, stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE) -> str:
    if host and not host.local:
        cmd = gen_ssh_cmd(cmd, host)
    
    logging.debug(f'Executing command: {[*cmd]}')
    
    if not env:
        env = None

    process = await asyncio.create_subprocess_exec(*cmd, stdin=stdin, stdout=stdout, stderr=stderr, env=env)

    if input:
        process.stdin.write(input.encode('utf-8'))
        process.stdin.close()

    out, err = await process.communicate()

    if process.returncode != 0:
        raise ProcessError(err.decode('utf-8').strip(), process.returncode)

    result = ''

    if out:
        result = out.decode('utf-8').strip()
    
    return result

async def mkdir(path: str, *, host: Remote = None):
    if not path:
        raise CmdExecError("Path not specified")

    return await exec_cmd(["mkdir", "-p", path], host=host)

async def copy(src: str, dst: str, *, host: Remote = None):
    if not src or not dst:
        raise CmdExecError("Source or destination not specified")

    return await exec_cmd(["cp", src, dst], host=host)

async def move(src: str, dst: str, *, host: Remote = None):
    if not src or not dst:
        raise CmdExecError("Source or destination not specified")

    return await exec_cmd(["mv", src, dst], host=host)

async def remove(path: str, *, host: Remote = None):
    if not path:
        raise CmdExecError("Path not specified")

    return await exec_cmd(["rm", "-rf", path], host=host)

async def mount(mount: str, *, host: Remote = None):
    if not mount:
        raise CmdExecError("Mount dir not specified")

    return await exec_cmd(["mount", mount], host=host)

async def mount_all(mount_list: list, *, host: Remote = None):
    for m in mount_list:
        mount(m, host=host)

async def umount(umount: str, *, host: Remote = None):
    if not umount:
        raise CmdExecError("Umount dir not specified")

    return await exec_cmd(["umount", umount], host=host)

async def umount_all(umount_List: list, *, host: Remote = None):
    for u in umount_List:
        umount(u, host=host)

async def mounted(mount: str, *, host: Remote = None):
    if not mount:
        raise CmdExecError("Mount dir not specified")

    return await exec_cmd(["mountpoint", "-q", mount], host=host)

async def rsync(src: str, dst: str, *, host: Remote = None, options: list = []):
    if not src or not dst:
        raise CmdExecError("Source or destination not specified")

    cmd_options = parse_cmd_options(options)

    cmd_prefix = []
    ssh_opts = []
    
    if host and not host.local:
        src = f'{host.user}@{host.host}:{src}'
        
        if host.password:
            cmd_prefix += ['sshpass', '-p', str(host.password)]
            logging.warning('Using password in plain is insecure. Consider using ssh keys instead')
        else:
            ssh_opts += ['-o', 'PasswordAuthentication=No', '-o', 'BatchMode=yes']
            
        if host.port:
            ssh_opts += ['-p', str(host.port)]

    if ssh_opts:
        cmd_options += ['--rsh', f'ssh {" ".join(ssh_opts)}']

    return await exec_cmd([*cmd_prefix, "rsync", *cmd_options, src, dst])

async def tar(dst: str, src: list[str], *, host: Remote = None):
    if not dst or not src:
        raise CmdExecError("Source or destination not specified")

    return await exec_cmd(["tar", "-czf", dst, *src], host=host)

async def du(path: str, *, host: Remote = None, match: str = None):
    if not path:
        raise CmdExecError("Path not specified")
    
    if match:
        return await exec_cmd(["find", path, "-maxdepth", '1', "-name", match, '-exec', 'du', '-sk', '{}', '+'], host=host)
    else:
        return await exec_cmd(["du", "-sk", path], host=host)

def parse_cmd_options(options: list, *, use_equal: bool = True):
    cmd_options = []
    
    for option in options:
        if isinstance(option, tuple):
            if use_equal:
                cmd_options.append(f'--{option[0]}={option[1]}')
            else:
                cmd_options.append(f'--{option[0]}')
                cmd_options.append(option[1])
        else:
            cmd_options.append(f'--{option}')

    return cmd_options

def gen_ssh_cmd(cmd: list, host: Remote) -> list:
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
        
    return [*cmd_prefix, 'ssh', *ssh_opts, f'{host.user}@{host.host}', *cmd]