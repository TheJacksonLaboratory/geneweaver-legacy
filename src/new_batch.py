# file: batch.py
# date: 6/10/16
# version: 1.0

import config
import psycopg2
import requests
import json
import sys
import progressbar
import time
import collections
import random


# allow unique user input? keep it private always?

class Batch:
	def __init__(self, input_filepath=None, usr_id=0):
		# testing purposes
		self.test = True
		self.user_id = usr_id
		self.cur_id = '1'  # uploaded as a public resource

		# EDIT: figure out optimum input type
		# EDIT: DESIGN DECISION - for now, pretend that input file is req
		self.input_file = input_filepath
		self.file_toString = None  # concatentated version of string input

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
		self.populate_dictionaries()

		# GeneSet obj fields
		self.genesets = {}  # {gs_abbrev: UploadGeneSet,}
		self.gs_gene_id_type = ''  # gs_gene_id_type (in case label changes)
		self.pubmed = ''  # PubMed ID
		self.privacy = ''  # group (public or private)
		self.score_type = ''  # gs_threshold_type
		self.threshold = ''  # gs_threshold
		self.species = ''  # sp_id
		self.publication = {'pub_id': None, 'pub_pubmed': None, 'pub_pages': None,
		                    'pub_title': None, 'pub_journal': None, 'pub_volume': None,
		                    'pub_authors': None, 'pub_abstract': None}  # {pub_*: val,}
		self.microarray = None

		self.run_batch()  # initates upload processing

	# -------------------------SESSION DATA---------------------------------------#

	def run_batch(self):
		print "initiating upload to GeneWeaver..."
		# read in the input file
		self.read_file(self.input_file)  # creates UploadGeneSet objs

		# create a new session, depending on handling approach
		if self.microarray:
			self.handle_platform()
			self.insert_publication()
			for gs_name, gs in self.genesets.iteritems():
				# TESTING PURPOSES:
				print
				print gs_name
				print 'of length:', len(gs.geneset_values)
				print
				gs.upload()
		else:
			self.handle_symbols()
			self.insert_publication()
			for gs_name, gs in self.genesets.iteritems():
				gs.upload()

		# TEST check to make sure that the changes are kept

	def handle_platform(self):
		""" Handles microarray condition.
		"""
		print 'handling platform assignment...'
		# for each geneset
		for gs_abbrev, geneset in self.genesets.iteritems():
			# look up prb_ids for each prb_ref_id
			query_probes = self.query_platformProbes(geneset.gs_gene_id_type,
			                                         geneset.geneset_values.keys())
			# print '\nquery_platformProbes:\n', query_probes

			# isolate probes, refs
			probes = []  # prb_ids
			probe_headers = query_probes.keys()  # prb_ref_ids
			for ref_probe, ids_probe in query_probes.iteritems():
				probes += ids_probe

			# look up ode_gene_ids for each prb_id
			query_odes = self.query_probe2gene(probes)
			# print '\nquery_probe2gene:\n', query_odes

			prb_results = {}  # (prb_ref_id: prb_id,}
			ode_results = {}  # (prb_ref_id: ode_gene_id,}

			# first, give priority to prb_ref_ids with only one prb_id
			for probe_ref, probe_ids in query_probes.iteritems():
				prb_results[probe_ref] = None
				size_poss = len(probe_ids)

				if size_poss != 1:
					continue  # prioritize potentially tricky items first
				elif probe_ids[0] not in prb_results.values():
					# print 'appended solo prb_id'
					prb_results[probe_ref] = probe_ids[0]
					probe_headers.remove(probe_ref)

			# second, process the remainder
			for header in probe_headers:
				pids = query_probes[header]

				for pid in pids:
					if pid not in prb_results.values():
						# print 'appended add. prb_id'
						prb_results[header] = pid
						probe_headers.remove(header)
						break

			# print prb_results
			# print probe_headers

			# next, go through prb_results for ode check
			adjusted_headers = set(query_probes.keys()) - set(probe_headers)
			ode_headers = list(adjusted_headers)
			for xref in adjusted_headers:
				xprobes = query_probes[xref]
				ode_results[xref] = None

				for xprobe in xprobes:
					if xprobe in query_odes.keys():
						odes = query_odes[xprobe]
						for ode in odes:
							if ode not in ode_results.values():
								ode_results[xref] = ode
								ode_headers.remove(xref)
								break

			# print ode_results
			# print ode_headers

			# TESTING
			if len(ode_results) != len(prb_results):
				print 'somethings gone wrong at the end of handle_platforms...'
				exit()

			# next, update geneset
			adjusted_headers = list(set(adjusted_headers) - set(ode_headers))
			geneset.update_geneset_values(adjusted_headers)
			geneset.update_microInfo(prb_map=prb_results, ode_map=ode_results)

	def handle_symbols(self):
		"""Handles symbol condition.
		"""
		print 'handling symbol assignment...'
		# for each geneset
		for gs_abbrev, geneset in self.genesets.iteritems():
			results = {}

			# look up ode_gene_ids for each ref_id
			query_id = self.query_genes(geneset.species, geneset.geneset_values.keys())

			all_gene_ids = []
			all_results = {}
			for (all_ref, all_pref, all_gdb), all_ids in query_id.iteritems():
				all_gene_ids += all_ids
				all_results[all_ref] = all_ids
			all_gene_ids = list(set(all_gene_ids))
			all_refs = all_results.keys()

			# look up preferred ode_ref_ids for each gene_id
			query_refs = self.query_prefRef(self.species, self.gs_gene_id_type,
			                                all_gene_ids)

			# go through query_ids and see if single values 'pass'
			poss_keys = query_id.keys()
			x_results = {}
			for (all_ref, all_pref, all_gdb), all_ids in query_id.iteritems():
				if all_ref not in results.keys():
					if all_pref and all_gdb == self.gs_gene_id_type:
						poss_keys.remove((all_ref, all_pref, all_gdb))
						all_refs.remove(all_ref)
						x_results[all_ref] = all_ids

			# go through the remaining possibilities
			next_poss = {}  # {ref_id: [poss_refs,],}
			for poss_ref in all_refs:
				poss_ids = all_results[poss_ref]
				for poss_id in poss_ids:
					if poss_id not in results.values():
						# look up in query_refs
						next_poss[poss_ref] = query_refs[poss_id]
						print '\nEDIT: remaining possibilities in handle_symbols (ask Tim)\n'
						exit()

			# go through the x_results (those found first time)
			for xref, xids in x_results.iteritems():
				for xid in xids:
					if xid not in results.values():
						results[xref] = xid
						break

			# check to make sure all values were found
			if len(results) != len(geneset.geneset_values):
				# EDIT: here is where you'd add a new gene
				err = "Error: missing ode_gene_id for input value(s), " \
				      "%s" % (set(all_results.keys()) - set(results.keys()))
				self.set_errors(critical=err)

			print results

			print 'made it to the end'
			exit()
			# next, update genesets
			relevant_headers = results.keys()
			# must preserve original header list for update_geneset_values to work
			# if diff for any reason, will need to call 'set_geneset_values' instead
			geneset.update_geneset_values(relevant_headers)
			# geneset.update_symbolInfo(ode_map=)
			# need header -> ode

	# ----------------- DATABASE -------------------------------------------------#

	def launch_connection(self):
		""" Launches psql connection to GeneWeaver database.
		"""
		data = config.get('db', 'database')
		user = config.get('db', 'user')
		password = config.get('db', 'password')
		host = config.get('db', 'host')

		print host  # TESTING

		# set up connection information
		cs = 'host=\'%s\' dbname=\'%s\' user=\'%s\' password=\'%s\'' % (host, data, user, password)

		try:
			self.connection = psycopg2.connect(cs)  # connect to geneweaver database
			self.cur = self.connection.cursor()
		except SyntaxError:  # cs most likely wouldn't be a useable string if wasn't able to connect
			print "Error: Unable to connect to database."
			exit()

	def commit(self):
		""" If test, does nothing. Otherwise, commits the query.
		"""
		if self.test:
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

	def query_platformProbes(self, pfid, refs):
		""" Returns a mapping of prb_ids -> prb_ref_ids for the given platform
			+ probe references.
		"""
		# error handling for input types
		try:
			pfid = int(pfid)
			gene_refs = tuple(refs)
		except ValueError:
			err = "Error: Incorrect input type(s) entered into Batch.query_platformProbes. " \
			      "Paramter 'refs' should be a tuple or a list, 'pfid' should be an int."
			self.set_errors(critical=err)

		# set up query
		query = 'SELECT prb_id, prb_ref_id ' \
		        'FROM odestatic.probe ' \
		        'WHERE pf_id = %s ' \
		        'AND prb_ref_id IN %s;'

		# execute query
		self.cur.execute(query, [pfid, gene_refs])

		# results in a list of tuples [(prb_ref_id, prb_id),]
		res = self.cur.fetchall()

		# cast to dictionary  {prb_ref_id: [prb_id,],}
		results = {}
		for r in res:
			# if the prb_ref_id not in results, add it
			if r[1] not in results:
				results[r[1]] = [r[0]]
			# otherwise, append additional prb_id
			else:
				results[r[1]].append(r[0])

		# check to make sure all were found
		diff = set(refs) - set(results.keys())

		if not diff:
			return results
		elif len(diff) == len(refs):
			err = 'Error: unable to find any genes that match those provided in the file. ' \
			      'Please check the geneset gene id type and try again.'
			self.set_errors(critical=err)
		else:
			err = 'Warning: some prb_ref_ids were not ' \
			      'found, + therefore will not be included in the ' \
			      'geneset. \nNOT_FOUND=', diff
			self.set_errors(noncritical=err)
			return results

	def query_probe2gene(self, prbids):
		""" Returns a mapping of platform IDs against ode gene IDs, for the given set
			of platform probes.
		"""
		print 'querying probe2gene...'

		# error handling for input types
		try:
			prb_ids = tuple(prbids)
		except ValueError:
			err = "Error: Incorrect input type(s) entered into Batch.query_probe2gene. " \
			      "Paramter 'refs' should be a tuple or a list, 'pfid' should be an int."
			self.set_errors(critical=err)

		# set up query
		query = 'SELECT prb_id, ode_gene_id ' \
		        'FROM extsrc.probe2gene ' \
		        'WHERE prb_id IN %s;'

		# execute query
		self.cur.execute(query, [prb_ids])

		# returns a list of tuples [(prb_id, ode_gene_id),]
		res = self.cur.fetchall()

		# cast to dictionary {prb_id: [ode_gene_id,],}
		results = {}
		for r in res:
			# if prb_id not in results, add it
			if r[0] not in results.keys():
				results[r[0]] = [r[1]]
			# otherwise, append additional ode_gene_id
			else:
				results[r[0]].append(r[1])

		# EDIT: put duplicate detection here if required

		# check to make sure all were found
		diff = set(prbids) - set(results.keys())
		if not diff:
			return results
		else:
			err = 'Warning: some prb_ids were not ' \
			      'found, + therefore will not be included in the ' \
			      'geneset. \nNOT_FOUND=%s' % diff
			self.set_errors(noncritical=err)
			return results

	def query_genes(self, sp_id, poss_refs):
		""" Queries database for possible ode_gene_ids. Returns a dictionary
			containing ode_ref_ids mapped to a nested array.
		"""
		print 'querying ode_gene_ids...'
		# set up the query
		query = 'SELECT ode_ref_id, ode_gene_id, ode_pref, gdb_id ' \
		        'FROM extsrc.gene ' \
		        'WHERE sp_id = %s ' \
		        'AND ode_ref_id IN %s;'

		# execute the query
		self.cur.execute(query, [sp_id, tuple(poss_refs)])

		# returns a list of tuples [(ode_ref_id, ode_gene_id, ode_pref, gdb_id'),]
		res = self.cur.fetchall()

		if not len(res):  # EDIT: change here if you want to allow for novel user input
			err = "Error: Unable to upload batch file as no genes were found.\n" \
			      "Check text file input before reattempting the batch file upload.\n"
			self.set_errors(critical=err)

		# cast result to a dictionary {(ode_ref_id, ode_pref, gdb_id): [ode_gene_id,]}
		results = {}
		xrefs = []
		for r in res:
			r = list(r)
			xrefs += [r[0]]
			key = tuple([r[0]] + r[2:])
			# if (ode_ref_id, ode_pref, gdb_id) not in results, add it
			if key not in results.keys():
				results[key] = [r[1]]
			else:
				results[key].append(r[1])
		xrefs = set(xrefs)

		# check to make sure that all refs were found
		diff = set(poss_refs) - xrefs
		if not diff:
			return results
		else:
			err = 'Warning: some ode_ref_ids were not found, + will therefore ' \
			      'not be included in the geneset. \nNOT_FOUND=%s' % diff
			self.set_errors(noncritical=err)
			return results

	def query_prefRef(self, sp_id, gdb_id, ode_ids):
		""" Looks up ode_gene_ids, given global query criteria.
		"""
		print 'querying preferred reference ids...'
		# error handling for input types
		ode_ids = tuple(ode_ids)

		# set up query
		query = 'SELECT ode_gene_id, ode_ref_id ' \
		        'FROM extsrc.gene ' \
		        'WHERE sp_id = %s ' \
		        'AND gdb_id = %s ' \
		        'AND ode_pref = TRUE ' \
		        'AND ode_gene_id IN %s;'

		# execute query
		self.cur.execute(query, [sp_id, gdb_id, ode_ids])

		# returns a list of tuples [(ode_gene_id, ode_ref_id),]
		res = self.cur.fetchall()

		# cast as a dictionary {ode_gene_id: [ode_ref_id,],}
		results = {}
		for (gene_id, ref_id) in res:
			if gene_id not in results.keys():
				results[gene_id] = [ref_id]
			else:
				results[gene_id].append(ref_id)

		# check to make sure that all the refs were found
		diff = set(ode_ids) - set(results.keys())
		if not diff:
			return results
		else:
			err = 'Warning: some ode_gene_ids were not found. ' \
			      '\nNOT_FOUND=%s' % diff
			self.set_errors(noncritical=err)
			return results

	def search_pubmed(self, pmid):

		print 'looking up PubMed ID...'
		# URL for pubmed article summary info
		url = ('http://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi?'
		       'retmode=json&db=pubmed&id=%s') % str(pmid)
		# NCBI eFetch URL that only retrieves the abstract
		url_abs = ('http://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi'
		           '?rettype=abstract&retmode=text&db=pubmed&id=%s') % str(pmid)

		res = requests.get(url).content
		temp = json.loads(res)['result']

		self.publication['pub_id'] = None
		self.publication['pub_pubmed'] = str(pmid)
		self.publication['pub_pages'] = temp[self.publication['pub_pubmed']]['pages']
		self.publication['pub_title'] = temp[self.publication['pub_pubmed']]['title']
		self.publication['pub_journal'] = temp[self.publication['pub_pubmed']]['fulljournalname']
		self.publication['pub_volume'] = temp[self.publication['pub_pubmed']]['volume']

		authors = ""  # will hold a CSV list
		for auth in temp[self.publication['pub_pubmed']]['authors']:
			authors += auth['name'] + ', '
		self.publication['pub_authors'] = authors[:-2]

		if 'Has Abstract' in temp[self.publication['pub_pubmed']]['attributes']:
			res2 = requests.get(url_abs).content.split('\n\n')[-3]
			self.publication['pub_abstract'] = res2
		else:
			err = 'Warning: The PubMed info retrieved from NCBI was incomplete. No ' \
			      'abstract data will be attributed to this GeneSet.'
			self.set_errors(noncritical=err)

	def insert_publication(self):
		print 'handling publication insertion...'

		if self.publication:
			# set up query
			query = 'INSERT INTO production.publication ' \
			        '(pub_authors, pub_title, pub_abstract, pub_journal, ' \
			        'pub_volume, pub_pages, pub_pubmed) ' \
			        'VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING pub_id;'

			vals = [self.publication['pub_authors'], self.publication['pub_title'],
			        self.publication['pub_abstract'], self.publication['pub_journal'],
			        self.publication['pub_volume'], self.publication['pub_pages'],
			        self.publication['pub_pubmed']]

			# execute query
			self.cur.execute(query, vals)
			self.commit()

			res = self.cur.fetchall()[0][0]
			self.publication['pub_id'] = str(res)

	# ---------------------ERROR HANDLING------------------------------------------#

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
		if crit_count:
			print "Critical error messages added [%i]\n" % crit_count
			for c in self.crit:
				print c
			exit()  # NOTE: might not be the way you want to leave this
		if noncrit_count:
			print "Noncritical error messages added [%i]\n" % noncrit_count

	# -----------------------------FILE HANDLING-----------------------------------#

	def read_file(self, fp):
		""" Reads in from a source text file, using the location stored in global
			var, 'input_file', + generates objs for data handling.
		"""
		with open(fp, 'r') as file_path:
			lines = file_path.readlines()
			self.file_toString = ''.join(lines)

			# first, detect how many GeneSets we need to create here
			numGS, gs_locs = self.calc_numGeneSets(self.file_toString)

			# second, find + assign required header values to global vars
			currPos = 0
			for line in lines:
				currPos += len(line)
				if currPos < gs_locs[0]:  # only search the metadata headers
					stripped = line.strip()
					if stripped[:1] == '#' or stripped[:2] == '\n' or not stripped:
						continue
					elif stripped[:1] == '!':  # score type indicator
						score = stripped[1:].strip()
						self.assign_threshVals(score)
					elif stripped[:1] == '@':  # species type indicator
						sp = stripped[1:].strip()
						self.assign_species(sp)
					elif stripped[:1] == '%':  # geneset gene id type
						gid = stripped[1:].strip()
						self.assign_geneType(gid)
					elif stripped[:2] == 'A ':  # group type
						grp = stripped[1:].strip()
						self.assign_groupType(grp)
					elif stripped[:2] == 'P ':  # pubmed id
						pub = stripped[1:].strip()
						self.search_pubmed(pub)
				else:
					break

			# third, isolate GeneSet info + create GeneSet objs
			currGS = 1
			for x in range(numGS):
				if currGS != numGS:
					gs = self.file_toString[gs_locs[x]: gs_locs[x + 1]]
					self.create_geneset(gs.strip())
				else:
					gs = self.file_toString[gs_locs[x]:]
					self.create_geneset(gs.strip())
				currGS += 1

		print "handling file parsing + global assignments..."

	def calc_numGeneSets(self, gs_file):
		print 'calculating number of GeneSets in file...'
		# if any of these fail, we know that the file is missing key info
		try:
			bang = gs_file.split('!')
			at = gs_file.split('@')
			perc = gs_file.split('%')
			equiv = gs_file.split('=')
			colon = gs_file.split(':')
		except ValueError:
			err = 'Error: Critical GeneSet information is missing. ' \
			      'Please refer to the documentation to make sure that ' \
			      'everything is labelled correctly.'
			self.set_errors(critical=err)

		# should only contain one of the following
		if len(bang) != 2 or len(at) != 2 or len(perc) != 2:
			err = 'Error: Critical GeneSet information is missing. ' \
			      'Please refer to the documentation to make sure that ' \
			      'everything is labelled correctly.'
			self.set_errors(critical=err)

		# should be of equal number
		if len(colon) != len(equiv):
			err = 'Error: Incorrect GeneSet labelling. Please refer to ' \
			      'the documentation.'
			self.set_errors(critical=err)

		# see which GeneSet header label comes first
		len_colon = 0
		len_equiv = 0
		order = {}  # TESTING
		first_loc = []
		for x in range(len(colon) - 1):  # last items should be equal, so skip
			len_colon += len(colon[x])
			len_equiv += len(equiv[x])
			# print len_colon, len_equiv
			if len_colon < len_equiv:
				order[x] = ':'  # TESTING
				first_loc.append(len_colon)
			else:
				order[x] = '='  # TESTING
				first_loc.append(len_equiv)
		# print order #  TESTING

		numGS = len(colon) - 1
		print 'estimated number of GeneSets in this file: %s' % numGS
		return numGS, first_loc

	def assign_threshVals(self, score):
		print 'checking + assigning score type...'
		score = score.replace(' ', '').lower()

		if 'binary' in score:
			self.score_type = '3'
		elif 'p-value' in score:
			self.score_type = '1'
			try:
				values = score.split('<')
				if len(values) == 1:  # then no value was actually given
					raise ValueError
				self.threshold = values[1]
			except ValueError:
				self.threshold = '0.05'
				err = 'Warning: P-Value threshold not specified. ' \
				      'Using "P-Value < 0.05".'
				self.set_errors(noncritical=err)
		elif 'q-value' in score:
			self.score_type = '2'
			try:
				values = score.split('<')
				if len(values) == 1:  # then no value was actually given
					raise ValueError
				self.threshold = values[1]
			except ValueError:
				self.threshold = '0.05'
				err = 'Warning: Q-Value threshold not specified. ' \
				      'Using "Q-Value < 0.05".'
				self.set_errors(noncritical=err)
		elif 'correlation' in score:
			self.score_type = '4'
			try:
				values = score.split('<')
				if len(values) != 3:  # then something is missing: assume default
					raise ValueError
				self.threshold = values[0] + ',' + values[2]
			except ValueError:
				self.threshold = '-0.75,0.75'
				err = 'Warning: Correlation thresholds not specified properly. ' \
				      'Using "-0.75 < Correlation < 0.75".'
				self.set_errors(noncritical=err)
		elif 'effect' in score:
			self.score_type = '5'
			try:
				values = score.split('<')
				if len(values) != 3:  # then something is missing: assume default
					raise ValueError
				self.threshold = values[0] + ',' + values[2]
			except ValueError:
				self.threshold = '0,1'
				err = 'Warning: Effect size thresholds not specified properly. ' \
				      'Using "0 < Effect < 1".'
				self.set_errors(noncritical=err)

	def assign_species(self, sp):
		print 'checking + assigning species type...'
		sp = sp.lower()

		if sp in self.species_types.keys():
			self.species = self.species_types[sp]
		else:
			err = 'Error: Unable to identify the input species type, %s. ' \
			      'Please refer to the documentation for a list of species types, ' \
			      'written out by their scientific name.' % sp
			self.set_errors(critical=err)

	def assign_geneType(self, gid):
		print 'checking + assigning gene ID type...'
		gid = gid.lower().strip()

		if gid in self.gene_types.keys():
			self.gs_gene_id_type = self.gene_types[gid]
		# check to see if it is a microarray
		elif gid[11:] in self.micro_types.keys():
			self.gs_gene_id_type = self.micro_types[gid[11:]]
			self.microarray = gid[11:]
		else:
			err = 'Error: Unable to determine the gene type provided. ' \
			      'Please consult the documentation for a list of types.'
			self.set_errors(critical=err)

	def assign_groupType(self, grp='private'):
		print 'checking + assigning group type...'
		grp = grp.lower()

		if grp == 'public':
			self.privacy = '0'
		else:
			self.privacy = '-1'

	def create_geneset(self, raw_info):
		print 'creating GeneSet obj...'
		# create UploadGeneSet obj
		gs = UploadGeneSet(self)

		gs_info = raw_info.split('\n')
		desc = []  # store as list, as can span multiple lines
		content_loc = 0
		for info in gs_info:
			info = info.strip()
			if info[:1] == ':':
				gs.set_abbrev(info[1:].strip())
			elif info[:1] == '=':
				gs.set_name(info[1:].strip())
			elif info[:1] == '+':
				desc.append(info[1:].strip())
			elif not info:
				# keep track of the location of the last blank line
				content_loc = gs_info.index(info)

			# add concatenated description to UploadGeneSet obj
		gs.set_description(' '.join(desc))

		# add content to UploadGeneSet obj
		gs_vals = {}
		vals = []  # in case score type is Binary, + we need to derive the max val
		for data in gs_info[content_loc + 1:]:
			try:
				gene, val = data.split('\t')
				vals.append(float(val))
				gs_vals[gene.strip()] = val.strip()
			# add the threshold val if binary
			except ValueError:
				err = "Error: Data points should be in the format 'gene " \
				      "id <tab> data value', with each data point on a " \
				      "separate line. Please check the file and make sure that you did " \
				      "not include an empty geneset with no genes."
				self.set_errors(critical=err)

		# pass GeneSet values along to UploadGeneSet obj
		gs.set_genesetValues(gs_vals)

		# if the score type is Binary, still need to assign a threshold value
		if self.score_type == '3':
			self.threshold = str(max(vals))
			gs.set_threshold(self.threshold)

		# add UploadGeneSet obj to global dict
		self.genesets[gs.abbrev_name] = gs


