import os
import filecmp
from typing import Literal
from pydantic import field_validator
from usbackup.libraries.cmd_exec import CmdExec, CmdExecProcessError
from usbackup.models.path import PathModel
from usbackup.handlers.backup import HandlerBaseModel, BackupHandler, BackupHandlerError

class CommandHandlerModel(HandlerBaseModel):
    handler: str = 'command'
    cmd: str
    file: str
    compress: Literal['zstd', 'gzip', 'none'] = 'none'
    
    @field_validator('cmd', mode='after')
    @classmethod
    def validate_cmd(cls, cmd):
        if not cmd.strip():
            raise ValueError('Command must not be empty')
        
        return cmd
    
    @field_validator('file', mode='after')
    @classmethod
    def validate_file(cls, file):
        # the output always lands in the command folder of the version, never anywhere else
        if not file or '/' in file or file in ('.', '..'):
            raise ValueError(f'Invalid file "{file}". It must be a plain file name')
        
        return file
    
    @property
    def output_file(self) -> str:
        return self.file + {'zstd': '.zst', 'gzip': '.gz', 'none': ''}[self.compress]

class CommandHandler(BackupHandler):
    handler: str = 'command'
    
    def __init__(self, model: CommandHandlerModel, *args, **kwargs) -> None:
        super().__init__(model, *args, **kwargs)
        
        self._cmd: str = model.cmd
        self._file: str = model.output_file
        self._writer: str = {'zstd': 'zstd -q -c', 'gzip': 'gzip -c', 'none': 'cat'}[model.compress]
    
    async def backup(self, dest: PathModel, dest_link: PathModel | None = None) -> None:
        output = dest.join(self._file)
        
        self._logger.info(f'Streaming the output of "{self._cmd}" from "{self._host}" to "{output.path}"')
        
        # compressed on the backup server, so a failing command is never hidden behind a successful compressor
        try:
            await CmdExec.pipe(['sh', '-c', self._cmd], ['sh', '-c', f'{self._writer} > "$1"', 'sh', output.path], src_host=self._host)
        except CmdExecProcessError as e:
            raise BackupHandlerError(f'Command "{self._cmd}" failed: {e}', 1050)
        
        if dest_link:
            self._link_if_unchanged(output, dest_link.join(self._file))
    
    def _link_if_unchanged(self, output: PathModel, previous: PathModel) -> None:
        # an output identical to the one of the previous version takes no extra space
        if not os.path.isfile(previous.path) or not filecmp.cmp(previous.path, output.path, shallow=False):
            return
        
        temp_path = f'{output.path}.link'
        
        os.link(previous.path, temp_path)
        os.replace(temp_path, output.path)
        
        self._logger.info(f'Output unchanged, hard-linked "{output.path}" to the previous version')
