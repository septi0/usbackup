import sys
import argparse
from usbackup.manager import UsBackupManager
from usbackup.snapshot import UsBackupSnapshot
from usbackup.snapshot_level import UsBackupSnapshotLevel
from usbackup.exceptions import UsbackupConfigError, CmdExecError, ProcessError, HandlerError

APP_NAME = "usbackup"
APP_VERSION = "0.1.8"

def main():
    # get args from command line
    parser = argparse.ArgumentParser(description='A simple linux backup tool featuring snapshots, retention policies, backup handlers and report handlers')
    parser.add_argument('--config', dest='config_files', action='append', help='Config file(s) to use. This option is required')
    parser.add_argument('--snapshot', dest='snapshot_names', action='append', help='Snapshot name(s). If none specified, all snapshots will be run')
    parser.add_argument('--log', dest='log_file', help='Log file where to write logs')
    parser.add_argument('--log-level', dest='log_level', help='Log level', choices=['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'], default='INFO')
    parser.add_argument('--service', dest='service', action='store_true', help='Run as service. Wake up every minute to check if there are any backups to be performed')

    subparsers = parser.add_subparsers(title="Commands", dest="command")

    configtest_parser = subparsers.add_parser('configtest', help='Test configuration file')
    
    args = parser.parse_args()

    options = {}
    configtest = False
    
    options['config_files'] = args.config_files
    options['snapshot_names'] = args.snapshot_names
    options['log_file'] = args.log_file
    options['log_level'] = args.log_level
    options['service'] = args.service

    if args.command == 'configtest':
        configtest = True

    try:
        usbackup = UsBackupManager(options)
    except UsbackupConfigError as e:
        print(f"Config error: {e}\nCheck documentation for more information on how to configure usbackup snapshots")
        sys.exit(2)
    
    if configtest:
        print("Config OK")
    else:
        usbackup.run()