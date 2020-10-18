from collections import Counter as mset
from collections import defaultdict as dd
from copy import deepcopy
import re

import geneweaverdb as gwdb
from pubmedsvc import get_pubmed_info
from batch import __parse_batch_syntax, __insert_geneset_file

class BatchReader(object):
    """
    Class used to read and parse batch variant geneset files.

    public
        contents:   list of lines in the batch file
        usr_id:     ID of the user uploading the batch file
        genesets:   list of dicts representing the parsed genesets, each dict
                    has fields corresponding to columns in the geneset table
        errors:     list of strings indicating critical errors found during
                    parsing
        warns:      list of strings indicating non-crit errors found during
                    parsing

    private
        _parse_set:         the gene set currently being parsed
        _pub_map:           PMID -> pub_id mapping
        _symbol_cache:      a series of nested dicts used to map species
                            specific gene symbols to GW identifiers. The
                            structure is:
                                sp_id -> gdb_id -> ode_ref_id -> ode_gene_id
                                ** this will probably change?**
        _annotation_cache:  mapping of ontology term IDs -> ont_ids
    """


    def parse_batch_file():
        """
        Parses a batch file to completion.

        arguments
            bs:     string containing the contents of the batch file
            usr_id: ID of the user uploading the gene sets

        returns
            A list of gene set objects (dicts) with properly filled out fields,
            ready for insertion into the GW DB.
        """
        ## errors that prevent further parsing
        self.errors = []
        ## warnings generated during parsing
        self.warns = []
        ## list of gs_ids successfully added to the db
        added = []

        if not bs:
            bs = self.contents

        if not usr_id:
            usr_id = self.usr_id

        self.__parse_batch_syntax(bs)

        if self.errors:
            return []

        for gs in self.genesets:
            gs['usr_id'] = usr_id
            gs['gs_is_variant'] = True;

        return self.genesets

    def insert_variantset(self):
        """
        Inserts parsed gene sets along with their files, values, and
        annotations into the DB.

        returns
            the gs_ids of the inserted sets
        """
        ids = []

        for gs in self.genesets:

            if not gs['gs_count']:

                self.errors.append((
                    'No genes in the set %s mapped to GW identifiers so it '
                    'was not uploaded'
                ) % gs['gs_name'])

                continue

            if not gs['pub_id'] and gs['pub']:
                gs['pub_id'] = gwdb.insert_publication(gs['pub'])

            gs['file_id'] = self.__insert_geneset_file(gs['values'])
            gs['gs_id'] = gwdb.insert_variantset(gs)

            ids.append(gs['gs_id'])

        return ids
