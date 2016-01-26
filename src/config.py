import ConfigParser
import os

## Just as a reminder: the configuration file (geneweaver.cfg) should NEVER be
## included in version control, especially if it has any usernames, passwords,
## or API keys.

CONFIG_PATH = './geneweaver.cfg'
## Global config object, sholudn't be accessed directly but using the helper
## functions found below.
CONFIG = ConfigParser.RawConfigParser(allow_no_value=True)

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
		print >> fl, 'host = '
		print >> fl, 'results = '
		print >> fl, 'secret = ' + os.urandom(32).encode('hex')
		print >> fl, ''
		print >> fl, '[celery]'
		print >> fl, 'url = '
		print >> fl, 'backend = '
		print >> fl, ''
		print >> fl, '[db]'
		print >> fl, 'database = '
		print >> fl, 'user = '
		print >> fl, 'password = '
		print >> fl, 'host = '
		print >> fl, 'port = '
		print >> fl, ''
		print >> fl, '[sphinx]'
		print >> fl, 'host = '
		print >> fl, 'port = '
		print >> fl, ''

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

def get(section, option):
	"""
	Returns the value of a section, key pair from the global config object.

	:ret: some config value
	"""

	return CONFIG.get(section, option)

if __name__ == '__main__':
	loadConfig()

