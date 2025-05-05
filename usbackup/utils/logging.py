import logging

class NoExceptionFormatter(logging.Formatter):
    def format(self, record):
        exc_info = record.exc_info
        record.exc_info = None
        
        formatted = super().format(record)
        
        record.exc_info = exc_info
        
        return formatted