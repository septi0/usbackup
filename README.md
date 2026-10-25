# UsBackup

## Description

**UsBackup** is a backup software that allows files, datasets, vms, configs to be backed up in pull mode (via ssh). It is designed to run as a background process and to be as simple as possible.

It features a simple configuration file that allows you to configure different sources, storages and jobs. It also features a simple reporting system that can send reports via various handlers after the backup is finished.

Replication is also supported, allowing you to replicate existing backups to other locations. This is useful for offsite backups or as a part of the 3-2-1 backup strategy.

Files can be backed up from local storage or from remote storage, also they can be backed up using incremental, full or archive mode. (The first one being the most efficient in terms of space and time)

The recommended way to configure hosts is to use ssh keys. Passwords are supported but not recommended as they will be stored as plain text in the configuration file.

**WARNING!** If using UsBackup prior to version 2.0, please note that the configuration file format and backup directories structure have changed and they are not compatible with versions 1.x and 0.x. Please check the `config.sample.yml` file for the new format and migrate your configuration file accordingly.
Version 1.x is still available in the `legacy` branch.

**Upgrading to 2.7.** Stop the running service before upgrading and start it again afterwards. Behavior changes to check:

- Cron schedules follow standard cron semantics: weekdays count from Sunday (`0` or `7`), so schedules using the weekday field now run one day earlier than before (on the intended day). Lists (`0,30`) are supported, steps on days and months start at 1, and a job restricted by both day of month and day of week runs when either matches. Invalid values (e.g. minute `75` or step `*/0`) are rejected by `configtest`.
- `usbackup run` and `usbackup daemon` exit with a non zero code on failure (see "Command line arguments").
- An empty retention policy (`retention_policy: {}`) is a configuration error instead of pruning all versions except the latest one.
- Replication only copies the latest successfully completed version of each source (the one the `latest` symlink points to). Storages created by versions without the `latest` symlink need one successful backup before they can be replicated.
- Remote storages are only allowed as replication destinations, which `configtest` enforces.
- Jobs must reference existing storages (`dest`, `replicate`) and sources (`limit`, `exclude`), otherwise `configtest` reports the typo instead of the job failing or silently skipping it.
- New runtime files: `data.db.lock` and a `cleanup` directory next to the datastore (whose directory is now private), and SSH control sockets in `/run/usbackup/ssh` (for root).

## Features

- Backup files (incremental, full, archive)
- Backup FTP/FTPS sources (incremental, full)
- Backup OpenWRT config
- Backup Truenas config
- Backup ZFS datasets
- Backup Home Assistant config
- Backup Proxmox VMs
- Remote or local sources
- Replication to local or remote hosts
- Source configuration
- Storage configuration
- Job configuration
- Notification configuration
- Pre / post backup commands

## Software requirements

- python3
- rsync
- tar
- ssh
- sshpass (if using passwords for remote hosts - not recommended)

## Installation

#### 1. As a package

```
pip install --upgrade <git-repo>
```

or 

```
git clone <git-repo>
cd <git-repo>
pip install .
```

#### 2. As a standalone script

```
git clone <git-repo>
```

## Usage

UsBackup can be used in 3 ways:

#### 1. As a package (if installed globally)

```
/usr/bin/usbackup <parameters>
```

#### 2. As a package (if installed in a virtualenv)

```
<path-to-venv>/bin/usbackup <parameters>
```

#### 3. As a standalone script

```
<git-clone-dir>/run.py <parameters>
```

Check "Command line arguments" section for more information about the available parameters.

## Command line arguments

```
usbackup [-h] [--config CONFIG_FILE] [--log LOG_FILE] [--log-level {DEBUG,INFO,WARNING,ERROR,CRITICAL}] [--version] {daemon,run,configtest,stats} ...

options:
  -h, --help            show this help message and exit
  --config CONFIG_FILE  Alternative config file
  --log LOG_FILE        Log file where to write logs
  --log-level {DEBUG,INFO,WARNING,ERROR,CRITICAL}
                        Log level
  --version             show program's version number and exit

Commands:
  {daemon,run,configtest,stats}
    daemon              Run as daemon and perform actions based on configured jobs
    
    run                 Run a job based on the provided paramaters
      options:
        --type {backup,replication}
                              The type of the job to run. Available types: backup, replication. Default: backup
        --dest DEST           Destination storage to be used when performing the job
        --replicate REPLICATE
                              Source storage to read the data from when performing the replication job - required when the job type is replication, otherwise ignored
        --replication-mode {incremental,full,archive}
                              Replication mode. Available options: incremental, full, archive. Default: incremental
        --limit LIMIT         List of sources for the job (if no sources are provided, all sources will be included, except the ones in the exclude list)
        --exclude EXCLUDE     List of sources to exclude from the job
        --retention-policy RETENTION_POLICY
                              Retention policy. last=<NR>,hourly=<NR>,daily=<NR>,weekly=<NR>,monthly=<NR>,yearly=<NR>. Example: --retention-policy last=6,hourly=24,daily=7,weekly=4,monthly=12,yearly=1
        --source-retention-policy SOURCES_RETENTION_POLICY
                              Retention policy for a specific source, replacing the job retention policy for that source. Can be used multiple times. <source>:last=<NR>,hourly=<NR>,daily=<NR>,weekly=<NR>,monthly=<NR>,yearly=<NR>. Example: --source-retention-policy host1:daily=30,monthly=12
        --notification-policy NOTIFICATION_POLICY
                              Notification policy. Available options: never, always, on-failure. Default: always
        --concurrency CONCURRENCY
                              Concurrency. Number of concurrent hosts to backup. Default: 1

    configtest          Test the configuration file

    stats               Show some stats
      options:
        --json          Output the stats in JSON format
```

