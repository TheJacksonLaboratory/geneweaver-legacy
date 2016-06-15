# file: batch.py
# date: 6/10/16
# version: 1.0

import config
import psycopg2

class Batch:

	def __init__(self, input_filepath = None):
		# testing purposes
		self.test = True

		# figure out optimum input type
		# DESIGN DECISION - for now, pretend that input file is req
		self.raw_file = input_filepath

		# error handling
		self.crit = []
		self.noncrit = []

		# database connection fields
		self.connection = None
		self.cur = None
		self.gene_types = {}  # {gdb_name: gdb_id,}
		self.micro_types = {}  # {pf_name: pf_id,}
		self.platform_types = {}  # {prb_ref_id: prb_id,}
		self.species_types = {}  # {sp_name: sp_id,}

		# launch connection to GeneWeaver database
		self.launch_connection()

	#----------------- DATABASE ------------------------------------------#

	def launch_connection(self):
		""" 
		"""
		data = config.get('db', 'database')
		user = config.get('db', 'user')
		password = config.get('db', 'password')
		host = config.get('db', 'host')

		print host  # TESTING

		# set up connection information
		cs = 'host=\'%s\' dbname=\'%s\' user=\'%s\' password=\'%s\'' % (host, data, user, password)

		try:
			self.connection = psycopg2.connect(cs)	# connect to geneweaver database
			self.cur = self.connection.cursor()
		except SyntaxError:	 # cs most likely wouldn't be a useable string if wasn't able to connect
			print "Error: Unable to connect to database."
			exit()

	def commit(self):
		if self.test == True:
			return
		else:
			self.connection.commit()

	def populate_dictionaries(self):
		""" Queries GeneWeaver, populating globally stored dictionaries with 
			information we only need to query once, including:
			- Gene Types
			- MicroArray Types
			- Species Types

		"""
		# Gene Types
		self.query_geneTypes()
		# MicroArray Types
		self.query_microArrayTypes()
		# Species Types
		self.query_speciesTypes()

	def query_geneTypes(self):
		""" Queries GeneWeaver for a list of gene types, populating global var 
			'gene_types'. The name of the gene type is mapped against gene type ID. 
			All gene type names are converted to lowercase, for ease of practice.
		"""
		# QUERY: get a tuple of gene types by id + name
		query = 'SELECT gdb_id, gdb_name ' \
				'FROM odestatic.genedb;'

		# run query
		self.cur.execute(query)
		# fetch results
		results = self.cur.fetchall()

		for tup in results:
			self.gene_types[tup[1].lower()] = tup[0]

	def query_microArrayTypes(self):
		""" Queries GeneWeaver for a list of microarray platforms, populating global
			var 'micro_types'. The name of the microarray type is mapped against 
			it's respective microarray ID. All microarray types are converted to 
			lowercase, for ease of practice. 
		"""
		# QUERY: get a tuple of microarray types by id + name
		query = 'SELECT pf_id, pf_name ' \
				'FROM odestatic.platform;'
		
		# run query
		self.cur.execute(query)
		# fetch results
		results = self.cur.fetchall()

		for tup in results:
			self.micro_types[tup[1].lower()] = tup[0]

	def query_speciesTypes(self):
		""" Queries GeneWeaver for a list of species types, populating global var
			'species_types'. The name of the species is mapped against it's 
			respective species ID. All species types are converted to lowercase, 
			for ease of practice.
		"""
		# QUERY: get a list of species types by id + name
		query = 'SELECT sp_id, sp_name ' \
				'FROM odestatic.species;'

		# run query
		self.cur.execute(query)
		# fetch results
		results = self.cur.fetchall()
		
		for tup in results:
			self.species_types[tup[1].lower()] = tup[0]

	#---------------------ERROR HANDLING---------------------------------#

	def get_errors(self, critical=False, noncritical=False):
		""" Returns error messages. If no additional parameters are filled, or if both
			'crit' and 'noncrit' are set to 'True', both critical and
			noncritical error messages are returned for the user.

			Otherwise, if either 'crit' or 'noncrit' are set to 'True', only that
			respective error type will be returned.

		Parameters
		----------
		crit (optional): boolean
		noncrit (optional): boolean

		Returns
		-------
		critical (optional): list of critical error messages generated [self.crit]
		noncritical (optional): list of noncritical error messages generated [self.noncrit]
		"""
		if critical and noncritical:
			return self.crit, self.noncrit
		elif critical:
			return self.crit
		elif noncritical:
			return self.noncrit
		else:
			return self.crit, self.noncrit

	def set_errors(self, critical=None, noncritical=None):
		""" Sets error messages, printing confirmation when new errors are added. Parameters
			'crit' and 'noncrit' can take either a string, appended onto respective global
			variable, a list or a tuple. In the case that a list or tuple is provided, function
			iterates through and appends to global error messages accordingly.

		Parameters
		----------
		critical: string or list
		noncritical: string or list
		"""
		crit_count = 0
		noncrit_count = 0

		if type(critical) == (list or tuple):
			for error in critical:
				self.crit.append(error)
				crit_count += 1
		elif type(critical) == str:
			self.crit.append(critical)
			crit_count += 1

		if type(noncritical) == (list or tuple):
			for n in noncritical:
				self.noncrit.append(n)
				noncrit_count += 1
		elif type(noncritical) == str:
			self.noncrit.append(noncritical)
			noncrit_count += 1

			# USER FEEDBACK [uncomment selection]
			# if crit_count:
			#     print "Critical error messages added [%i]\n" % crit_count
			# if noncrit_count > 0:
			#     print "Noncritical error messages added [%i]\n" % noncrit_count

	#-----------------------------FILE HANDLING-----------------------------------#

	def read_file(self, fp):
		""" Reads in from a source text file and outputs organized data	 # EDIT

		# separate each column into lists (make sure the same length before proceeding)

		Parameters
		----------
		fp: filepath to read (string)
		"""
		print "will handle file parsing someday..."

	def groom_raw_data(self):
		print "will assign raw data to objects someday..."

	def database_setup(self):
		print "will upload to GeneWeaver someday..."

