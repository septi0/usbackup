class GracefulExit(SystemExit):
    code = 1
class UsbackupRuntimeError(Exception):
    pass