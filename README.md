# UsBackup

## Description

**UsBackup** is a backup software that allows files, datasets, vms, configs to be backed up in pull mode (via ssh). It is designed to run as a background process and to be as simple as possible.

It features a simple configuration file that allows you to configure different sources, storages and jobs. It also features a simple reporting system that can send reports via various handlers after the backup is finished.

Replication is also supported, allowing you to replicate existing backups to other locations. This is useful for offsite backups or as a part of the 3-2-1 backup strategy.

Files can be backed up from local storage or from remote storage, also they can be backed up using incremental, full or archive mode. (The first one being the most efficient in terms of space and time)

The recommended way to configure hosts is to use ssh keys. Passwords are supported but not recommended as they will be stored as plain text in the configuration file.

**WARNING!** If using UsBackup prior to version 2.0, please note that the configuration file format and backup directories structure have changed and they are not compatible with versions 1.x and 0.x. Please check the `config.sample.yml` file for the new format and migrate your configuration file accordingly.
Version 1.x is still available in the `legacy` branch.

## Features

- Backup files (incremental, full, archive)
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
python setup.py install
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
usbackup [-h] [--config CONFIG_FILES] [--log LOG_FILE] [--log-level {DEBUG,INFO,WARNING,ERROR,CRITICAL}] [--version] {configtest,du,backup} ...

options:
  -h, --help            show this help message and exit
  --config CONFIG_FILES
                        Alternative config file(s)
  --log LOG_FILE        Log file where to write logs
  --log-level {DEBUG,INFO,WARNING,ERROR,CRITICAL}
                        Log level
  --version             show program's version number and exit

Commands:
  {configtest,du,backup}
    configtest          Test configuration file

    daemon              Run as daemon and perform actions based on configured jobs
    
    run                 Run a job based on the provided paramaters
      options:
        --type {backup,replication}
                              The type of the job to run. Available types: backup, replication. Default: backup
        --dest DEST           Destination storage to be used when performing the job
        --replicate REPLICATE
                              Source storage to read the data from when performing the replication job - required when the job type is replication, otherwise ignored
        --limit LIMIT         List of sources for the job (if no sources are provided, all sources will be included, except the ones in the exclude list)
        --exclude EXCLUDE     List of sources to exclude from the job
        --retention-policy RETENTION_POLICY
                              Retention policy. last=<NR>,hourly=<NR>,daily=<daNRys>,weekly=<NR>,monthly=<NR>,yearly=<NR>. Example: --retention-policy last=6,hourly=24,daily=7,weekly=4,monthly=12,yearly=1
        --notification-policy NOTIFICATION_POLICY
                              Notification policy. Available options: never, always, on-failure. Default: always
        --concurrency CONCURRENCY
                              Concurrency. Number of concurrent hosts to backup. Default: 1
```

## Configuration file

For a sample configuration file see `config.sample.yml` file. Aditionally, you can copy the file to `/etc/usbackup/config.yml`, `/etc/opt/usbackup/config.yml` or `~/.config/usbackup/config.yml` (or where you want as long as you provide the `--config` parameter) and adjust the values to your needs.

For details on how to configure the file, see the `config.sample.yml` file.

The main sections of the configuration file are:

- `sources` Sources are the representation of each host that needs to be backed up and contains the instructions of what to back up.
- `storages` Storages are the representation of backup destinations.
- `jobs` Jobs are the glue that binds sources and storages together and defines when to run the backup and how many backups to keep.
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