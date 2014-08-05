from collections import OrderedDict
from hashlib import md5
from psycopg2.pool import ThreadedConnectionPool


class GeneWeaverThreadedConnectionPool(ThreadedConnectionPool):
    """Extend ThreadedConnectionPool to initialize the search_path"""
    def __init__(self, minconn, maxconn, *args, **kwargs):
        ThreadedConnectionPool.__init__(self, minconn, maxconn, *args, **kwargs)

    def _connect(self, key=None):
        """Create a new connection and set its search_path"""
        conn = super(GeneWeaverThreadedConnectionPool, self)._connect(key)
        cursor = conn.cursor()
        cursor.execute('SET search_path TO production, extsrc, odestatic;')
        conn.commit()

        return conn

# the global threaded connection pool that should be used for all DB connections in this application
pool = GeneWeaverThreadedConnectionPool(
    5, 20,
    database='geneweaver',
    user='odeadmin',
    password='odeadmin',
    host='crick.ecs.baylor.edu',
    port=5432,
)


class PooledConnection(object):
    """
    A pooled connection suitable for using in a with ... as ...: construct (the connection is automatically
    returned to the pool at the end of the with block)
    """

    def __init__(self, conn_pool=pool, rollback_on_exception=False):
        self.conn_pool = conn_pool
        self.rollback_on_exception = rollback_on_exception
        self.connection = None

    def __enter__(self):
        self.connection = self.conn_pool.getconn()
        return self.connection

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.connection is not None:
            if self.rollback_on_exception and exc_type is not None:
                self.connection.rollback()

            self.conn_pool.putconn(self.connection)


class PooledCursor(object):
    """
    A cursor obtained from a connection pool. This is suitable for using in a with ... as ...: construct (the
    underlying connection will be automatically returned to the connection pool
    """

    def __init__(self, conn_pool=pool, rollback_on_exception=False):
        self.conn_pool = conn_pool
        self.rollback_on_exception = rollback_on_exception
        self.connection = None

    def __enter__(self):
        self.connection = self.conn_pool.getconn()
        return self.connection.cursor()

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.connection is not None:
            if self.rollback_on_exception and exc_type is not None:
                self.connection.rollback()

            self.conn_pool.putconn(self.connection)


def dictify_row(cursor, row):
    """Turns the given row into a dictionary where the keys are the column names"""
    d = OrderedDict()
    for i, col in enumerate(cursor.description):
        d[col[0]] = row[i]
    return d


def dictify_cursor(cursor):
    """converts all cursor rows into dictionaries where the keys are the column names"""
    return (dictify_row(cursor, row) for row in cursor)


def get_all_projects(usr_id):
    """
    returns all projects associated with the given project ID
    """
    with PooledCursor() as cursor:
        cursor.execute(
            '''
            SELECT p.*, x.* FROM project p, (
                SELECT p2g.pj_id, COUNT(gs_id), x.count AS deprecated, g.group
                FROM
                    project2geneset p2g
                    LEFT JOIN (
                        SELECT pj_id, COUNT(gs.gs_id)
                        FROM project2geneset p2g, geneset gs
                        WHERE
                            gs_status LIKE 'deprecated%%' AND p2g.gs_id=gs.gs_id
                            AND pj_id IN (SELECT pj_id FROM project WHERE usr_id=%(usr_id)s) GROUP BY pj_id
                    ) x ON x.pj_id=p2g.pj_id
                    LEFT JOIN (
                        SELECT pj_id, grp_name AS GROUP
                        FROM project p, grp g
                        WHERE p.usr_id=%(usr_id)s AND g.grp_id=CAST(p.pj_groups AS INTEGER)
                    ) g ON (g.pj_id=p2g.pj_id)
                WHERE p2g.pj_id IN (SELECT pj_id FROM project WHERE usr_id=%(usr_id)s)
                GROUP BY p2g.pj_id, x.count, g.group
            ) x WHERE x.pj_id=p.pj_id ORDER BY p.pj_name;
            ''',
            {'usr_id': usr_id}
        )

        return list(cursor)


def get_all_species():
    """
    returns an ordered mapping from species ID to species name for all available species
    """
    with PooledCursor() as cursor:
        cursor.execute('''SELECT sp_id, sp_name FROM species ORDER BY sp_id;''')
        return OrderedDict(cursor)


def resolve_feature_id(sp_id, feature_id):
    """
    For the given species and feature IDs get the corresponding ODE gene ID (which
    is our canonical ID type)
    :param sp_id:       species ID
    :param feature_id:  feature ID (this can be a gene ID from any of the many source databases)
    :return:            the list of DB rows containing 3 columns:
                        ODE IDs, gene datbase IDs and reference IDs (should be a case
                        insensitive match of the given feature ID
    """
    with PooledCursor() as cursor:
        cursor.execute(
            '''
            SELECT ode_gene_id, gdb_id, ode_ref_id
            FROM gene
            WHERE sp_id=%(sp_id)s AND LOWER(ode_ref_id)=%(feature_id)s;
            ''',
            {'sp_id': sp_id, 'feature_id': feature_id})

        return list(cursor)


def get_gene_id_types(sp_id=0):
    with PooledCursor() as cursor:
        cursor.execute(
            '''SELECT * FROM genedb WHERE %(sp_id)s=0 OR sp_id=0 OR sp_id=%(sp_id)s ORDER BY gdb_id;''',
            {'sp_id': sp_id})

        return list(dictify_cursor(cursor))


