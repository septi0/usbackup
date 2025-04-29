import os
import yaml
import re
from usbackup.backup_handlers import dynamic_loader as backup_handler_loader
from usbackup.notification_handlers import dynamic_loader as notification_handler_loader

__all__ = ['UsBackupConfigParser']

class UsBackupConfigParser:
    lexicon: dict = {
        'hosts': {
            'required': True,
            'type': list,
            'children': {
                'name': {'required': True, 'type': str},
                'host': {'required': True, 'type': str, 'allowed-pattern': r'^(([^:@]+)(?::([^@]+))?@)?([^:\/]+)(?::(\d+))?$'},
                'backup': {
                    'required': True,
                    'type': list,
                    'children': {
                        'handler': {'required': True, 'type': str},
                    },
                },
            },
        },
        'jobs': {
            'type': list,
            'children': {
                'name': {'required': True, 'type': str},
                'dest': {'required': True, 'type': str},
                'limit': {'type': list},
                'exclude': {'type': list},
                'schedule': {'type': str, 'default': '0 0 * * *', 'allowed-pattern': r'^(\*|(\d+|\*\/\d+|\d+-\d+|\d+(,\d+)*))(\s+(\*|(\d+|\*\/\d+|\d+-\d+|\d+(,\d+)*))){4}$'},
                'retention-policy': {
                    'type': dict,
                    'children': {
                        'last': {'type': int, 'allowed-pattern': r'^[1-9]+$'},
                        'hourly': {'type': int, 'allowed-pattern': r'^[1-9]+$'},
                        'daily': {'type': int, 'allowed-pattern': r'^[1-9]+$'},
                        'weekly': {'type': int, 'allowed-pattern': r'^[1-9]+$'},
                        'monthly': {'type': int, 'allowed-pattern': r'^[1-9]+$'},
                        'yearly': {'type': int, 'allowed-pattern': r'^[1-9]+$'},
                    },
                },
                'notification-policy': {'type': str, 'default': 'always', 'allowed': ['never', 'always', 'on-failure']},
                'concurrency': {'type': int, 'default': 1, 'allowed-pattern': r'^[1-9]+$'},
                'pre_backup_cmd': {'type': str},
                'post_backup_cmd': {'type': str},
            },
        },
        'notification': {
            'type': list,
            'children': {
                'handler': {'required': True, 'type': str},
            },
        },
    }
    
    def __init__(self, *, file: str = None, config: dict = {}, section: str = None) -> None:
        if file and config:
            raise UsbackupConfigError("Cannot specify both file and config")
        
        if not file and not config:
            raise UsbackupConfigError("Must specify either file or config")
        
        if file:
            unsafe_config = self._load(file)
        
        if config:
            unsafe_config = config
            
        self._config: dict = self._parse(unsafe_config, section=section)
        
    def __getitem__(self, key: str) -> any:
        return self._config[key]
    
    def get(self, key: str, default: any = None) -> any:
        return self._config.get(key, default)
    
    def get_all(self) -> dict:
        return self._config
        
    def _load(self, config_file: str) -> dict:
        config = {}
        
        with open(config_file, 'r') as f:
            try:
                config = yaml.safe_load(f)
            except yaml.YAMLError as e:
                raise UsbackupConfigError(f"Failed to parse config file: {e}")
            
        return config
            
    def _parse(self, config: dict, *, section: str = None) -> dict:
        if section and section not in self.lexicon:
            raise UsbackupConfigError(f"Invalid section: {section}")
        
        lexicon = {'children': self.lexicon[section]['children']} if section else {'children': self.lexicon}
        
        return self._check_config('', lexicon, config)
    
    def _check_config(self, key: str, definition: dict, value: any) -> any:
        key = key.lstrip('.')
        
        if value is None and 'default' in definition:
            value = definition['default']
        
        if value is None and definition.get('required'):
            raise UsbackupConfigError(f"Missing required key: {key}")
        
        if value is None:
            return value
        
        if value is not None:
            if 'type' in definition and not isinstance(value, definition['type']):
                raise UsbackupConfigError(f"Invalid type for key: {key}. Expected {definition['type'].__name__}, got {type(value).__name__}")
            
            if 'allowed' in definition and value not in definition['allowed']:
                raise UsbackupConfigError(f"Invalid value for key: {key}. Expected one of {definition['allowed']}, got {value}")
            
            if 'allowed-pattern' in definition and not re.match(definition['allowed-pattern'], str(value)):
                raise UsbackupConfigError(f"Invalid value for key: {key}. Expected pattern {definition['allowed-pattern']}, got {value}")
        
        if 'children' in definition:
            if isinstance(value, list):
                for index, item in enumerate(value):
                    children = definition['children'].copy()
                    
                    try:
                        # we have dynamic lex for backup and notification handlers
                        if key == 'hosts.backup' and 'handler' in item: children = backup_handler_loader(item['handler']).lexicon | children
                        if key == 'notification' and 'handler' in item: children = notification_handler_loader(item['handler']).lexicon | children
                    except Exception as e:
                        raise UsbackupConfigError(f"Inexistent handler: {item['handler']}. Error: {e}")
                    
                    for child_key, child_definition in children.items():
                        value[index][child_key] = self._check_config(f'{key}.{child_key}', child_definition, item.get(child_key))
                        
                    self._check_extra_keys(children, item)
            elif isinstance(value, dict):
                for child_key, child_definition in definition['children'].items():
                    value[child_key] = self._check_config(f'{key}.{child_key}', child_definition, value.get(child_key))
                    
                self._check_extra_keys(definition['children'], value)
            else:
                raise UsbackupConfigError(f"Invalid type for key: {key}. Expected list or dict, got {type(value).__name__}")
            
        return value
            
    def _check_extra_keys(self, definition: dict, value: any) -> None:
        if not isinstance(value, dict):
            raise UsbackupConfigError(f"Invalid type for items: {type(value).__name__}. Expected dict")
        
        unknown_keys = set(value.keys()) - set(definition.keys())
        
        if unknown_keys:
            raise UsbackupConfigError(f"Unknown keys found: {', '.join(unknown_keys)}")
    
class UsbackupConfigError(Exception):
    pass