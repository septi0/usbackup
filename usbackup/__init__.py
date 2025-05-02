import sys
import argparse
from pydantic import ValidationError
from usbackup.manager import UsBackupManager
from usbackup.info import __app_name__, __version__, __description__, __author__, __author_email__, __author_url__, __license__

def main():
    # get args from command line
    parser = argparse.ArgumentParser(description=__description__)
    
    parser.add_argument('--config', dest='config_file', help='Alternative config file')
    parser.add_argument('--log', dest='log_file', help='Log file where to write logs')
    parser.add_argument('--log-level', dest='log_level', help='Log level', choices=['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'], default='INFO')
    parser.add_argument('--version', action='version', version=f'{__app_name__} {__version__}')

    subparsers = parser.add_subparsers(title="Commands", dest="command")
    
    configtest_parser = subparsers.add_parser('configtest', help='Test the configuration file')
    
    stats_parser = subparsers.add_parser('stats', help='Show statistics of hosts')
    stats_parser.add_argument('--limit', dest='limit', action='append', help='Host name(s) to check statistics for. If none specified, all hosts will be checked except those specified in --exclude')
    stats_parser.add_argument('--exclude', dest='exclude', action='append', help='Host name(s) excluded in statistics check')

    backup_parser = subparsers.add_parser('backup', help='Backup hosts. This option creates a backup job from the options provided')
    
    backup_parser.add_argument('--dest', dest='dest',  help='Destination folder. If not specified, the default destination from config will be used')
    backup_parser.add_argument('--limit', dest='limit', action='append', help='Host name(s) to backup. If none specified, all hosts will be backed up except those specified in --exclude')
    backup_parser.add_argument('--exclude', dest='exclude', action='append', help='Host name(s) to exclude in the backup')
    backup_parser.add_argument('--retention-policy', dest='retention_policy', help='Retention policy. last=<NR>,hourly=<NR>,daily=<daNRys>,weekly=<NR>,monthly=<NR>,yearly=<NR>. Example: --retention-policy last=6,hourly=24,daily=7,weekly=4,monthly=12,yearly=1')
    backup_parser.add_argument('--notification-policy', dest='notification_policy', default='always', type=str, help='Notification policy. Available options: never, always, on-failure. Default: always')
    backup_parser.add_argument('--concurrency', dest='concurrency', default=1, type=int, help='Concurrency. Number of concurrent hosts to backup. Default: 1')
    
    backup_parser = subparsers.add_parser('daemon', help='Run as daemon and perform actions based on configured jobs')
    
    args = parser.parse_args()

    if args.command is None:
      parser.print_help()
      sys.exit()

    try:
        usbackup = UsBackupManager(log_file=args.log_file, log_level=args.log_level, config_file=args.config_file)
    except ValidationError as e:
        print(f"Config error: {e}\nCheck documentation for more information on how to configure usbackup")
        sys.exit(2)
    
    if args.command == 'configtest':
        print("Configuration file is valid")
    elif args.command == 'backup':
        config = {
            'dest': args.dest,
            'limit': args.limit,
            'exclude': args.exclude,
            'retention_policy': args.retention_policy,
            'notification_policy': args.notification_policy,
            'concurrency': args.concurrency,
        }
        
        config = {k : v for k, v in config.items() if v is not None}
        
        usbackup.backup(daemon=False, config=config)
    elif args.command == 'daemon':
        usbackup.backup(daemon=True)

    sys.exit(0)