import usbackup.info as info
from setuptools import setup

with open("README.md", "r") as f:
    long_description = f.read()

with open("requirements.txt") as f:
    requirements = [line.strip() for line in f]

setup(
    name=info.__app_name__,
    version=info.__version__,
    description=info.__description__,
    long_description=long_description,
    long_description_content_type="text/markdown",
    license=info.__license__,
    author=info.__author__,
    author_email=info.__author_email__,
    author_url=info.__author_url__,
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