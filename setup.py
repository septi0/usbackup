
from setuptools import setup

with open("README.md", "r") as f:
    long_description = f.read()

with open("requirements.txt") as f:
    requirements = [line.strip() for line in f]

setup(
    name="UsBackup",
    version="0.1.8",
    description='A linux backup tool featuring snapshots, retention policies, backup handlers and report handlers',
    long_description=long_description,
    long_description_content_type="text/markdown",
    license="GPLv3",
    author='Septimiu Ujica',
    author_email='me@septi.ro',
    author_url='https://www.septi.ro',
    python_requires='>=3.10',
    install_requires=requirements,
    packages=[
        'usbackup',
        'usbackup.backup_handlers',
        'usbackup.report_handlers',
    ],
    classifiers=[
        "Programming Language :: Python :: 3",
        "Operating System :: POSIX :: Linux",
        "License :: OSI Approved :: GNU General Public License v3 (GPLv3)",
        "Topic :: System :: Archiving :: Backup",
        "Topic :: System :: Archiving :: Mirroring",
        "Topic :: Utilities",
    ],
    entry_points={
        'console_scripts': [
            'usbackup = usbackup:main',
        ],
    },
)