Exit codes: `0` on success, `1` if a run or the service failed (including any failed source or an interrupted run), `2` for invalid arguments, an invalid configuration or other startup errors.

## Examples

#### Run a manual backup job

Backup all sources to `storage1`. No retention policy is applied - all versions are kept indefinitely:

```
usbackup run --dest storage1
```

---

Backup only specific sources:

```
usbackup run --dest storage1 --limit host1 --limit host2
```

---

Backup all sources except one:

```
usbackup run --dest storage1 --exclude host3
```

---

Backup with a custom retention policy (keep last 5, 7 daily, 4 weekly):

```
usbackup run --dest storage1 --retention-policy last=5,daily=7,weekly=4
```

---

Backup with a custom retention policy for all sources, except `host1` and `host2` which use their own policies:

```
usbackup run --dest storage1 --retention-policy last=5,daily=7 --source-retention-policy host1:daily=30,monthly=12,yearly=2 --source-retention-policy host2:last=3
```

> **Note:** A source retention policy fully replaces the job retention policy for that source (the policies are not merged). It can also be used without a job retention policy, in which case only the given sources are pruned.

---

#### Run a manual replication job

Replicate the latest backup from `storage1` to `storage2` using incremental mode (default):

```
usbackup run --type replication --replicate storage1 --dest storage2
```

---

Replicate using archive mode (packages the latest backup version into an `archive.tar.gz` per version):

```
usbackup run --type replication --replicate storage1 --dest storage2 --replication-mode archive
```

---

Replicate only specific sources with a retention policy:

```
usbackup run --type replication --replicate storage1 --dest storage2 --limit host1 --retention-policy last=3,daily=7
```

> **Note:** The destination storage for replication jobs can be a remote Linux host over SSH. Configure it with a host in the `storages` section of the config file (e.g. `path: ssh://user@backup-host:22/path/to/storage`). The remote host needs `rsync` (incremental and full modes), `sh` and the standard coreutils, and key based SSH authentication is recommended. Remote storages can only be used as replication destinations: backup jobs and replication sources must use local storages. Only the latest successfully completed version of each source is replicated.

> **Note:** SSH connections to remote storages are reused while a source is being replicated, through control sockets kept in a private runtime directory (`/run/usbackup/ssh` for root). If that directory cannot be made private, connections are not reused and a warning is logged.
## Configuration file

For a sample configuration file see `config.sample.yml` file. Aditionally, you can copy the file to `/etc/usbackup/config.yml`, `/etc/opt/usbackup/config.yml` or `~/.config/usbackup/config.yml` (or where you want as long as you provide the `--config` parameter) and adjust the values to your needs.

A `secrets.env` file can also be created in the same directory as the config file to store sensitive information such as passwords and API keys. This file should be in the format of key=value pairs, one per line and referenced in the config file using the `${VAR_NAME}` syntax.

For details on how to configure the file, see the `config.sample.yml` file.

The main sections of the configuration file are:

- `sources` Sources are the representation of each host that needs to be backed up and contains the instructions of what to back up on that host.
- `storages` Storages are the representation of the different backup destinations.
- `jobs` Jobs are the glue that binds sources and storages together and defines when to run the backup and how many backups to keep. The `retention_policy` applies to all sources of the job, while `sources_retention_policy` can replace it for specific sources.
- `notifiers` Notifiers are the different methods of sending notifications after the backup is finished.

Valid format for hosts:

```
<user>:<password>@<host>:<port>
```

With all the fields except `host` being optional.
If no user is specified, the `root` user will be used. If no port is specified, the default port will be used for that service. If no password is specified, it will try to use ssh keys (recomended way).

**Note!** Using passwords is not recommended as they will be stored as plain text in the configuration file, instead use ssh keys for file transfers / configs.

## Systemd service

To run UsBackup as a service, have it start on boot and restart on failure, create a systemd service file in `/etc/systemd/system/usbackup.service` and copy the content from `usbackup.sample.service` file, adjusting the `ExecStart` parameter based on the installation method.

After that, run the following commands:

```
systemctl daemon-reload
systemctl enable usbackup.service
systemctl start usbackup.service
```

## Disclaimer

This software is provided as is, without any warranty. Use at your own risk. The author is not responsible for any damage caused by this software.

## License

This software is licensed under the GNU GPL v3 license. See the LICENSE file for more information.