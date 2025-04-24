# UsBackup

## Description

**UsBackup** is a backup software that allows files, databases, openwrt configs to be backed up. It is designed to run as a background process and to be as simple as possible.

It features a simple configuration file that allows you to configure different snapshots, snapshot levels, the backup sources and the backup destinations. It also features a simple reporting system that can send email or slack reports after the backup is finished either globally or for each snapshot.

Files can be backed up from local storage or from remote storage, also they can be backed up using incremental, full or archive mode. (The first one being the most efficient in terms of space and time)

## Features

- Backup files
- Backup databases (mysql)
- Backup OpenWRT config
- Backup Truenas config
- Backup ZFS datasets
- Backup Home Assistant config
- Backup Proxmox VMs
- Backup from local host
- Backup from remote host
- Backup to local host
- Independent snapshot configuration
- Independent snapshot level configuration
- Full backup
- Incremental backup
- Archive backup
- Email reporting
- Slack reporting
- Pre / post backup commands
- Snapshots disk usage

## Software requirements

- python3
- rsync
- mysqldump
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
    configtest          Test configuration file (based on provided snapshots)
    du                  Show disk usage of snapshots
    stats               Show statistics of snapshots
    backup              Backup snapshots
      options:
        -h, --help            show this help message and exit
        --service             Run as service. Wake up every minute to check if there are any backups to be performed
```

## Configuration file

For a sample configuration file see `config.sample.conf` file. Aditionally, you can copy the file to `/etc/usbackup/config.conf`, `/etc/opt/usbackup/config.conf` or `~/.config/usbackup/config.conf` (or where you want as long as you provide the `--config` parameter) and adjust the values to your needs.

Each section in the configuration file is a **snapshot**. These sections are independent of each other and each needs to be configured separately. A snapshot represents a collection of backup actions (files, mysql, truenas, etc) that apply to a given remote host (or local). The only exception is the `[GLOBALS]` section which is used to configure global settings that will be used by all the snapshots.

Section properties:
- `report.email` - email address to be used when sending the email report. Leave empty to disable email reporting
- `report.email.from` - email from address to be used in the email report
- `report.email.command` - command to be used when sending the email report. Default: sendmail -t
- `report.slack` - slack channel to be used when sending the slack report. Leave empty to disable slack reporting
- `report.slack.token` - slack token to be used when sending the slack report
- `src-host` - source remote host to be used when performing the backup
- `dest=/tmp/backup` - destination path to be used when performing the backup
- `levels` - backup levels to be used when performing the backup
 Allowed format (1 per line): <level_name> <replicas> <trigger_type> <options>
  - `level_name` - name of the backup level. Must respect the following format: a-zA-Z0-9_-
  - `replicas` - number of replicas to be kept. Must be a number
  - `trigger_type` - what type of even will trigger the level backup. Must be one of: schedule, age, on_demand
  - `options` - options for the trigger type.
    - `schedule` - any cron expression. Example: 0 0 * * * (every day at midnight)
    - `age` - number followed by m, h, d (minutes, hours, days). Example: 1d
    - `on_demand` - no options
- `backup.files` - folders to be backed up
- `backup.files.exclude` - files to be excluded from the backup
- `backup.files.bwlimit` - bandwidth limit to be used when performing the backup
- `backup.files.remote` - remote address to be used when performing the backup for the source files
- `backup.files.mode` - backup mode to be used when performing the files backup. Must be one of: incremental, full, archive
**Note!** Archive mode is only available for local backups for now (backup_files.remote is incompatible with backup_files.mode=archive)
- `backup.mysql` - specify mysql hosts to be backed up
- `backup.mysql.credentials-file` - mysql credentials to be used when performing the backup
- `backup.openwrt-config` - backup openwrt on the specified host (1/0)
- `backup.truenas-config` - backup truenas on the specified host (1/0)
- `backup.zfs-datasets` - list of zfs datasets to be backed up
- `pre_backup_cmd` - command to be executed before the backup is started
- `post_backup_cmd` - command to be executed after the backup is finished (regardless of the result)

Valid format for remote hosts:

```
<user>:<password>@<host>:<port>
```

With all the fields except `host` being optional.
If no user is specified, the `root` user will be used. If no port is specified, the default port will be used for that service. If no password is specified, it will try to use ssh keys (recomended way).

**Note!** Using passwords is not recommended as they will be stored as plain text in the configuration file, instead use ssh keys for file transfers / openwrt backups and credentials files for mysql backups.

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