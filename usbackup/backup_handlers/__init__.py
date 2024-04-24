from usbackup.backup_handlers.files import FilesHandler
from usbackup.backup_handlers.mysql import MysqlHandler
from usbackup.backup_handlers.openwrt import OpenWrtHandler
from usbackup.backup_handlers.postgresql import PostgreSqlHandler
from usbackup.backup_handlers.truenas import TruenasHandler

__all__ = ['list']

list = [
    FilesHandler,
    MysqlHandler,
    OpenWrtHandler,
    PostgreSqlHandler,
    TruenasHandler,
]