"""
SpeechBridge Framework Setup
=============================
"""

from setuptools import setup, find_packages
from pathlib import Path

# Читаем README
readme_file = Path(__file__).parent / "README.md"
long_description = ""
if readme_file.exists():
    long_description = readme_file.read_text(encoding='utf-8')

# Читаем requirements
requirements_file = Path(__file__).parent / "requirements.txt"
requirements = []
if requirements_file.exists():
    with open(requirements_file, 'r', encoding='utf-8') as f:
        requirements = [
            line.strip() for line in f
            if line.strip() and not line.startswith('#')
        ]

# Версия
version_file = Path(__file__).parent / "speechbridge" / "__version__.py"
version = "1.0.0"
if version_file.exists():
    exec(version_file.read_text())
    version = locals().get('__version__', '1.0.0')

setup(
    name="speechbridge",
    version=version,
    author="SpeechBridge Development Team",
    author_email="dev@speechbridge.com",
    description="Modular framework for automated video translation with GPU support",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/your-org/speechbridge",
    packages=find_packages(),
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "Topic :: Multimedia :: Video",
        "Topic :: Scientific/Engineering :: Artificial Intelligence",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
    ],
    python_requires=">=3.10",
    install_requires=requirements,
    extras_require={
        'dev': [
            'pytest>=7.4.0',
            'pytest-cov>=4.1.0',
            'black>=23.0.0',
            'flake8>=6.0.0',
            'mypy>=1.0.0',
        ],
        'tensorflow': [
            'tensorflow>=2.13.0',
        ],
    },
    entry_points={
        'console_scripts': [
            'speechbridge=speechbridge.cli.main:cli',
        ],
    },
    include_package_data=True,
    zip_safe=False,
)
