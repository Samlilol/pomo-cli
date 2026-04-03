from setuptools import find_packages, setup


setup(
    name="pomo-cli",
    version="0.1.0",
    description="Local pomodoro CLI for agent-assisted workflows",
    package_dir={"": "src"},
    packages=find_packages(where="src"),
    entry_points={
        "console_scripts": [
            "pomo=pomo_cli.cli:main",
        ]
    },
)
