from setuptools import setup, find_packages

setup(
    name="industrial-brain-shared",
    version="0.1.0",
    packages=find_packages(),
    install_requires=[
        "pydantic>=2.0.0",
    ],
    python_requires=">=3.9",
)
