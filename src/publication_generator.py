from __future__ import print_function
import geneweaverdb
import pub_assignments
import re
import urllib
import urllib2

PUBMED_SEARCH_URL = 'http://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi?db=pubmed&term=%s&usehistory=y'
PUBMED_DATA_URL = 'http://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi?db=pubmed&usehistory=y&query_key=%s&WebEnv=%s&retmode=xml'
TO_MONTH_NAME = {
    '1': 'Jan', '2': 'Feb', '3': 'Mar', '4': 'Apr', '5': 'May', '6': 'Jun',
    '7': 'Jul', '8': 'Aug', '9': 'Sep', '10': 'Oct', '11': 'Nov', '12': 'Dec'
}


class PublicationGenerator(object):
    """
    This class represents a predefined pubmed query for bringing back a list of publications.
    The query is stored as a "querystring" attribute, and should use syntax as definded on the pubmed website.
    The class is persisted to the GeneWeaver database.  If an instance of this class is created and it does not
    already include a database generated stubgenid, then the constructor will automatically save this generator to
    the database.
    """

    def __init__(self, **kwargs):
        """
        Parameter **kwargs has the following expected attributes

        :param name: User defined name of the generator
        :param querystring: Valid pubmed search string
        :param last_update: The last time this generator was run
        :param usr_id: User who created this
        :param grp_id: Group for which this generator was created
        :param grp_name: Convenience parameter, containing the name of the above group
        :param stubgenid:  If this is provided, it is assumed the generator exists in the database, if not, generator is
                           saved, an id is created, and then set.
        """
        self.name = kwargs.get('name')
        self.querystring = kwargs.get('querystring')
        self.last_update = kwargs.get('last_update')
        self.usr_id = kwargs.get('usr_id')
        self.grp_id = kwargs.get('grp_id')
        self.grp_name = kwargs.get('grp_name')

        # stubgenid is a database generated identifier.  If it is not passed, we assume that this is a new generator
        # thus needing to be inserted into the database.
        self.stubgenid = kwargs.get('stubgenid')
        if not self.stubgenid:
            self.save()

    @staticmethod
    def get_generator_by_id(generator_id):
        """
        Simple static method to pull an instance of a generator from the database by it's generator_id.

        :param generator_id: Maps to a stubgenid in the gwcuration.stubgenerators table.
        :return: An instance of the PublicationGenerator class if the id exists, otherwise method returns "None"
        """
        """
        Fetch the PublicationGenerator object for the given ID
        :return:  If ID is valid returns PublicationGenerator object, otherwise returns None
        """
        with geneweaverdb.PooledCursor() as cursor:

            cursor.execute("SELECT * FROM gwcuration.stubgenerators WHERE stubgenid=%s;", (generator_id,))
            rows = geneweaverdb.dictify_cursor(cursor)
            return PublicationGenerator(**next(rows)) if rows else None

    def save(self):
        """
        Saves a PublicationGenerator instance to the database.  If stubgenid is None this method will create a new
        record in the database, otherwise it will only save changes to the querystring attribute.

        :return: No return value
        """
        with geneweaverdb.PooledCursor() as cursor:
            if not self.stubgenid:
                cursor.execute(
                    'INSERT INTO gwcuration.stubgenerators (name, querystring, grp_id, usr_id) values (%s, %s, %s, %s);',
                    (self.name, self.querystring, self.grp_id, self.usr_id))
                cursor.connection.commit()

                # Get the database generated stubgenid and set the attribute on the instance
                cursor.execute('''SELECT stubgenid FROM gwcuration.stubgenerators
                               WHERE name = %s AND grp_id = %s AND usr_id = %s ''',
                               (self.name, self.grp_id, self.usr_id))
                self.stubgenid = cursor.fetchone()[0]
            else:
                cursor.execute('UPDATE gwcuration.stubgenerators SET name = %s, querystring = %s, grp_id = %s WHERE stubgenid = %s',
                               (self.name, self.querystring, self.grp_id, self.stubgenid,))
                cursor.connection.commit()

    def run(self):
        """
        Refresh this PublicationGenerator by running it and returning the list of associated pubmed entries

        :return: Returns a list of pubmed entries as GeneratedPublication instances. If the publication already exists
                 in GeneWeaver the GeneratedPublication will also contain the associated PubAssignment
        :raised: If there are communication problems with PubMed an urllib2.HTTPError will be allowed to pass through
        """
        import time
        start = time.time()
        response = urllib2.urlopen(PUBMED_SEARCH_URL % (urllib.quote(self.querystring),)).read()
        query_key = re.search('<QueryKey>([0-9]*)</QueryKey>', response).group(1)
        web_env = re.search('<WebEnv>([^<]*)</WebEnv>', response).group(1)

        # TODO: batch download these instead of all-at-once (10k max)
        # PM_DATA = 'http://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi?db=pubmed&usehistory=y&query_key=%s&WebEnv=%s'
        # Allow HTTPError from communication problems with PubMed to get propogated up
        try:
            response = urllib2.urlopen(PUBMED_DATA_URL % (query_key, web_env)).read()
        except urllib2.HTTPError as e:
            print("Problem communicating with PubMed. {}".format(e.message))
            raise e

        new_time = time.time()
        print("Time querying Pubmed")
        print (new_time - start)
        # Update the generator has having been run
        with geneweaverdb.PooledCursor() as cursor:
            cursor.execute(
                'UPDATE gwcuration.stubgenerators SET last_update=NOW() WHERE stubgenid=%s;',
                (self.stubgenid,))
            cursor.connection.commit()
        return _process_pubmed_response(response)


