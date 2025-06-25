class GracefulExit(SystemExit):
    code = 1
class UsBackupRuntimeError(Exception):
    pass