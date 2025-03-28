from setuptools import setup, find_packages

setup(
    name="video_generator",
    packages=find_packages(),
    install_requires=[
        'flask==2.0.1',
        'moviepy==1.0.3',
        'edge-tts==6.1.9',
    ]
) 