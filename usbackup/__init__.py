import sys
import argparse
import datetime
from pydantic import ValidationError
from usbackup.manager import UsBackupManager
from usbackup.exceptions import UsBackupRuntimeError
from usbackup.info import __app_name__, __version__, __description__, __author__, __author_email__, __author_url__, __license__

def parse_retention_policy(value: str) -> dict[str, int]:
    policy = {}
    
    for item in value.split(','):
        category, separator, number = item.partition('=')
        category = category.strip()
        
        if not separator or not category:
            raise argparse.ArgumentTypeError(f'invalid retention policy item "{item}". Expected <category>=<NR>')
        
        if category in policy:
            raise argparse.ArgumentTypeError(f'duplicate retention policy category "{category}"')
        
        try:
            policy[category] = int(number)
        except ValueError:
            raise argparse.ArgumentTypeError(f'invalid number "{number}" for retention policy category "{category}"')
    
    return policy

def parse_source_retention_policy(value: str) -> tuple[str, dict[str, int]]:
    # split on the last colon since source names may contain colons
    source, separator, policy = value.rpartition(':')
    
    if not separator or not source:
        raise argparse.ArgumentTypeError(f'invalid source retention policy "{value}". Expected <source>:<category>=<NR>,...')
    
    return source, parse_retention_policy(policy)

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
    
    job_parser.add_argument('--job', dest='job', help='Name of a configured job to run, as configured. Can only be combined with --limit and --exclude, to run some of its sources')
    job_parser.add_argument('--type', dest='type', choices=['backup', 'replication'] , help='The type of the job to run. Available types: backup, replication')
    job_parser.add_argument('--dest', dest='dest', help='Destination storage to be used when performing the job - required unless --job is used')
    job_parser.add_argument('--replicate', dest='replicate', help='Source storage to read the data from when performing the replication job - required when the job type is replication, otherwise ignored')
    job_parser.add_argument('--replication-mode', dest='replication_mode', choices=['incremental', 'full', 'archive'], help='Replication mode. Available options: incremental, full, archive. Default: incremental')
    job_parser.add_argument('--limit', dest='limit', action='append', help='List of sources for the job (if no sources are provided, all sources will be included, except the ones in the exclude list)')
    job_parser.add_argument('--exclude', dest='exclude', action='append', help='List of sources to exclude from the job')
    job_parser.add_argument('--retention-policy', dest='retention_policy', type=parse_retention_policy, help='Retention policy. last=<NR>,hourly=<NR>,daily=<NR>,weekly=<NR>,monthly=<NR>,yearly=<NR>. Example: --retention-policy last=6,hourly=24,daily=7,weekly=4,monthly=12,yearly=1')
    job_parser.add_argument('--source-retention-policy', dest='sources_retention_policy', type=parse_source_retention_policy, action='append', help='Retention policy for a specific source, replacing the job retention policy for that source. Can be used multiple times. <source>:last=<NR>,hourly=<NR>,daily=<NR>,weekly=<NR>,monthly=<NR>,yearly=<NR>. Example: --source-retention-policy host1:daily=30,monthly=12')
    job_parser.add_argument('--notification-policy', dest='notification_policy', type=str, help='Notification policy. Available options: never, always, on-failure.')
    job_parser.add_argument('--concurrency', dest='concurrency', type=int, help='Concurrency. Number of concurrent hosts to backup')
    
    prune_parser = subparsers.add_parser('prune', help='Apply the retention policies of a configured job, without running it')
    
    prune_parser.add_argument('--job', dest='job', required=True, help='Name of the configured job whose retention policies are applied')
    prune_parser.add_argument('--limit', dest='limit', action='append', help='Sources of the job to prune (if no sources are provided, all sources of the job will be pruned, except the ones in the exclude list)')
    prune_parser.add_argument('--exclude', dest='exclude', action='append', help='Sources of the job to skip')
    prune_parser.add_argument('--dry-run', dest='dry_run', action='store_true', help='Only show which versions would be removed, without removing them')
    
    configtest_parser = subparsers.add_parser('configtest', help='Test the configuration file')
    stats_parser = subparsers.add_parser('stats', help='Show some stats')
    
    stats_parser.add_argument('--json', dest='json', action='store_true', help='Output the stats in JSON format')
    
    args = parser.parse_args()

    if args.command is None:
      parser.print_help()
      sys.exit()
      
    alt_job = None
      
    if args.command == 'run' and args.job:
        # a configured job runs as configured, it can only be narrowed to some of its sources
        job_options = {'type': '--type', 'dest': '--dest', 'replicate': '--replicate', 'replication_mode': '--replication-mode', 'retention_policy': '--retention-policy', 'sources_retention_policy': '--source-retention-policy', 'notification_policy': '--notification-policy', 'concurrency': '--concurrency'}
        used_options = [option for name, option in job_options.items() if getattr(args, name) is not None]
        
        if used_options:
            job_parser.error(f'argument --job: not allowed with {", ".join(used_options)}')
    elif args.command == 'run':
        if not args.dest:
            job_parser.error('the following arguments are required: --dest (unless --job is used)')
        
        sources_retention_policy = None
        
        if args.sources_retention_policy:
            sources_retention_policy = {}
            
            for source, policy in args.sources_retention_policy:
                if source in sources_retention_policy:
                    job_parser.error(f'argument --source-retention-policy: duplicate source "{source}"')
                
                sources_retention_policy[source] = policy
        
        alt_job = {
            'name': f'manual-{datetime.datetime.now().strftime("%Y%m%d%H%M%S")}',
            'type': args.type,
            'dest': args.dest,
            'replicate': args.replicate,
            'replication_mode': args.replication_mode,
            'limit': args.limit,
            'exclude': args.exclude,
            'retention_policy': args.retention_policy,
            'sources_retention_policy': sources_retention_policy,
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

        print(f"\nCheck documentation for more information on how to configure UsBackup")
        sys.exit(2)
    except (UsBackupRuntimeError, OSError) as e:
        # startup errors like a missing or unreadable config file are reported without a traceback
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(2)
    
    try:
        if args.command == 'daemon':
            # a failed service exits with a non zero code so the service manager can restart it
            if not usbackup.run_forever():
                sys.exit(1)
        elif args.command == 'run':
            # failed or interrupted runs exit with a non zero code so schedulers and monitoring can detect them
            if not usbackup.run_once(args.job, limit=args.limit if args.job else None, exclude=args.exclude if args.job else None):
                sys.exit(1)
        elif args.command == 'prune':
            if not usbackup.prune(args.job, limit=args.limit, exclude=args.exclude, dry_run=args.dry_run):
                sys.exit(1)
        elif args.command == 'configtest':
            print("Configuration file is valid")
        elif args.command == 'stats':
            format = 'json' if args.json else 'text'
            stats = usbackup.stats(format=format)
            
            if not isinstance(stats, str):
                sys.exit(1)
            
            print(stats)
    except UsBackupRuntimeError as e:
        # inexistent jobs or sources given on the command line are reported like startup errors
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(2)

    sys.exit(0)