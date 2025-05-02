import importlib

__all__ = ['handler_factory']

_class_cache = {}

def handler_factory(submodule: str, *, name: str, entity: str = 'handler'):
    cache_key = name + entity
    if cache_key in _class_cache:
        return _class_cache[cache_key]
    
    try:
        module = importlib.import_module(f'usbackup.handlers.{submodule}.{name}')
    except ImportError as e:
        raise ImportError(f'Submodule "handlers.{submodule}.{name}" could not be imported: {e}')
    
    class_name = name.replace("_", " ").title().replace(" ", "")
    
    if (entity == 'handler'):
        class_name = class_name + 'Handler'
    elif (entity == 'model'):
        class_name = class_name + 'HandlerModel'
    else:
        raise ValueError(f"Invalid entity type: {entity}")
    
    if not hasattr(module, class_name):
        raise ImportError(f"Class {class_name} not found in module {module.__name__}")
    
    obj_class = getattr(module, class_name)
    
    _class_cache[cache_key] = obj_class
    
    return obj_class