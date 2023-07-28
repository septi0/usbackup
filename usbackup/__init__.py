import sys
import argparse
from usbackup.manager import UsBackupManager
from usbackup.snapshot import UsBackupSnapshot
from usbackup.snapshot_level import UsBackupSnapshotLevel
from usbackup.exceptions import UsbackupConfigError, CmdExecError, ProcessError, HandlerError
from usbackup.info import __app_name__, __version__, __description__, __author__, __author_email__, __author_url__, __license__

def main():
    # get args from command line
    parser = argparse.ArgumentParser(description=__description__)
    
    parser.add_argument('--config', dest='config_files', action='append', help='Alternative config file(s)')
    parser.add_argument('--snapshot', dest='snapshot_names', action='append', help='Snapshot name(s). If none specified, all snapshots will be backed up')
    parser.add_argument('--log', dest='log_file', help='Log file where to write logs')
    parser.add_argument('--log-level', dest='log_level', help='Log level', choices=['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'], default='INFO')
    parser.add_argument('--version', action='version', version=f'{__app_name__} {__version__}')

    subparsers = parser.add_subparsers(title="Commands", dest="command")

    configtest_parser = subparsers.add_parser('configtest', help='Test configuration file (based on provided snapshots)')

    du_parser = subparsers.add_parser('du', help='Show disk usage of snapshots')

    backup_parser = subparsers.add_parser('backup', help='Backup snapshots')
    backup_parser.add_argument('--service', dest='service', action='store_true', help='Run as service. Wake up every minute to check if there are any backups to be performed')
    
    args = parser.parse_args()

    if args.command is None:
      parser.print_help()
      sys.exit()

    options = {
        'config_files': args.config_files,
        'snapshot_names': args.snapshot_names,
        'log_file': args.log_file,
        'log_level': args.log_level,
    }

    try:
        usbackup = UsBackupManager(options)
    except UsbackupConfigError as e:
        print(f"Config error: {e}\nCheck documentation for more information on how to configure usbackup snapshots")
        sys.exit(2)
    
    if args.command == 'configtest':
        print("Config OK")
        sys.exit(0)
    elif args.command == 'du':
        print("Checking disk usage of snapshots. This may take a while...")
        usages = usbackup.du()

        if usages:
            formatted_usages = ''
            
            for snapshot_name, usage in usages.items():
                formatted_usages += f"\n{snapshot_name}:\n"

                for level, versions in usage.items():
                    formatted_usages += f"  {level}:\n"

                    for (version, size) in versions:
                        formatted_usages += f"    {version}: {size}\n"
        else:
            formatted_usages = "No snapshots found"

        print(formatted_usages)
        sys.exit(0)
    elif args.command == 'backup':
        usbackup.backup(service=args.service)
        sys.exit(0)