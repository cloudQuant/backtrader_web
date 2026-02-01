"""
Backtrader Web - 量化回测可视化框架
"""
from setuptools import setup, find_packages

setup(
    name="backtrader-web",
    version="0.1.0",
    description="量化回测可视化框架，支持通过Web页面展示backtrader回测结果",
    author="yunjinqi",
    packages=find_packages(),
    python_requires=">=3.8",
    install_requires=[
        "backtrader>=1.9.78.123",
        "pandas>=1.0.0",
        "numpy>=1.18.0",
        "akshare>=1.0.0",
    ],
    extras_require={
        "dev": [
            "pytest>=7.0.0",
            "pytest-cov>=4.0.0",
        ],
    },
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Intended Audience :: Developers",
        "Intended Audience :: Financial and Insurance Industry",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Topic :: Office/Business :: Financial :: Investment",
    ],
)
