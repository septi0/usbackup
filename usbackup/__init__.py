import sys
import argparse
import datetime
from pydantic import ValidationError
from usbackup.manager import UsBackupManager
from usbackup.info import __app_name__, __version__, __description__, __author__, __author_email__, __author_url__, __license__

def main():
    # get args from command line
    parser = argparse.ArgumentParser(description=__description__)
    
    parser.add_argument('--config', dest='config_file', help='Alternative config file')
    parser.add_argument('--log', dest='log_file', help='Log file where to write logs')
    parser.add_argument('--log-level', dest='log_level', help='Log level', choices=['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'])
    parser.add_argument('--version', action='version', version=f'{__app_name__} {__version__}')

    subparsers = parser.add_subparsers(title="Commands", dest="command")
    
    daemon_parser = subparsers.add_parser('daemon', help='Run as daemon and perform actions based on configured jobs')
    job_parser = subparsers.add_parser('run', help='Run a job based on the provided paramaters')
    
    job_parser.add_argument('--type', dest='type', choices=['backup', 'replication'] , help='The type of the job to run. Available types: backup, replication')
    job_parser.add_argument('--dest', dest='dest', required=True, help='Destination storage to be used when performing the job')
    job_parser.add_argument('--replicate', dest='replicate', help='Source storage to read the data from when performing the replication job - required when the job type is replication, otherwise ignored')
    job_parser.add_argument('--limit', dest='limit', action='append', help='List of sources for the job (if no sources are provided, all sources will be included, except the ones in the exclude list)')
    job_parser.add_argument('--exclude', dest='exclude', action='append', help='List of sources to exclude from the job')
    job_parser.add_argument('--retention-policy', dest='retention_policy', help='Retention policy. last=<NR>,hourly=<NR>,daily=<daNRys>,weekly=<NR>,monthly=<NR>,yearly=<NR>. Example: --retention-policy last=6,hourly=24,daily=7,weekly=4,monthly=12,yearly=1')
    job_parser.add_argument('--notification-policy', dest='notification_policy', type=str, help='Notification policy. Available options: never, always, on-failure.')
    job_parser.add_argument('--concurrency', dest='concurrency', type=int, help='Concurrency. Number of concurrent hosts to backup')
    
    configtest_parser = subparsers.add_parser('configtest', help='Test the configuration file')
    stats_parser = subparsers.add_parser('stats', help='Show some stats')
    
    stats_parser.add_argument('--json', dest='json', action='store_true', help='Output the stats in JSON format')
    
    args = parser.parse_args()

    if args.command is None:
      parser.print_help()
      sys.exit()
      
    alt_job = None
      
    if args.command == 'run':
        alt_job = {
            'name': f'manual-{datetime.datetime.now().strftime("%Y%m%d%H%M%S")}',
            'type': args.type,
            'dest': args.dest,
            'replicate': args.replicate,
            'limit': args.limit,
            'exclude': args.exclude,
            'retention_policy': args.retention_policy,
            'notification_policy': args.notification_policy,
            'concurrency': args.concurrency,
        }
        
        alt_job = {k : v for k, v in alt_job.items() if v is not None}
    elif args.command == 'stats':
        # change default log level for stats
        if not args.log_level:
            args.log_level = 'WARNING'
    
    try:
        usbackup = UsBackupManager(log_file=args.log_file, log_level=args.log_level, config_file=args.config_file, alt_job=alt_job)
    except ValidationError as e:
        print(f"Configuration file contains {e.error_count()} error(s):")
        
        for error in e.errors(include_url=False):
            loc = '.'.join(str(x) for x in error['loc']) if error['loc'] else 'general'
            print(f"  - {loc}: {error['msg']}")
            exit()

        print(f"\nCheck documentation for more information on how to configure UsBackup")
        sys.exit(2)
    
    if args.command == 'daemon':
        usbackup.run_forever()
    elif args.command == 'run':
        usbackup.run_once()
    elif args.command == 'configtest':
        print("Configuration file is valid")
    elif args.command == 'stats':
        format = 'json' if args.json else 'text'
        print(usbackup.stats(format=format))

    sys.exit(0)