class GeneratedPublication(object):
    """
    This is a convenience class for encapsulating the attributes of a publication generated by a PublicationGenerator.
    This is not necessarily associated with a persistent object in the database.
    If however the pubmed id is associated with an existing PubAssignement instance, then that object is included
    with the class, and in persisted in pub_assignments and publication tables.
    """

    def __init__(self, **kwargs):
        """
        Simple constructor pulls expected attributes from kwargs.

        :param pmid: Pub Med ID
        :param title: Publication Title
        :param authors: Publication Authors
        :param abstract: Publication abstract
        :param journal: Journal article published in
        :param volume: Volume of said journal
        :param month:  Month of publication
        :param year:  Year of publication
        :param link_to_fulltext: The URL to the publication
        :param pub_assignments:  A list of PubAssignment objects if publication has been assigned to a group and/or curator
        """
        self.pubmed_id = kwargs.get('pmid')
        self.authors = kwargs.get('authors')
        self.title = kwargs.get('title')
        self.abstract = kwargs.get('abstract')
        self.journal = kwargs.get('journal')
        self.volume = kwargs.get('volume')
        self.pages = kwargs.get('pages')
        self.month = kwargs.get('month')
        self.year = kwargs.get('year')
        self.link_to_fulltext = kwargs.get('link_to_fulltext')
        self.pub_assignments = kwargs.get('pub_assigns', [])


def list_generators(user_id, groups):
    """
    For a user and a list of groups return all of the associated publication generators

    :param user_id:  Database generated usr_id from the stubgenerators table.
    :param groups:   A list of database generated grp_id values associated with user_id, for which there may be generators.
    :return: An array of PublicationGenerator objects
    """
    generators = []
    with geneweaverdb.PooledCursor() as cursor:
        cursor.execute(
            '''
                        SELECT DISTINCT stubgenid, sg.name as name, querystring, sg.usr_id,
                        to_char(last_update, 'YYYY-MM-DD') as last_update, sg.grp_id as grp_id, grp_name, LOWER(name)
                        FROM gwcuration.stubgenerators sg LEFT JOIN production.grp g
                        ON sg.grp_id = g.grp_id
                        WHERE usr_id=%s OR sg.grp_id=ANY(%s)
                        ORDER BY LOWER(name), grp_name
                        ''', (str(user_id), '{' + ','.join(groups) + '}')
        )
        generators = [PublicationGenerator(**row_dict) for row_dict in geneweaverdb.dictify_cursor(cursor)]
    return generators


def delete_generator(generator):
    """
    Delete a given PublicationGenerator object from the database

    :param generator: The PublicationGenerator object we want to delete
    :return: Returns an integer value representing number of rows effected. 0 indicates delete did not happen.
    """
    rowcount = 0
    with geneweaverdb.PooledCursor() as cursor:
        # Foreign key constraint required deleting the records from this table first.
        cursor.execute('DELETE FROM gwcuration.stub_status WHERE stubgenid=%s;', (generator.stubgenid,))
        cursor.connection.commit()
        cursor.execute('DELETE FROM gwcuration.stubgenerators WHERE stubgenid=%s;',
                       (generator.stubgenid,))
        rowcount = cursor.rowcount
        cursor.connection.commit()
    return rowcount