class UploadGeneSet:

	def __init__(self, batch, prelim_info):
		print "will initialize GeneSet object someday, using preliminary info from the input file..."

	def geneweaver_setup(self):
		print "will identify the preliminary features of the GeneWeaver query, + populate globals..."

	def upload(self):
		print "will initiate data query..."  # EDIT - needed?

	def get_platformProbeTypes(self, pfid, refs):
		""" 
		"""
		pass

	def getProbe2Gene(self, prbids):
		"""
		"""
		pass

	def add_gene(self):
		print "will generate new UploadGene obj..."

	def create_file(self):
		print "will create user's UploadGeneSet..."

	def create_publicaton(self):
		print "will generate new publication, if not already in GeneWeaver... "
		# EDIT: may have absolutely no functionality at all - refer to input file layout

	def commit(self):
		print "will determine whether or not to actually make changes, or to just" \
			  " leave it in a 'test mode' state..."

class UploadGene:

	def __init__(self, geneset):
		print "will initialize Gene obj someday, using information inherited from GeneSet..."

	#-----------------mutators go here-----------------------#

	def insert_gene(self):
		print 'will insert user-specified gene into GeneSet someday...'

	def insert_gene_info(self):
		print 'will insert gene info, if gene is not already in GeneWeaver...'

	def insert_value(self):
		print 'will insert Gene value into GeneWeaver, if all information is provided...'

	def search_geneweaver(self):
		print "queries GeneWeaver for a series of possible cases, depending on what's available..."

	# -----------------series of cross-checking functions go here-----------------#

# class UploadSNP - only if relevant, if tables are up to speed

def test_dictionaries():
	b = Batch()	
	b.populate_dictionaries()

if __name__ == '__main__':
	test_dictionaries()

