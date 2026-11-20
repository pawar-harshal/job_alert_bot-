"""
setup.py declares the external PyPI packages job_alert_bot depends on.
It does NOT wrap any custom config/logging package -- we use Python's own
configparser and logging modules directly (see utils/ConfigReader.py and
utils/Logger.py). Same shape as TicketPilot's setup.py.
"""
from setuptools import find_packages, setup

setup(
    name="job_alert_bot",
    version="1.0.0",
    description="Finds relevant job openings and pushes them to Telegram as a single digest per run.",
    author="Harshal Pawar",
    packages=find_packages(),
    include_package_data=True,
    install_requires=[
        "python-jobspy",
        "requests>=2.31,<3.0",
        "openai>=1.0,<2.0",
        "retrying>=1.3,<2.0",
    ],
    python_requires=">=3.10",
)
