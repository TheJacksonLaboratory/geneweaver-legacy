import ConfigParser
import os

## Just as a reminder: the configuration file (geneweaver.cfg) should NEVER be
## included in version control, especially if it has any usernames, passwords,
## or API keys.
rootpath="/srv/www/geneweaver/"
CONFIG_PATH = rootpath+'geneweaver.cfg'

## Global config object, sholudn't be accessed directly but using the helper
## functions found below.
CONFIG = None


def createConfig():
    """
    Generates a new configuration file in the current directory. The config
    file uses the common INI style which can be parsed with python's
    ConfigParser module.

    :ret:
    """

    with open(CONFIG_PATH, 'w') as fl:
        print >> fl, '## GeneWeaver Configuration File'
        print >> fl, '#'
        print >> fl, ''
        print >> fl, '[application]'
        print >> fl, 'host = 127.0.0.1'
        print >> fl, 'results = '+rootpath+'website-py/results'
        print >> fl, 'secret = ' + os.urandom(32).encode('hex')
        print >> fl, ''
        print >> fl, '[celery]'
        print >> fl, 'url = amqp://guest@localhost//'
        print >> fl, 'backend = amqp'
        print >> fl, ''
        print >> fl, '[db]'
        print >> fl, 'database = dbname'
        print >> fl, 'user = user'
        print >> fl, 'password = somepassword'
        print >> fl, 'host = 127.0.0.1'
        print >> fl, 'port = 5432'
        print >> fl, ''
        print >> fl, '[sphinx]'
        print >> fl, 'host = 127.0.0.1'
        print >> fl, 'port = 9312'
        print >> fl, ''

def checkIntegrity():
    """
    Checks to make sure all the key-value pairs have values and fills in any
    missing spots so the app won't crash later.
    """

    sections = ['application', 'celery', 'db', 'sphinx']

    for sec in sections:
        for key, val in CONFIG.items(sec):
            if not val:
                val = '0'

                CONFIG.set(sec, key, val)

def loadConfig():
    """
    Attempts to load and parse a config file.
    """

    if not os.path.exists(CONFIG_PATH):
        createConfig()

        raise IOError(('Could not find a config file, so we made '
                       'one for you. Please fill it out.'))

    ## Assumes the config file info is correct. The app will throw exceptions
    ## later anyway if any of the parameters are wrong.
    CONFIG.read(CONFIG_PATH)

    checkIntegrity()

def get(section, option):
    """
    Returns the value of a section, key pair from the global config object.

    :ret str: some config value
    """

    return CONFIG.get(section, option)


def getInt(section, option):
    """
    Returns the value of a section, key pair from the global config object as
    an int.

    :ret str: some config value
    """

    return CONFIG.getint(section, option)

## This config module should be included prior to any others since other parts
## of the app may need to access its variables. The config will attempt to load
## and parse everything as soon as it's imported.
if not CONFIG:
    CONFIG = ConfigParser.RawConfigParser(allow_no_value=True)
    loadConfig()

if __name__ == '__main__':
    loadConfig()
