from setuptools import setup

setup(
    name='mediczuwacz',
    version='0.6',
    py_modules=['mediczuwacz'],
    include_package_data=True,
    install_requires=[
        'fake-useragent',
        'click',
        'requests',
        'beautifulsoup4',
        'python-pushover',
        'notifiers',
        'xmpppy',
        'python-dotenv',
        'appdirs',
        'xmpppy',
        'lxml'
    ],
    entry_points='''
        [console_scripts]
        mediczuwacz=mediczuwacz:mediczuwacz
    ''',
)
