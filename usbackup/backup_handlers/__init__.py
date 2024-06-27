from usbackup.backup_handlers.files import FilesHandler
from usbackup.backup_handlers.mysql import MysqlHandler
from usbackup.backup_handlers.openwrt_config import OpenwrtConfigHandler
from usbackup.backup_handlers.truenas_config import TruenasConfigHandler
from usbackup.backup_handlers.zfs_datasets import ZfsDatasetsHandler

__all__ = ['list']

list = [
    FilesHandler,
    MysqlHandler,
    OpenwrtConfigHandler,
    TruenasConfigHandler,
    ZfsDatasetsHandler,
]