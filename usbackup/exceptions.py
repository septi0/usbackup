class GracefulExit(BaseException):
    pass

class UsbackupConfigError(Exception):
    pass

class CmdExecError(Exception):
    pass

# raise processError(message, code)
class ProcessError(Exception):
    def __init__(self, message, code):
        super().__init__(message)
        self.code = code

class HandlerError(Exception):
    pass