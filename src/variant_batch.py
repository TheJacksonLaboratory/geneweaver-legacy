from collections import Counter as mset
from collections import defaultdict as dd
from copy import deepcopy
import re

import geneweaverdb as gwdb
from pubmedsvc import get_pubmed_info
import batch

class BatchReader(batch.BatchReader):
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


    def parse_batch_file(self, bs='', usr_id=0):
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
        print("Parsing in VariantBatch")
        self.__parse_batch_syntax(bs)

        if self.errors:
            return []

        for gs in self.genesets:
            gs['usr_id'] = usr_id
            gs['gs_is_variant'] = True;

        return self.genesets

    def insert_genesets(self):
        print("Overloading")
        """
        Inserts parsed gene sets along with their files, values, and
        annotations into the DB.
        For variant_set, if gs_count is not found, set it to null.

        returns
            the gs_ids of the inserted sets
        """
        ids = []

        for gs in self.genesets:
            print(gs)
            gs['gs_count'] = 1
            if not gs['gs_count']:
                print("error in variant_batch.py insert_variantset")
                gs['gs_count'] = 0
                self.errors.append((
                    'No genes in the set %s mapped to GW identifiers so it '
                    'was not uploaded'
                ) % gs['gs_name'])

                continue

            if not gs['pub_id'] and gs['pub']:
                gs['pub_id'] = gwdb.insert_publication(gs['pub'])

            gs['file_id'] = self.__insert_geneset_file(gs['values'])
            gs['gs_id'] = gwdb.insert_variantset(gs)
            self.__insert_geneset_values(gs)
            self.__insert_annotations(gs)

        return ids

    def __insert_geneset_values(self, gs):
        """
        Inserts gene set values into the DB.

        arguments
            gs: gene set object
        """

        ttype = gs['gs_threshold_type']
        thresh = None

        if ttype == 1 or ttype == 2 or ttype == 3:
            thresh = float(gs['gs_threshold'])

        elif ttype == 4 or ttype == 5:
            thresh = map(float, gs['gs_threshold'].split(','))

        ## This should never happen
        else:
            thresh = 1.0

        for ref, ode, value in gs['geneset_values']:
            gwdb.insert_variantset_value(
                gs['gs_id'], ode, value
            )
