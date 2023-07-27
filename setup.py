
from setuptools import setup
from usbackup.info import APP_NAME, APP_VERSION, APP_DESCRIPTION

with open("README.md", "r") as f:
    long_description = f.read()

with open("requirements.txt") as f:
    requirements = [line.strip() for line in f]

setup(
    name=APP_NAME,
    version=APP_VERSION,
    description=APP_DESCRIPTION,
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