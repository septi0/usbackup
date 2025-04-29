# UsBackup

## Description

**UsBackup** is a backup software that allows files and configs to be backed up in pull mode (via ssh). It is designed to run as a background process and to be as simple as possible.

It features a simple configuration file that allows you to configure different snapshots, snapshot levels, the backup sources and the backup destinations. It also features a simple reporting system that can send email or slack reports after the backup is finished either globally or for each snapshot.

Files can be backed up from local storage or from remote storage, also they can be backed up using incremental, full or archive mode. (The first one being the most efficient in terms of space and time)

## Features

- Backup files
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

For a sample configuration file see `config.sample.yml` file. Aditionally, you can copy the file to `/etc/usbackup/config.yml`, `/etc/opt/usbackup/config.yml` or `~/.config/usbackup/config.yml` (or where you want as long as you provide the `--config` parameter) and adjust the values to your needs.

For details on how to configure the file, see the `config.sample.yml` file.

Valid format for remote hosts:

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