def _process_pubmed_response(response):
    """
    Method intended to be treated as private.
    This method takes a PublicationGenerator object and the return of a call to a PubMed query and parses it into a
    result that includes all the publications associated with the query, with the publications already in GeneWeaver
    marked as such.  Additional supporting information about that publication (group and user it is assigned to) will
    be included with the result.

    NOTE:  This is adapted from curation_server._process_pubmed_response, as written by Jeremy Jay.  I kept his code
    mostly intact (with the exception of some format cleanup), and then altered the code where relevant for our
    new workflow.

    :param response:  The PubMed result response received for the given query associated with a PublicationGenerator
    :return:  A list of GeneratedPublication objects.  GeneratedPublication is not persisted in the database.  However,
              they may have an associated PubAssignment if they have already been assigned to a group and/or curator,
              in which case they are persisted as a publication entry and a pub_assignment entry in the database.
    """
    pubmed_results = []
    import time
    start = time.time()
    last = start
    total_parse = 0
    total_db = 0
    total_append = 0
    count = 0
    for match in re.finditer('<PubmedArticle>(.*?)</PubmedArticle>', response, re.S):
        ++count
        last = time.time()
        article_ids = {}
        abstract = ''
        fulltext_link = None

        article = match.group(1)
        article_id_matches = re.finditer('<ArticleId IdType="([^"]*)">([^<]*?)</ArticleId>', article, re.S)
        abstract_matches = re.finditer('<AbstractText([^>]*)>([^<]*)</AbstractText>', article, re.S)
        article_title = re.search('<ArticleTitle[^>]*>([^<]*)</ArticleTitle>', article, re.S).group(1).strip()

        for amatch in article_id_matches:
            article_ids[amatch.group(1).strip()] = amatch.group(2).strip()
        for amatch in abstract_matches:
            abstract += amatch.group(2).strip() + ' '

        if 'pmc' in article_ids:
            fulltext_link = 'http://www.ncbi.nlm.nih.gov/pmc/articles/%s/' % (article_ids['pmc'],)
        elif 'doi' in article_ids:
            fulltext_link = 'http://dx.crossref.org/%s' % (article_ids['doi'],)
        pmid = article_ids['pubmed'].strip()

        author_matches = re.finditer('<Author [^>]*>(.*?)</Author>', article, re.S)
        authors = []
        for author_match in author_matches:
            name = ''
            try:
                name = re.search('<LastName>([^<]*)</LastName>', author_match.group(1), re.S).group(1).strip()
                name = name + ' ' + re.search('<Initials>([^<]*)</Initials>', author_match.group(1), re.S).group(1).strip()
            except:
                pass
            authors.append(name)

        authors = ', '.join(authors)

        journal = re.search('<MedlineTA>([^<]*)</MedlineTA>', article, re.S).group(1).strip()

        pubdate = re.search('<PubDate>.*?<Year>([^<]*)</Year>.*?<Month>([^<]*)</Month>', article, re.S)
        pm = pubdate.group(2).strip()
        if pm in TO_MONTH_NAME:
            pm = TO_MONTH_NAME[pm]
        pub_year = pubdate.group(1).strip()

        new_time = time.time()
        total_parse += new_time - last
        last = new_time
        pub_assigns = []
        with geneweaverdb.PooledCursor() as cursor:
            cursor.execute('''
                SELECT p.pub_id as pub_id, curation_group as grp_id, g.grp_name as grp_name
                FROM production.pub_assignments pa, production.publication p, production.grp g
                WHERE pa.pub_id = p.pub_id
                AND p.pub_pubmed = %s
                AND pa.curation_group = g.grp_id
                ORDER BY p.pub_pubmed
              ''', (pmid,))
            for row in cursor:
                pub_assigns.append(row[2])
        new_time = time.time()
        total_db += new_time - last
        last = new_time
        pubmed_results.append({
            'pmid': pmid,
            'authors': authors,
            'title': article_title,
            'abstract': abstract,
            'journal': journal,
            'month': pm,
            'year': pub_year,
            'link_to_fulltext': fulltext_link,
            'pub_assigns': ", ".join(pub_assigns)
        })
        new_time = time.time()
        total_append += new_time - last
        last = new_time

    print("Total elapsed time")
    print (last - start)
    print("Total time parsing")
    print(total_parse)
    print("Total time in db")
    print(total_db)
    print("Total time appending")
    print(total_append)
    return pubmed_results