class UploadGeneSet:
	def __init__(self, batch):
		print "initializing GeneSet object..."

		self.batch = batch
		self.gs_gene_id_type = batch.gs_gene_id_type
		self.pubmed = batch.pubmed  # PubMed ID
		self.group = batch.privacy  # group (public or private)
		self.score_type = batch.score_type  # gs_threshold_type
		self.threshold = batch.threshold  # gs_threshold
		self.species = batch.species  # sp_id

		# GeneSet fields
		self.geneset_values = {}  # {gene id: gene value,} (for gsv_value_list)
		self.abbrev_name = ''  # gs_abbreviation
		self.name = ''  # gs_name
		self.description = ''  # gs_description
		self.file_id = None

		self.count = 0
		self.gs_id = None

		# platform fields
		self.prb_info = None
		self.ode_info = None

		# symbol fields
		self.header2ode = None   # {gene id (original ref): ode_gene_id, }

	def upload(self):
		print "initiating upload sequence..."
		self.insert_file()
		self.insert_geneset()
		self.insert_geneset_values()
		self.modify_gsv_lists()

	# -----------------------MUTATORS--------------------------------------------#
	def set_genesetValues(self, gsv_values):
		print 'setting GeneSet value list...'
		if type(gsv_values) == dict:
			self.geneset_values = gsv_values
		else:
			err = 'Error: Expected to recieve a dictionary of GeneSet values in ' \
			      'UploadGeneset.set_genesetValues() where "{gene id: gene value, }".'
			self.batch.set_errors(critical=err)

	def set_abbrev(self, abbrev):
		print 'setting abbreviated GeneSet name...'
		self.abbrev_name = abbrev

	def set_name(self, gs_name):
		print 'setting GeneSet name...'
		self.name = gs_name

	def set_description(self, desc):
		print 'setting GeneSet description...'
		self.description = desc

	def set_threshold(self, thresh):
		print 'setting GeneSet threshold value...'
		self.threshold = str(thresh)

	def update_geneset_values(self, headers):
		print 'updating geneset values...'
		res = {}
		for header in headers:
			res[header] = self.geneset_values[header]
		self.geneset_values = res

		# update global count to reflect changes
		self.update_count()

	def update_microInfo(self, prb_map, ode_map):
		print 'updating platform info...'
		# prb_map {prb_ref_id: prb_id}
		# ode_map {prb_ref_id: ode_gene_id}

		self.prb_info = prb_map
		self.ode_info = ode_map

	def update_symbolInfo(self, ode_map):
		# ode_map expects {ref_id: ode_gene_id, }
		print 'updating gsv lists...'
		self.header2ode = ode_map

	def update_count(self):
		self.count = len(self.geneset_values)

	def geneweaver_setup(self):
		print "will identify the preliminary features of the GeneWeaver query, + populate globals..."

	def create_genes(self):
		print "will generate new UploadGene objs..."
		# if handling platforms
		if self.batch.microarray:
			print self.ode_info
			print self.prb_info
			print self.geneset_values

		# if handling symbols

		# if self.geneset_values:
		# 	for gene_id, value in self.geneset_values.iteritems():
		# 		# create UploadGene obj, adding these raw data
		# 		g = UploadGene(self)
		# 		g.set_rawID(gene_id)
		# 		g.set_rawVal(value)
		# 		g.setup()
		#
		# 		# store UploadGene obj in global dict
		# 		self.genes[gene_id] = g
		# else:
		# 	err = "Error: Unable to create UploadGene objs in UploadGeneSet, as there " \
		# 	      "are no values in 'self.geneset_values'."
		# 	self.batch.set_errors(critical=err)

	def insert_file(self):
		print "inserting file..."
		# gather contents
		contents = ''
		for gene, score in self.geneset_values.iteritems():
			curline = str(gene) + '\t' + str(score) + '\n'
			contents += curline

		# set up query
		query = 'INSERT INTO production.file ' \
		        '(file_size, file_uri, file_contents, file_comments, ' \
		        'file_created, file_changes) ' \
		        'VALUES (%s, %s, %s, %s, NOW(), \'\') RETURNING file_id;'

		vals = [self.count, self.name, contents, '']

		# execute query
		self.batch.cur.execute(query, vals)
		self.batch.commit()

		self.file_id = self.batch.cur.fetchall()[0][0]

	def insert_geneset(self):
		print 'inserting geneset...'

		# set up query
		query = 'INSERT INTO geneset ' \
		        '(file_id, usr_id, cur_id, sp_id, gs_threshold_type, ' \
		        'gs_threshold, gs_created, gs_updated, gs_status, ' \
		        'gs_count, gs_uri, gs_gene_id_type, gs_name, ' \
		        'gs_abbreviation, gs_description, gs_attribution, ' \
		        'gs_groups, pub_id) ' \
		        'VALUES (%s, %s, %s, %s, %s, %s, NOW(), NOW(), \'normal\', ' \
		        '%s, \'\', %s, %s, %s, %s, 0, %s, %s) RETURNING gs_id;'

		vals = [self.file_id, self.batch.user_id, self.batch.cur_id,
		        self.species, self.score_type, self.threshold, self.count,
		        self.gs_gene_id_type, self.name, self.abbrev_name,
		        self.description, self.group, self.batch.publication['pub_id']]

		# execute query
		self.batch.cur.execute(query, vals)
		self.batch.commit()

		self.gs_id = self.batch.cur.fetchall()[0][0]

	def insert_geneset_values(self):
		print 'inserting geneset values...'
		# set up query
		query = 'INSERT INTO extsrc.geneset_value ' \
		        '(gs_id, ode_gene_id, gsv_value, gsv_hits, gsv_source_list, ' \
		        'gsv_value_list, gsv_in_threshold, gsv_date) ' \
		        'VALUES (%s, %s, %s, 0, %s, %s, %s, NOW());'

		# TESTING / UI
		bar = progressbar.ProgressBar(maxval=len(self.geneset_values)).start()
		count = 0  # TESTING

		# iterate through geneset_values
		for gene_id, value in self.geneset_values.iteritems():
			# find the right ode_gene_id associated w/ gene
			ode_gene = self.header2ode[gene_id]

			# check to see if value is within the threshold
			if float(value) <= float(self.threshold):
				gsv_in_thresh = True
			else:
				gsv_in_thresh = False

			# update gsv_source_list + gsv_value_list after this
			search_vals = [self.gs_id, ode_gene, value, [], [], gsv_in_thresh]
			self.batch.cur.execute(query, search_vals)
			self.batch.commit()
			count += 1  # TESTING
			bar.update(count)  # TESTING
		bar.finish()  # TESTING

		# update the value count for geneset
		self.modify_geneset_count(self.gs_id, self.count)

	def modify_gsv_lists(self):
		print 'updating gsv lists...'
		gsv_source_list = self.geneset_values.keys()
		gsv_value_list = self.geneset_values.values()

		# UPDATE GSV_SOURCE_LIST
		query = 'UPDATE extsrc.geneset_value ' \
		        'SET gsv_source_list = %s ' \
		        'WHERE gs_id = %s;'
		vals = [gsv_source_list, self.gs_id]
		self.batch.cur.execute(query, vals)
		self.batch.commit()

		# UPDATE GSV_VALUE_LIST
		query = 'UPDATE extsrc.geneset_value ' \
		        'SET gsv_value_list = %s ' \
		        'WHERE gs_id = %s;'
		vals = [gsv_value_list, self.gs_id]
		self.batch.cur.execute(query, vals)
		self.batch.commit()

		# UPDATE GSV_DATE
		query = 'UPDATE extsrc.geneset_value ' \
		        'SET gsv_date = NOW() ' \
		        'WHERE gs_id = %s;'
		vals = [self.gs_id]
		self.batch.cur.execute(query, vals)
		self.batch.commit()

		print '\n try alternative method for modify_gsv_lists! \n'
		# EDIT: eventually try instead ->
		# query = 'UPDATE extsrc.geneset_value ' \
		#         'SET (gsv_source_list, gsv_value_list, ' \
		#         'gsv_date) = (%s, %s, NOW()) ' \
		#         'WHERE gs_id = %s;'

	def modify_geneset_count(self, gsid, num):
		print 'modifying geneset count...'
		# set up query
		query = 'UPDATE geneset ' \
		        'SET gs_count = %s ' \
		        'WHERE gs_id = %s'
		vals = [gsid, num]

		# execute + commit query
		self.batch.cur.execute(query, vals)
		self.batch.commit()

def test_dictionaries():
	b = Batch()
	b.populate_dictionaries()

def test_fileParsing(number):
	test = '/Users/Asti/geneweaver/website-py/src/static/text/'
	append = ['affy-batch.txt',         # 0
	          'affy-dup.txt',           # 1
	          'agilent-batch.txt',      # 2
	          'batch-geneset-a.txt',    # 3
	          'batch-geneset-b.txt',    # 4
	          'batch-geneset-c.txt',    # 5
	          'batch-geneset-d.txt',    # 6
	          'empty-geneset.txt',      # 7
	          'symbol-batch.txt']       # 8

	test_file = test + append[number]
	b = Batch(input_filepath=test_file)

if __name__ == '__main__':
	# TESTING
	print sys.argv

	if len(sys.argv) < 2:
		print "Usage: python %s <int_range(9)>" % sys.argv[0]
		print "       where <int_range(9)> specifies an integer" \
		      "       between 0-8 [incl.]"
		exit()
	test_fileParsing(int(sys.argv[1]))

# WORKING
# test_dictionaries()
