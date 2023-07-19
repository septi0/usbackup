from usbackup.backup_handlers.files import FilesHandler
from usbackup.backup_handlers.mysql import MysqlHandler
from usbackup.backup_handlers.openwrt import OpenWrtHandler

__all__ = ['list']

list = [
    FilesHandler,
    MysqlHandler,
    OpenWrtHandler,
]