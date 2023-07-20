import logging
import subprocess
from usbackup.exceptions import CmdExecError, ProcessError

__all__ = ['exec_cmd', 'mkdir', 'copy', 'move', 'remove', 'mount', 'mount_all', 'umount', 'umount_all', 'rsync', 'tar']

def exec_cmd(cmd: list, *, input: str = None, stdout=subprocess.PIPE, stderr=subprocess.PIPE):
    logging.debug(f'Executing command: {[*cmd]}')

    out = subprocess.run([*cmd], input=input, stdout=stdout, stderr=stderr)

    if out.returncode != 0:
        raise ProcessError(out.stderr.decode('utf-8'), out.returncode)

    if out.stdout:
        return out.stdout.decode('utf-8')
    
    return ''

def mkdir(path: str):
    if not path:
        raise CmdExecError("Path not specified")

    return exec_cmd(["mkdir", "-p", path])

def copy(src: str, dst: str):
    if not src or not dst:
        raise CmdExecError("Source or destination not specified")

    return exec_cmd(["cp", src, dst])

def move(src: str, dst: str):
    if not src or not dst:
        raise CmdExecError("Source or destination not specified")

    return exec_cmd(["mv", src, dst])

def remove(path: str):
    if not path:
        raise CmdExecError("Path not specified")

    return exec_cmd(["rm", "-rf", path])

def mount(mount: str):
    if not mount:
        raise CmdExecError("Mount dir not specified")

    return exec_cmd(["mount", mount])

def mount_all(mount_list: list):
    for m in mount_list:
        mount(m)

def umount(umount: str):
    if not umount:
        raise CmdExecError("Umount dir not specified")

    return exec_cmd(["umount", umount])

def umount_all(umount_List: list):
    for u in umount_List:
        umount(u)

def rsync(src: str, dst: str, *, options: list = [], password: str = None):
    if not src or not dst:
        raise CmdExecError("Source or destination not specified")

    cmd_options = parse_cmd_options(options)

    cmd_prefix = []

    if password:
        cmd_prefix = ["sshpass", "-p", str(password)]

    return exec_cmd([*cmd_prefix, "rsync", *cmd_options, src, dst])

def tar(dst: str, src: list[str]):
    if not dst or not src:
        raise CmdExecError("Source or destination not specified")

    return exec_cmd(["tar", "-czf", dst, *src])

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