import importlib

__all__ = ['dynamic_loader']

_class_cache = {}

def dynamic_loader(handler: str):
    if handler in _class_cache:
        return _class_cache[handler]
    
    module = importlib.import_module(f'usbackup.notification_handlers.{handler}')
    handler_class = getattr(module, f'{handler.replace("_", " ").title().replace(" ", "")}Handler')
    
    _class_cache[handler] = handler_class
    
    return handler_class