def get_microarray_types(sp_id=0):
    """
    get all rows from the platform table with the given species identifier
    :param sp_id:   the species identifier
    :return:        the list of rows from the platform table
    """
    with PooledCursor() as cursor:
        cursor.execute(
            '''SELECT * FROM platform WHERE (sp_id=%(sp_id)s OR 0=%(sp_id)s) ORDER BY pf_name;''',
            {'sp_id': sp_id})
        return list(dictify_cursor(cursor))


class User:
    def __init__(self, usr_dict):
        self.user_id = usr_dict['usr_id']
        self.first_name = usr_dict['usr_first_name']
        self.last_name = usr_dict['usr_last_name']
        self.email = usr_dict['usr_email']
        self.prefs = usr_dict['usr_prefs']

        usr_admin = usr_dict['usr_admin']
        self.is_curator = usr_admin == 1
        self.is_admin = usr_admin == 2 or usr_admin == 3
        self.last_seen = usr_dict['usr_last_seen']
        self.creation_date = usr_dict['usr_created']
        self.ip_addr = usr_dict['ip_addr']


def _cursor_to_users(cursor):
    return (User(dictify_row(cursor, row)) for row in cursor)


class Publication:
    def __init__(self, pub_dict):
        self.pub_id = pub_dict['pub_id']
        self.authors = pub_dict['pub_authors']
        self.title = pub_dict['pub_title']
        self.abstract = pub_dict['pub_abstract']
        self.journal = pub_dict['pub_journal']
        self.volume = pub_dict['pub_volume']
        self.pages = pub_dict['pub_pages']
        self.month = pub_dict['pub_month']
        self.year = pub_dict['pub_year']
        self.pubmed_id = pub_dict['pub_pubmed']


class Geneset:
    def __init__(self, gs_dict):
        self.geneset_id = gs_dict['gs_id']
        self.user_id = gs_dict['usr_id']
        try:
            self.user = User(gs_dict)
        except KeyError:
            self.user = None
        self.file_id = gs_dict['file_id']
        self.name = gs_dict['gs_name']
        self.abbreviation = gs_dict['gs_abbreviation']
        self.pub_id = gs_dict['pub_id']
        try:
            self.publication = Publication(gs_dict)
        except KeyError:
            self.publication = None
        self.res_id = gs_dict['res_id']
        self.cur_id = gs_dict['cur_id']
        self.description = gs_dict['gs_description']
        self.sp_id = gs_dict['sp_id']
        self.count = gs_dict['gs_count']
        # TODO document what different threshold values mean
        self.threshold_type = gs_dict['gs_threshold_type']
        self.threshold = gs_dict['gs_threshold']
        # a comma seperated list of group IDs (0=development, -1=private)
        self.group_ids = gs_dict['gs_groups']
        self.attribution_old = gs_dict['gs_attribution_old']
        self.uri = gs_dict['gs_uri']
        self.gene_id_type = gs_dict['gs_gene_id_type']
        self.creation_date = gs_dict['gs_created']
        # TODO document how admin flag works. Is it similar to usr_admin in the user table?
        self.admin_flag = gs_dict['admin_flag']
        self.updated_date = gs_dict['gs_updated']
        # TODO document how status works
        self.status = gs_dict['gs_status']
        # TODO figure out what this field is for
        self.gsv_qual = gs_dict['gsv_qual']
        self.attribution = gs_dict['gs_attribution']


def _cursor_to_genesets(cursor):
    return (Geneset(dictify_row(cursor, row)) for row in cursor)


def authenticate_user(email, password):
    """
    Looks up user in the database
    :param email:       the user's email address
    :param password:    the user's password
    :return:            the User with the corresponding email address and password
                        OR None if no such User is found
    """
    email = email.strip()
    if not email or not password:
        # this check is probably not needed but it makes me feel better
        return None
    else:
        with PooledCursor() as cursor:
            password_md5 = md5()
            password_md5.update(password)
            cursor.execute(
                '''SELECT * FROM usr WHERE usr_email=%(email)s AND usr_password=%(password_md5)s''',
                {
                    'email': email,
                    'password_md5': password_md5.hexdigest(),
                }
            )
            users = list(_cursor_to_users(cursor))
            return users[0] if len(users) == 1 else None


def get_user(user_id):
    """
    Looks up a User in the database
    :param user_id:     the user's ID
    :return:            the User matching the given ID or None if no such user is found
    """
    with PooledCursor() as cursor:
        cursor.execute('''SELECT * FROM usr WHERE usr_id=%s''', (user_id,))
        users = list(_cursor_to_users(cursor))
        return users[0] if len(users) == 1 else None


def get_geneset(geneset_id, user_id=None):
    """
    Gets the Geneset if either the geneset is publicly visible or the user
    has permission to view it.
    :param geneset_id:  the geneset ID
    :param user_id:     the user ID that needs permission
    :return:            the Geneset corresponding to the given ID if the
                        user has read permission, None otherwise
    """

    # TODO not sure if we really need to convert to -1 here. The geneset_is_readable function may be able to handle None
    if user_id is None:
        user_id = -1

    with PooledCursor() as cursor:
        cursor.execute(
            '''SELECT * FROM geneset WHERE gs_id=%(geneset_id)s AND geneset_is_readable(%(user_id)s, %(geneset_id)s)''',
            {
                'geneset_id': geneset_id,
                'user_id': user_id,
            }
        )
        genesets = list(_cursor_to_genesets(cursor))
        return genesets[0] if len(genesets) == 1 else None
