from collections import OrderedDict
from hashlib import md5
import json
import string
import random
from psycopg2.pool import ThreadedConnectionPool
import distutils.sysconfig
from distutils.util import strtobool
from tools import toolcommon as tc
import os
import flask
from flask import session


app = flask.Flask(__name__)

RESULTS_PATH = '/var/www/html/geneweaver/results'


class GeneWeaverThreadedConnectionPool(ThreadedConnectionPool):
    """Extend ThreadedConnectionPool to initialize the search_path"""

    def __init__(self, minconn, maxconn, *args, **kwargs):
        ThreadedConnectionPool.__init__(self, minconn, maxconn, *args, **kwargs)

    def _connect(self, key=None):
        """Create a new connection and set its search_path"""
        conn = super(GeneWeaverThreadedConnectionPool, self)._connect(key)
        conn.set_client_encoding('UTF-8')
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


def _dictify_row(cursor, row):
    """Turns the given row into a dictionary where the keys are the column names"""
    d = OrderedDict()
    for i, col in enumerate(cursor.description):
        # TODO find out what the right way to do unicode for postgres is? Is UTF-8 the right encoding here?
        # This prevents exceptions when non-ascii chars show up in a jinja2 template variable
        # but I'm not sure if it's the correct solution
        d[col[0]] = row[i].decode('utf-8') if type(row[i]) == str else row[i]
    return d


def dictify_cursor(cursor):
    """converts all cursor rows into dictionaries where the keys are the column names"""
    return (_dictify_row(cursor, row) for row in cursor)


class Project:
    def __init__(self, proj_dict):
        self.project_id = proj_dict['pj_id']
        self.user_id = proj_dict['usr_id']
        self.name = proj_dict['pj_name']

        # TODO in the database this is column 'pj_groups'. The name suggests
        # that this field can contain multiple groups but it looks like
        # in practice (in the DB) it is always a single integer value. This is why
        #      I name it singular "group_id" here, but this should be confirmed
        #      by Erich
        self.group_id = proj_dict['pj_groups']

        # NOTE: for now I'm ignoring pj_sessionid since it can be dangerous
        #       to let session IDs leak out and I assume it's not really useful
        #       as a readable property (I'm thinking it's more useful as a
        #       query param)
        self.created = proj_dict['pj_created']
        self.notes = proj_dict['pj_notes']

        # depending on if/how the project table is joined the following may be available
        self.count = proj_dict.get('count')
        self.deprecated = proj_dict.get('deprecated')
        self.group_name = proj_dict.get('group')

    def get_genesets(self, auth_user_id):
        return get_genesets_for_project(self.project_id, auth_user_id)


def get_genesets_for_project(project_id, auth_user_id):
    """
    Get all genesets in the given project that the given user is authorized to read
    :param project_id:      the project that we're looking up genesets for
    :param auth_user_id:    the user that is authenticated (we need to ensure that the
                            genesets are readable by the user)
    :return:                A list of genesets in the project
    """
    with PooledCursor() as cursor:
        cursor.execute(
            '''
            SELECT *
            FROM
                (
                    -- selects all genesets for the given project ID
                    SELECT geneset.*
                    FROM geneset INNER JOIN project2geneset
                    ON geneset.gs_id=project2geneset.gs_id
                    WHERE project2geneset.pj_id=%(project_id)s
                ) AS gs
                -- join with publications (there should be 1 or 0 per geneset so
                -- this will not generate extra rows)
                LEFT OUTER JOIN
                publication ON gs.pub_id = publication.pub_id
            WHERE
                -- security check: make sure the authenticated user has the
                -- right to view the geneset
                geneset_is_readable(%(auth_user_id)s, gs.gs_id);
            ''',
            {
                'project_id': project_id,
                'auth_user_id': auth_user_id,
            }
        )
        return [Geneset(row_dict) for row_dict in dictify_cursor(cursor)]


def insert_geneset_to_project(project_id, geneset_id):
    with PooledCursor() as cursor:
        cursor.execute(
            '''
            INSERT INTO project2geneset (pj_id, gs_id, modified_on)
            VALUES (%s, %s, now())
            RETURNING pj_id;
            ''',
            (project_id, geneset_id,)
        )
        cursor.connection.commit()

        # return the primary ID for the insert that we just performed
        return cursor.fetchone()[0]


# this function creates a project with no genesets associated with it
# if a guest is creating a project, pass in -1 for user_id
# NOT TESTED
def create_project(project_name, user_id):
    if user_id > 0:
        with PooledCursor() as cursor:
            cursor.execute(
                '''
                INSERT INTO project (pj_name, usr_id, pj_created)
                VALUES (%s, %s, now())
                RETURNING pj_id;
                ''',
                (project_name, user_id,)
            )
            cursor.connection.commit()
            # return the primary ID for the insert that we just performed
            return cursor.fetchone()[0]
    else:
        with PooledCursor() as cursor:
            cursor.execute(
                '''
                INSERT INTO project (pj_name, pj_created)
                VALUES (%s, now())
                RETURNING pj_id;
                ''',
                (project_name,)
            )
            cursor.connection.commit()
            # return the primary ID for the insert that we just performed
            return cursor.fetchone()[0]


def get_all_projects(usr_id):
    """
    returns all projects associated with the given user ID
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

        return [Project(d) for d in dictify_cursor(cursor)]


# Begin group block, Getting specific groups for a user, and creating/modifying them

def get_all_owned_groups(usr_id):
    """
    returns all owned groups of the given user ID
    """
    with PooledCursor() as cursor:
        cursor.execute(
            '''SELECT * FROM production.grp WHERE grp_id in (SELECT grp_id
			   FROM production.usr2grp
			   WHERE usr_id = %s and u2g_privileges = 1)''', (usr_id,)
        )

        return list(dictify_cursor(cursor))


def get_all_member_groups(usr_id):
    """
    returns all groups the given user ID is a member of
    """
    with PooledCursor() as cursor:
        cursor.execute(
            '''SELECT * FROM production.grp WHERE grp_id in (SELECT grp_id
			   FROM production.usr2grp
			   WHERE usr_id = %s and (u2g_privileges = 0 or u2g_privileges IS NULL))''', (usr_id,)
        )

        return list(dictify_cursor(cursor))


# group_name is a string provided by user, group_private should be either true or false
# true, the group is private. false the group is public.
# The user_id will be initialized as the owner of the group   

def create_group(group_name, group_private, user_id):
    if (group_private):
        with PooledCursor() as cursor:
            cursor.execute(
                '''
                INSERT INTO production.grp (grp_name, grp_private)
                VALUES (%s, %s)
                RETURNING grp_id;
                ''',
                (group_name, 't',)
            )
            cursor.connection.commit()
            # return the primary ID for the insert that we just performed
            grp_id = cursor.fetchone()[0]
    else:
        with PooledCursor() as cursor:
            cursor.execute(
                '''
                INSERT INTO production.grp (grp_name, grp_private)
                VALUES (%s, %s)
                RETURNING grp_id;
                ''',
                (group_name, 'f',)
            )
            cursor.connection.commit()
            # return the primary ID for the insert that we just performed
            grp_id = cursor.fetchone()[0]

    with PooledCursor() as cursor:
        cursor.execute(
            '''
            INSERT INTO production.usr2grp (grp_id, usr_id, u2g_privileges)
            VALUES (%s, %s, 1 );
            ''',
            (grp_id, user_id, )
        )
        cursor.connection.commit()

    return grp_id


# adds a user to the group specified.
# permision should be passed as 0 if it is a normal user
# permision should be passed as 1 if it is an admin
# permision is defaulted to 0			        
def add_user_to_group(group_name, owner_id, usr_email, permission=0):
    with PooledCursor() as cursor:
        cursor.execute(
            '''
            INSERT INTO production.usr2grp (grp_id, usr_id, u2g_privileges)
            VALUES ((SELECT grp_id
                     FROM production.usr2grp
                     WHERE grp_id = (SELECT grp_id FROM production.grp WHERE grp_name = %s)
                     AND usr_id = %s AND u2g_privileges = 1),
                    (SELECT usr_id
                     FROM production.usr
                     WHERE usr_email = %s LIMIT 1), %s)
            RETURNING grp_id;
            ''',
            (group_name, owner_id, usr_email, permission,)
        )
        cursor.connection.commit()
        # return the primary ID for the insert that we just performed
        grp_id = cursor.fetchone()[0]

    return grp_id


def remove_user_from_group(group_name, owner_id, usr_email):
    with PooledCursor() as cursor:
        cursor.execute(
            '''
            DELETE FROM production.usr2grp
            WHERE (grp_id = (SELECT grp_id
                            FROM production.usr2grp
                            WHERE grp_id = (SELECT grp_id FROM production.grp WHERE grp_name = %s)
                            AND usr_id = %s AND u2g_Privileges = 1)
                            OR grp_id = (SELECT grp_id
                                         FROM production.usr2grp
                                         WHERE grp_id = (SELECT grp_id FROM production.grp WHERE grp_name = %s) AND usr_id = (SELECT usr_id
                                                                         FROM production.usr
                                                                         WHERE usr_email = %s LIMIT 1)))
                 AND usr_id = (SELECT usr_id
                               FROM production.usr
                               WHERE usr_email = %s LIMIT 1);

            ''',
            (group_name, owner_id, group_name, usr_email, usr_email,)
        )
        cursor.connection.commit()
    # return the primary ID for the insert that we just performed
    return


# switches group active field between false and true, and true and false
def toggle_group_active(group_id, user_id):
    with PooledCursor() as cursor:
        cursor.execute(
            '''
            UPDATE production.usr2grp
            SET u2g_active = not u2gactive
            WHERE grp_id = %s and usr_id = %s;
            ''',
            (group_id, user_id,)
        )
        cursor.connection.commit()
        return

# Be Careful with this fucntion
# Only let owners of groups call this function
def delete_group(group_name, owner_id):
    with PooledCursor() as cursor:
        cursor.execute(
            '''
            DELETE FROM production.usr2grp
            WHERE grp_id = (SELECT grp_id
                            FROM production.usr2grp
                            WHERE grp_id = (SELECT grp_id FROM production.grp WHERE grp_name = %s) AND  usr_id = %s AND u2g_privileges = 1)
            RETURNING grp_id;
            ''',
            (group_name, owner_id,)
        )
        cursor.connection.commit()
    with PooledCursor() as cursor:
        cursor.execute(
            '''
            DELETE FROM production.grp
            WHERE grp_name = %s;
            ''',
            (group_name,)
        )
        cursor.connection.commit()
        return


# End group block

def get_all_species():
    """
    returns an ordered mapping from species ID to species name for all available species
    """
    with PooledCursor() as cursor:
        cursor.execute('''SELECT sp_id, sp_name FROM species  ORDER BY sp_id;''')
        return OrderedDict(cursor)

def get_all_publications(gs_id):
    """
    :param gs_id:
    :return: All information in the publication table if pub_id is attached to publication table
    """
    with PooledCursor() as cursor:
        cursor.execute('''SELECT * FROM publication p, geneset g WHERE p.pub_id=g.pub_id AND g.gs_id=%s''', (gs_id,))
        publications = [Publication(row_dict) for row_dict in dictify_cursor(cursor)]
        return publications[0] if len(publications) == 1 else None

def get_all_attributions():
    """
    returns an ordered mapping from attribution ID to attribution name for all available attributions

    TODO remark - there is an added statement to remove null attributions. At the time of writing, this would be
    attribution id 1. It has an abbreviation that is null, and description 'none'. However, there are no genesets with
    gs_attribution set to 1. They are either NULL or 0.
    """
    with PooledCursor() as cursor:
        # TODO resolve issue of the null at_abbrev. For now this is truncated for the search feature, but could be
        #enabled in the future.
        cursor.execute('''select at_id, at_abbrev from attribution WHERE at_abbrev IS NOT NULL ORDER BY at_id;''')
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


# *************************************

def delete_geneset_by_gsid(rargs):
    usr_id = rargs.get('user_id', type=int)
    gs_id = rargs.get('gs_id', type=int)
    with PooledCursor() as cursor:
        cursor.execute(
            '''
            UPDATE geneset
            SET gs_status = 'deleted'
            WHERE gs_id =%s AND usr_id =%s;
            ''',
            (gs_id, usr_id,)
        )
        cursor.connection.commit()
        return

def delete_geneset_value_by_id(rargs):
    gs_id = rargs.get('gsid', type=int)
    gene_id = rargs.get('id', type=str)
    with PooledCursor() as cursor:
        cursor.execute('''DELETE from temp_geneset_value WHERE gs_id=%s AND src_id =%s''', (gs_id, gene_id,))
        print cursor.statusmessage
        cursor.connection.commit()
        return

def user_is_owner(usr_id, gs_id):
    with PooledCursor() as cursor:
        cursor.execute('''SELECT COUNT(gs_id) FROM geneset WHERE usr_id=%s AND gs_id=%s''', (usr_id, gs_id))
        return cursor.fetchone()[0]

def edit_geneset_id_value_by_id(rargs):
    gs_id = rargs.get('gsid', type=int)
    gene_id = rargs.get('id', type=str)
    gene_old = rargs.get('idold', type=str)
    value = rargs.get('value', type=float)
    user_id = flask.session['user_id']
    if (get_user(user_id).is_admin != 'False' or get_user(user_id).is_curator != 'False') or user_is_owner(user_id, gs_id) != 0:
        with PooledCursor() as cursor:
            cursor.execute('''UPDATE temp_geneset_value SET src_id=%s, src_value=%s WHERE gs_id=%s AND src_id=%s''',
                           (gene_id, value, gs_id, gene_old,))
            cursor.connection.commit()
            return

def add_geneset_gene_to_temp(rargs):
    gs_id = rargs.get('gsid', type=int)
    gene_id = rargs.get('id', type=str)
    value = rargs.get('value', type=float)
    user_id = flask.session['user_id']
    if (get_user(user_id).is_admin != 'False' or get_user(user_id).is_curator != 'False') or user_is_owner(user_id, gs_id) != 0:
        with PooledCursor() as cursor:
            ##Check to see if ode_gene_id exists
            cursor.execute('''SELECT g.ode_gene_id FROM gene g, geneset gs WHERE gs.gs_id=%s AND gs.sp_id=g.sp_id AND
                              g.ode_ref_id=%s''', (gs_id, gene_id,))
            if cursor.rowcount == 0:
                return {'error': 'Identifier Not Found'}
            else:
                ode_gene_id = cursor.fetchone()[0]
            ##Check to see if the src_id already exists
            cursor.execute('''SELECT src_id FROM temp_geneset_value WHERE gs_id=%s AND src_id=%s''', (gs_id, gene_id,))
            if cursor.rowcount != 0:
                return {'error': 'The Source Identifier already exists for this geneset'}
            ##Insert into temp table
            cursor.execute('''INSERT INTO temp_geneset_value (gs_id, ode_gene_id, src_value, src_id)
                              VALUES (%s, %s, %s, %s)''', (gs_id, ode_gene_id, value, gene_id,))
            cursor.connection.commit()
            return {'error': 'None'}

def cancel_geneset_edit_by_id(rargs):
    gs_id = rargs.get('gsid', type=int)
    user_id = rargs.get('user_id', type=int)
    if (get_user(user_id).is_admin != 'False' or get_user(user_id).is_curator != 'False') or user_is_owner(user_id, gs_id) != 0:
        with PooledCursor() as cursor:
            cursor.execute('''DELETE FROM temp_geneset_value WHERE gs_id=%s''', (gs_id,))
            cursor.execute('''DELETE FROM temp_geneset_meta WHERE gs_id=%s''', (gs_id,))
            cursor.connection.commit()
            return gs_id

def updategeneset(usr_id, form):
    '''
    This function updates both some of the metadata in the geneset table and the publication table. If geneset metadata
    is not null, it will update everything. If the pub_pubmed is not null, it will insert all publication information if
    it does not exist. If pub_pubmed is null, and any other pubmed record is populated it will update those records. This
    function does not check a mismatch between pubmed info and pub_pubmed id. Both are done in an explicit transaction.
    :param usr_id:
    :param form:
    :return: success is 'True' or 'Error Msg'
    '''
    gs_id = int((form["gs_id"]).strip()) if form["gs_id"] else None
    gs_abbreviation = (form["gs_abbreviation"]).strip() if form["gs_abbreviation"] else None
    gs_description = (form["gs_description"]).strip() if form["gs_description"] else None
    gs_name = (form["gs_name"]).strip() if form["gs_name"] else None
    pub_authors = (form["pub_authors"]).strip() if form["pub_authors"] else None
    pub_title = (form["pub_title"]).strip() if form["pub_title"] else None
    pub_abstract = (form["pub_abstract"]).strip() if form["pub_abstract"] else None
    pub_journal = (form["pub_journal"]).strip() if form["pub_journal"] else None
    pub_volume = (form["pub_volume"]).strip() if form["pub_volume"] else None
    pub_pages = (form["pub_pages"]).strip() if form["pub_pages"] else None
    pub_month = (form["pub_month"]).strip() if form["pub_month"] else None
    pub_year = (form["pub_year"]).strip() if form["pub_year"] else None
    pub_pubmed = (form["pub_pubmed"]).strip() if form["pub_pubmed"] else None
    pub_id = (form["pmid"]).strip() if form["pmid"] else None
    pmid = None
    if (get_user(usr_id).is_admin == 'False' and get_user(usr_id).is_curator == 'False') or user_is_owner(usr_id, gs_id) != 1:
        return 'You do not have permission to update this geneset'
    if gs_abbreviation is None or gs_description is None or gs_name is None:
        return 'Required Field is not provided'
    # if a pubmed id is submitted, insert into the db if it does not exist. Then return the pub_id.
    if pub_pubmed is not None:
        with PooledCursor() as cursor:
            cursor.execute('''INSERT INTO publication (pub_authors, pub_title, pub_abstract, pub_journal,
                                    pub_volume, pub_pages, pub_month, pub_year, pub_pubmed)
                                    SELECT %s, %s, %s, %s, %s, %s, %s, %s, %s
                                    WHERE NOT EXISTS
                                    (SELECT 1 FROM publication WHERE pub_pubmed=%s)''', (pub_authors, pub_title,
                                    pub_abstract, pub_journal, pub_volume, pub_pages, pub_month, pub_year, pub_pubmed, pub_pubmed,))
            cursor.connection.commit()
        with PooledCursor() as cursor:
            cursor.execute('''SELECT pub_id FROM publication WHERE pub_pubmed=%s''', (pub_pubmed,))
            pmid = cursor.fetchone()[0]

    # if pubmed id is none and everything else is blank, then pub_id = None
    elif pub_authors is None and pub_title is None and pub_abstract is None and pub_journal is None and pub_volume is None and pub_pages is None and pub_month is None and pub_year is None:
        pmid = None

    # if pubmed id is none and something else is not, then use the pmid to update the appropriate information
    else:
        if pub_id is not None:
            with PooledCursor() as cursor:
                cursor.execute('''UPDATE publication SET pub_title=%s, pub_abstract=%s, pub_journal=%s, pub_volume=%s,
                                  pub_pages=%s, pub_month=%s, pub_year=%s, pub_pubmed=%s FROM geneset WHERE publication.pub_id=geneset.pub_id AND
                                  geneset.gs_id=%s''', (pub_title, pub_abstract, pub_journal, pub_volume, pub_pages, pub_month,
                                                        pub_year, pub_pubmed, gs_id,))
                cursor.connection.commit()
            pmid = pub_id
        # if there is no pmid associated, we need to add it and return the pub_id
        else:
            with PooledCursor() as cursor:
                cursor.execute('''INSERT INTO publication (pub_authors, pub_title, pub_abstract, pub_journal, pub_volume, pub_pages, pub_month, pub_year) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)''',
                                    (pub_authors, pub_title, pub_abstract, pub_journal, pub_volume, pub_pages, pub_month, pub_year,))
                cursor.connection.commit()
            with PooledCursor() as cursor:
                cursor.execute('''SELECT currval(%s)''', ("publication_pub_id_seq",))
                pmid = cursor.fetchone()[0]
    # update geneset with changes
    with PooledCursor() as cursor:
        sql = cursor.mogrify('''UPDATE geneset SET pub_id=%s, gs_name=(%s), gs_abbreviation=(%s), gs_description=(%s)
                                WHERE gs_id=%s''', (pmid, gs_name, gs_abbreviation, gs_description, gs_id,))
        print sql
        cursor.execute(sql)
        cursor.connection.commit()
    return 'True'

def add_project(usr_id, pj_name):
    with PooledCursor() as cursor:
        cursor.execute(
            ''' INSERT INTO production.project
                (usr_id, pj_name) VALUES (%s, %s)
                RETURNING pj_id;
                ''', (usr_id, pj_name,))
        cursor.connection.commit()
    return cursor.fetchone()

def add_geneset2project(pj_id, gs_id):
    gs_id = gs_id[2:]
    with PooledCursor() as cursor:
        cursor.execute(
            ''' INSERT INTO project2geneset
                (pj_id, gs_id) SELECT %s, %s
                WHERE NOT EXISTS
                (SELECT pj_id, gs_id FROM project2geneset WHERE pj_id=%s AND gs_id=%s)
              ''', (pj_id, gs_id, pj_id, gs_id)
        )
        cursor.connection.commit()
    return

def add_genesets_to_projects(rargs):
    usr_id = rargs.get('user_id', type=int)
    npn = rargs.get('npn', type=str)
    gs_ids = rargs.get('gs_id', type=str)
    checked = json.loads(rargs.get('option', type=str))
    if (gs_ids is not None):
        if (npn is not None):
            new_pj_id = add_project(usr_id, npn)
            checked.append(new_pj_id)
        gs_id = gs_ids.split(',')
        for pj_id in checked:
           for g in gs_id:
               g = g.strip()
               add_geneset2project(pj_id, g)
    return

def delete_results_by_runhash(rargs):
    # ToDO: Remove results from RESULTS Dir
    user_id = rargs.get('user_id', type=int)
    runHash = rargs.get('runHash', type=str)
    with PooledCursor() as cursor:
        cursor.execute(
            '''
            DELETE FROM result
            WHERE usr_id=%s AND res_runhash=%s;
            ''',
            (user_id, runHash,)
        )
        cursor.connection.commit()
        return

def edit_results_by_runhash(rargs):
    user_id = rargs.get('user_id', type=int)
    runHash = rargs.get('runHash', type=str)
    editName = rargs.get('editName', type=str)
    with PooledCursor() as cursor:
        cursor.execute(
            '''
            UPDATE result SET res_name=%s
            WHERE usr_id=%s AND res_runhash=%s;
            ''',
            (editName, user_id, runHash,)
        )
        cursor.connection.commit()
        return


def get_server_side_genesets(rargs):
    user_id = rargs.get('user_id', type=int)

    select_columns = ['', 'sp_id', 'cur_id', 'gs_attribution', 'gs_count', 'gs_id', 'gs_name']
    select_clause = """SELECT gs_status, sp_id, cur_id, gs_attribution, gs_count, gs_id, gs_name, gs_abbreviation, gs_description,
                    to_char(gs_created, '%s'), to_char(gs_updated, '%s') FROM geneset WHERE gs_status NOT LIKE 'de%%' AND usr_id=%s""" % \
                    ('YYYY-MM-DD', 'YYYY-MM-DD', user_id,)
    source_columns = ['cast(sp_id as text)', 'cast(cur_id as text)', 'cast(gs_attribution as text)',
                      'cast(gs_count as text)',
                      'cast(gs_id as text)', 'cast(gs_name as text)']

    # Paging
    iDisplayStart = rargs.get('start', type=int)
    iDisplayLength = rargs.get('length', type=int)
    limit_clause = 'LIMIT %d OFFSET %d' % (iDisplayLength, iDisplayStart) \
        if (iDisplayStart is not None and iDisplayLength != -1) \
        else ''

    # searching
    search_value = rargs.get('search[value]')
    search_clauses = []
    if search_value:
        for i in range(len(source_columns)):
            search_clauses.append('''%s LIKE '%%%s%%' ''' % (source_columns[i], search_value))
        search_clause = 'OR '.join(search_clauses)
    else:
        search_clause = ''

    # Sorting
    sorting_col = select_columns[rargs.get('order[0][column]', type=int)]
    sorting_direction = rargs.get('order[0][dir]', type=str)
    sort_dir = 'ASC NULLS LAST' \
        if sorting_direction == 'asc' \
        else 'DESC NULLS LAST'
    order_clause = 'ORDER BY %s %s' % (sorting_col, sort_dir) if sorting_col else ''

    # joins all clauses together as a query
    where_clause = ' AND %s' % search_clause if search_clause else ''
    # print where_clause
    sql = ' '.join([select_clause,
                    where_clause,
                    order_clause,
                    limit_clause]) + ';'
    print sql

    with PooledCursor() as cursor:
        # cursor.execute(sql, ac_patterns + pc_patterns)
        cursor.execute(sql)
        things = cursor.fetchall()

        sEcho = rargs.get('sEcho', type=int)

        # Count of all values in table
        cursor.execute("SELECT COUNT(*) FROM geneset WHERE gs_status NOT LIKE 'de%%' AND usr_id = %d" % user_id)
        iTotalRecords = cursor.fetchone()[0]

        # Count of all values that satisfy WHERE clause
        iTotalDisplayRecords = iTotalRecords
        if where_clause:
            sql = ' '.join([select_clause, where_clause]) + ';'
            # cursor.execute(sql, ac_patterns + pc_patterns)
            cursor.execute(sql)
            iTotalDisplayRecords = cursor.rowcount

        response = {'sEcho': sEcho,
                    'iTotalRecords': iTotalRecords,
                    'iTotalDisplayRecords': iTotalDisplayRecords,
                    'aaData': things
        }

        return response


def get_server_side_results(rargs):
    user_id = rargs.get('user_id', type=int)

    select_columns = ['temp', 'res_name', 'res_created', 'res_description', 'res_id', 'res_runhash', 'res_duration']
    ## res_name doesn't exist in the result table...
    select_clause = """SELECT cast(to_char((select now() - res_created), 'DDD') as int) as temp, res_name,
                    to_char(res_created, '%s') as res_created, res_description, res_id, res_runhash,
                    to_char(age(res_completed, res_created), '%s') as res_duration FROM result
                    WHERE usr_id=%s """ % ('YYYY-MM-DD', 'HH24:MI:SS', user_id,)
    source_columns = ['cast(res_id as text)', 'cast(res_runhash as text)', 'cast(res_created as text)',
                      'cast(res_name as text)', 'cast(res_description as text)']

    # Paging
    iDisplayStart = rargs.get('start', type=int)
    iDisplayLength = rargs.get('length', type=int)
    limit_clause = 'LIMIT %d OFFSET %d' % (iDisplayLength, iDisplayStart) \
        if (iDisplayStart is not None and iDisplayLength != -1) \
        else ''

    # searching
    search_value = rargs.get('search[value]')
    search_clauses = []
    if search_value:
        for i in range(len(source_columns)):
            search_clauses.append('''%s LIKE '%%%s%%' ''' % (source_columns[i], search_value))
        search_clause = 'OR '.join(search_clauses)
    else:
        search_clause = ''

    # Sorting
    sorting_col = select_columns[rargs.get('order[0][column]', type=int)]
    sorting_direction = rargs.get('order[0][dir]', type=str)
    sort_dir = 'ASC NULLS LAST' \
        if sorting_direction == 'asc' \
        else 'DESC NULLS LAST'
    order_clause = 'ORDER BY %s %s' % (sorting_col, sort_dir) if sorting_col else ''

    # joins all clauses together as a query
    where_clause = ' AND %s' % search_clause if search_clause else ''
    # print where_clause
    sql = ' '.join([select_clause,
                    where_clause,
                    order_clause,
                    limit_clause]) + ';'
    print sql

    with PooledCursor() as cursor:
        # cursor.execute(sql, ac_patterns + pc_patterns)
        cursor.execute(sql)
        things = cursor.fetchall()

        sEcho = rargs.get('sEcho', type=int)

        # Count of all values in table
        cursor.execute('SELECT COUNT(*) FROM result WHERE usr_id = %d' % user_id)
        iTotalRecords = cursor.fetchone()[0]

        # Count of all values that satisfy WHERE clause
        iTotalDisplayRecords = iTotalRecords
        if where_clause:
            sql = ' '.join([select_clause, where_clause]) + ';'
            # cursor.execute(sql, ac_patterns + pc_patterns)
            cursor.execute(sql)
            iTotalDisplayRecords = cursor.rowcount

        response = {'sEcho': sEcho,
                    'iTotalRecords': iTotalRecords,
                    'iTotalDisplayRecords': iTotalDisplayRecords,
                    'aaData': things
        }

        return response


def get_server_side(rargs):
    source_table = rargs.get('table', type=str)
    user_id = rargs.get('user_id', type=int)
    source_columns = []
    select_columns = []

    print source_table

    i = 0
    temp = rargs.get('columns[%d][name]' % i)
    while temp is not None:
        col_name = 'cast(' + temp + ' as text)'
        source_columns.append(col_name)
        select_columns.append(temp)
        i = i + 1
        temp = rargs.get('columns[%d][name]' % i)

    # select and from clause creation
    select_clause = 'SELECT %s ' % ','.join(select_columns)
    from_clause = 'FROM %s' % source_table


    # Paging
    iDisplayStart = rargs.get('start', type=int)
    iDisplayLength = rargs.get('length', type=int)
    limit_clause = 'LIMIT %d OFFSET %d' % (iDisplayLength, iDisplayStart) \
        if (iDisplayStart is not None and iDisplayLength != -1) \
        else ''

    #searching
    search_value = rargs.get('search[value]')
    search_clauses = []
    if search_value:
        for i in range(len(source_columns)):
            search_clauses.append('''%s LIKE '%%%s%%' ''' % (source_columns[i], search_value))
        search_clause = 'OR '.join(search_clauses)
        # if source_table == 'production.result':
        #     search_clause += ' AND usr_id = %d ' % user_id
    else:
        # if source_table == 'production.result':
        #     search_clause = "usr_id = %d " % user_id
        # else:
        search_clause = ''


    # Sorting
    sorting_col = select_columns[rargs.get('order[0][column]', type=int)]
    sorting_direction = rargs.get('order[0][dir]', type=str)
    sort_dir = 'ASC NULLS LAST' \
        if sorting_direction == 'asc' \
        else 'DESC NULLS LAST'
    order_clause = 'ORDER BY %s %s' % (sorting_col, sort_dir) if sorting_col else ''

    #joins all clauses together as a query
    where_clause = 'WHERE %s' % search_clause if search_clause else ''
    #print where_clause
    sql = ' '.join([select_clause,
                    from_clause,
                    where_clause,
                    order_clause,
                    limit_clause]) + ';'
    print sql

    with PooledCursor() as cursor:
        #cursor.execute(sql, ac_patterns + pc_patterns)
        cursor.execute(sql)
        things = cursor.fetchall()

        sEcho = rargs.get('sEcho', type=int)

        # Count of all values in table
        cursor.execute(' '.join(['SELECT COUNT(*)', from_clause]) + ';')
        iTotalRecords = cursor.fetchone()[0]

        # Count of all values that satisfy WHERE clause
        iTotalDisplayRecords = iTotalRecords
        if where_clause:
            sql = ' '.join([select_clause, from_clause, where_clause]) + ';'
            #cursor.execute(sql, ac_patterns + pc_patterns)
            cursor.execute(sql)
            iTotalDisplayRecords = cursor.rowcount

        response = {'sEcho': sEcho,
                    'iTotalRecords': iTotalRecords,
                    'iTotalDisplayRecords': iTotalDisplayRecords,
                    'aaData': things
        }

        return response


def get_all_columns(table):
    sql = '''SELECT column_name FROM information_schema.columns WHERE table_name='%s'AND table_schema='%s';''' % (
        table.split(".")[1], table.split(".")[0])
    try:
        with PooledCursor() as cursor:
            cursor.execute(sql)
            return list(dictify_cursor(cursor))
    except Exception, e:
        return str(e)


def get_primary_keys(table):
    sql = '''SELECT pg_attribute.attname FROM pg_index, pg_class, pg_attribute WHERE pg_class.oid = '%s'::regclass AND indrelid = pg_class.oid AND pg_attribute.attrelid = pg_class.oid AND pg_attribute.attnum = any(pg_index.indkey) AND indisprimary;''' % (
        table)
    try:
        with PooledCursor() as cursor:
            cursor.execute(sql)
            return list(dictify_cursor(cursor))
    except Exception, e:
        return str(e)


# get all columns for a table that aren't auto increment and can't be null
def get_required_columns(table):
    sql = '''SELECT column_name FROM information_schema.columns WHERE table_name='%s'AND table_schema='%s' AND is_nullable='NO' AND column_name NOT IN (SELECT column_name FROM information_schema.columns WHERE table_name = '%s' AND column_default LIKE '%s' AND table_schema='%s');''' % (
        table.split(".")[1], table.split(".")[0], table.split(".")[1], "%nextval(%", table.split(".")[0])
    try:
        with PooledCursor() as cursor:
            cursor.execute(sql)
            return list(dictify_cursor(cursor))
    except Exception, e:
        return str(e)


#gets all columns for a table that aren't auto increment and can be null
def get_nullable_columns(table):
    sql = '''SELECT column_name FROM information_schema.columns WHERE table_name='%s' AND table_schema='%s' AND is_nullable='YES' AND column_name NOT IN (SELECT column_name FROM information_schema.columns WHERE table_name = '%s' AND column_default LIKE '%s' AND table_schema='%s');''' % (
        table.split(".")[1], table.split(".")[0], table.split(".")[1], "%nextval(%", table.split(".")[0])
    print sql
    try:
        with PooledCursor() as cursor:
            cursor.execute(sql)
            return list(dictify_cursor(cursor))
    except Exception, e:
        return str(e)


#gets values for columns of specified key(s)
def admin_get_data(table, cols, keys):
    sql = '''SELECT %s FROM %s WHERE %s;''' % (','.join(cols), table, ' AND '.join(keys))
    #print sql
    try:
        with PooledCursor() as cursor:
            cursor.execute(sql)
            return list(dictify_cursor(cursor))
    except Exception, e:
        return str(e)


#removes item from db that has specified primary key(s)
def admin_delete(args, keys):
    table = args.get('table', type=str)

    if len(keys) <= 0:
        return "Error: No primary key constraints set."

    sql = '''DELETE FROM %s WHERE %s;''' % (table, ' AND '.join(keys))

    print sql
    try:
        with PooledCursor() as cursor:
            cursor.execute(sql)
            cursor.connection.commit()
            return "Deletion Successful"
    except Exception, e:
        return str(e)


#updates columns for specified key(s)
def admin_set_edit(args, keys):
    table = args.get('table', type=str)

    if len(keys) <= 0:
        return "Error: No primary key constraints set"

    colmerge = []
    colkeys = args.keys()
    for key in colkeys:
        if key != 'table':
            value = args.get(key, type=str)
            if value and value != "None":
                colmerge.append(key + '=\'' + value.replace("'", "\'") + '\'')

    sql = '''UPDATE %s SET %s WHERE %s;''' % (table, ','.join(colmerge), ' AND '.join(keys))

    print sql
    try:
        with PooledCursor() as cursor:
            cursor.execute(sql)
            cursor.connection.commit()
            return "Edit Successful"
    except Exception, e:
        return str(e)


#adds item into db for specified table
def admin_add(args):
    table = args.get('table', type=str)
    source_columns = []
    column_values = []

    keys = args.keys()

    #sql creation   	   
    for key in keys:
        if key != 'table':
            value = args.get(key, type=str)
            if value:
                source_columns.append(key)
                column_values.append(value)

    if len(source_columns) <= 0:
        return "Nothing to insert"
    sql = 'INSERT INTO %s (%s) VALUES (\'%s\');' % (table, ','.join(source_columns), '\',\''.join(column_values))
    print sql
    try:
        with PooledCursor() as cursor:
            cursor.execute(sql)
            cursor.connection.commit()
            return "Add Successful"
    except Exception, e:
        return str(e)


def genesets_per_tier(includeDeleted):
    if includeDeleted:
        sql1 = '''SELECT count(*) FROM production.geneset WHERE cur_id = 1;'''
        sql2 = '''SELECT count(*) FROM production.geneset WHERE cur_id = 2;'''
        sql3 = '''SELECT count(*) FROM production.geneset WHERE cur_id = 3;'''
        sql4 = '''SELECT count(*) FROM production.geneset WHERE cur_id = 4;'''
        sql5 = '''SELECT count(*) FROM production.geneset WHERE cur_id = 5;'''
    else:
        sql1 = '''SELECT count(*) FROM production.geneset WHERE gs_status NOT LIKE 'de%' AND cur_id = 1;'''
        sql2 = '''SELECT count(*) FROM production.geneset WHERE gs_status NOT LIKE 'de%' AND cur_id = 2;'''
        sql3 = '''SELECT count(*) FROM production.geneset WHERE gs_status NOT LIKE 'de%' AND cur_id = 3;'''
        sql4 = '''SELECT count(*) FROM production.geneset WHERE gs_status NOT LIKE 'de%' AND cur_id = 4;'''
        sql5 = '''SELECT count(*) FROM production.geneset WHERE gs_status NOT LIKE 'de%' AND cur_id = 5;'''

    try:
        with PooledCursor() as cursor:
            cursor.execute(sql1)
            one = cursor.fetchone()[0]
            cursor.execute(sql2)
            two = cursor.fetchone()[0]
            cursor.execute(sql3)
            three = cursor.fetchone()[0]
            cursor.execute(sql4)
            four = cursor.fetchone()[0]
            cursor.execute(sql5)
            five = cursor.fetchone()[0]
            response = OrderedDict([('Tier 1', one),
                                    ('Tier 2', two),
                                    ('Tier 3', three),
                                    ('Tier 4', four),
                                    ('Tier 5', five)
            ])
        return response
    except Exception, e:
        return str(e)


def genesets_per_species_per_tier(includeDeleted):
    if includeDeleted:
        sql1 = '''SELECT sp_id, count(*) FROM production.geneset WHERE cur_id = 1 GROUP BY sp_id ORDER BY sp_id;'''
        sql2 = '''SELECT sp_id, count(*) FROM production.geneset WHERE cur_id = 2 GROUP BY sp_id ORDER BY sp_id;'''
        sql3 = '''SELECT sp_id, count(*) FROM production.geneset WHERE cur_id = 3 GROUP BY sp_id ORDER BY sp_id;'''
        sql4 = '''SELECT sp_id, count(*) FROM production.geneset WHERE cur_id = 4 GROUP BY sp_id ORDER BY sp_id;'''
        sql5 = '''SELECT sp_id, count(*) FROM production.geneset WHERE cur_id = 5 GROUP BY sp_id ORDER BY sp_id;'''
    else:
        sql1 = '''SELECT sp_id, count(*) FROM production.geneset WHERE gs_status NOT LIKE 'de%' AND cur_id = 1 GROUP BY sp_id ORDER BY sp_id;'''
        sql2 = '''SELECT sp_id, count(*) FROM production.geneset WHERE gs_status NOT LIKE 'de%' AND cur_id = 2 GROUP BY sp_id ORDER BY sp_id;'''
        sql3 = '''SELECT sp_id, count(*) FROM production.geneset WHERE gs_status NOT LIKE 'de%' AND cur_id = 3 GROUP BY sp_id ORDER BY sp_id;'''
        sql4 = '''SELECT sp_id, count(*) FROM production.geneset WHERE gs_status NOT LIKE 'de%' AND cur_id = 4 GROUP BY sp_id ORDER BY sp_id;'''
        sql5 = '''SELECT sp_id, count(*) FROM production.geneset WHERE gs_status NOT LIKE 'de%' AND cur_id = 5 GROUP BY sp_id ORDER BY sp_id;'''

    #print sql1

    try:
        with PooledCursor() as cursor:
            cursor.execute(sql1)
            one = OrderedDict(cursor)
            cursor.execute(sql2)
            two = OrderedDict(cursor)
            cursor.execute(sql3)
            three = OrderedDict(cursor)
            cursor.execute(sql4)
            four = OrderedDict(cursor)
            cursor.execute(sql5)
            five = OrderedDict(cursor)
            response = OrderedDict([('Tier 1', one),
                                    ('Tier 2', two),
                                    ('Tier 3', three),
                                    ('Tier 4', four),
                                    ('Tier 5', five)
            ])
        return response
    except Exception, e:
        return str(e)


def get_species_name():
    try:
        with PooledCursor() as cursor:
            cursor.execute('''SELECT sp_id, sp_name FROM odestatic.species;''')
        return OrderedDict(cursor)
    except Exception, e:
        return str(e)


def get_species_id_by_name(sp_name):
    sp_name = sp_name.strip()
    with PooledCursor() as cursor:
        cursor.execute('''SELECT sp_id FROM species WHERE sp_name=%s''', (sp_name,))
        results = cursor.fetchone()[0]
        return results


def get_gdb_id_by_name(gdb_name):
    gdb_name = gdb_name.strip()
    print gdb_name
    with PooledCursor() as cursor:
        cursor.execute('''SELECT gdb_id FROM genedb WHERE gdb_shortname=%s''', (gdb_name,))
        if cursor.rowcount != 0:
            results = cursor.fetchone()[0]
            return -1 * results
        else:
            cursor.execute('''SELECT pf_id FROM platform WHERE pf_shortname=%s''', (gdb_name,))
            results = cursor.fetchone()[0]
            return results


def monthly_tool_stats():
    tools = [];
    with PooledCursor() as cursor:
        cursor.execute(
            '''SELECT DISTINCT res_tool FROM production.result WHERE res_created >= now() - interval '30 days';''')
    tools = list(dictify_cursor(cursor))

    try:
        with PooledCursor() as cursor:
            response = OrderedDict()
            for tool in tools:
                cursor.execute(
                    '''SELECT res_created, count(*) FROM production.result WHERE res_created >= now() - interval '30 days' AND res_tool=%s GROUP BY res_created ORDER BY res_created desc;''',
                    (tool['res_tool'],))
                response.update({tool['res_tool']: OrderedDict(cursor)})
        return response
    except Exception, e:
        return str(e)


def get_bimodal_threshold(gs_id):
    with PooledCursor() as cursor:
        cursor.execute('''SELECT gsv_value FROM geneset_value WHERE gs_id=%s GROUP BY gsv_value''', (gs_id,))
        bi_modal = 'True' if cursor.rowcount == 1 else 'False'
        return bi_modal


def user_tool_stats():
    try:
        with PooledCursor() as cursor:
            cursor.execute(
                '''SELECT usr_id, count(*) FROM production.result WHERE res_created >= now() - interval '6 months' GROUP BY usr_id ORDER BY count(*) desc limit 20;''')
        return OrderedDict(cursor)
    except Exception, e:
        return str(e)


def tool_stats_by_user(user_id):
    try:
        with PooledCursor() as cursor:
            cursor.execute('''SELECT res_description, res_started, age(res_completed,res_started) as res_duration
                          FROM production.result
                          WHERE res_created >= now() - interval '30 days' AND usr_id=%s
                          ORDER BY res_started desc;''', (user_id,))
        return list(dictify_cursor(cursor))
    except Exception, e:
        return str(e)


def currently_running_tools():
    try:
        with PooledCursor() as cursor:
            cursor.execute(
                '''SELECT res_id, usr_id, res_tool, res_status FROM production.result WHERE res_completed is NULL;''')
        return list(dictify_cursor(cursor))
    except Exception, e:
        return str(e)


def size_of_genesets():
    try:
        with PooledCursor() as cursor:
            cursor.execute(
                '''SELECT gs_id, gs_count FROM production.geneset WHERE gs_status not like 'de%' ORDER BY gs_count DESC limit 1000;''')
        return OrderedDict(cursor)
    except Exception, e:
        return str(e)


def avg_tool_times(keys, tool):
    sql = '''SELECT avg(res_completed - res_started) FROM production.result WHERE res_tool='%s' AND res_id=%s;''' % (
        tool, ' OR res_id='.join(str(v) for v in keys))
    #print sql
    try:
        with PooledCursor() as cursor:
            cursor.execute(sql)
        return cursor.fetchone()[0]
    except Exception, e:
        return 0


def avg_genes(keys):
    sql = '''SELECT avg(gs_count) FROM production.geneset WHERE gs_id=%s;''' % (' OR gs_id='.join(str(v) for v in keys))
    #print sql
    try:
        with PooledCursor() as cursor:
            cursor.execute(sql)
        return cursor.fetchone()[0]
    except Exception, e:
        return 0


def gs_in_tool_run():
    try:
        with PooledCursor() as cursor:
            cursor.execute(
                '''SELECT res_id, res_tool, gs_ids, res_completed FROM production.result WHERE res_completed IS NOT NULL ORDER BY res_completed DESC LIMIT 500;''')
        return list(dictify_cursor(cursor))
    except Exception, e:
        return str(e)


def tools():
    try:
        with PooledCursor() as cursor:
            cursor.execute('''SELECT DISTINCT res_tool FROM production.result;''')
        return list(dictify_cursor(cursor))
    except Exception, e:
        return str(e)


# New code for Tools, Next 5 functions Modify usr2gene for Emphasis
# Not tested fucntion, query tested; returns usr id of usr it was inserted for
def create_usr2gene(user_id, ode_gene_id):
    with PooledCursor() as cursor:
        cursor.execute(
            '''
            INSERT INTO extsrc.usr2gene (usr_id, ode_gene_id)
            VALUES (%s, %s)
            ''',
            (user_id, ode_gene_id,)
        )
        cursor.connection.commit()
        # return the primary ID for the insert that we just performed


# insert delete all  with usr id
def delete_usr2gene_by_user(user_id):
    with PooledCursor() as cursor:
        cursor.execute(
            '''DELETE FROM usr2gene WHERE usr_id=%s;''', (user_id,)
        )

        cursor.connection.commit()
        return


# insert delete specific gene_id with usr id
def delete_usr2gene_by_user_and_gene(user_id, ode_gene_id):
    with PooledCursor() as cursor:
        cursor.execute(
            '''DELETE FROM usr2gene WHERE usr_id=%s AND ode_gene_id=%s;''', (user_id, ode_gene_id,)
        )
        cursor.connection.commit()
        return


# Not tested fucntion, query tested; insert get all gene and species stuff from u2g, gene, and species
def get_gene_and_species_info_by_user(user_id):
    with PooledCursor() as cursor:
        cursor.execute(
            '''SELECT gene.*, species.* FROM (extsrc.gene INNER JOIN odestatic.species USING (sp_id))
              INNER JOIN usr2gene USING (ode_gene_id) WHERE gene.ode_pref and usr2gene.usr_id = (%s);''',
            (user_id,))
    return list(dictify_cursor(cursor))


# Not tested fucntion, query tested;gets all gene and species stuff from gene, and species
def get_gene_and_species_info(ode_ref_id):
    with PooledCursor() as cursor:
        cursor.execute(
            '''SELECT gene.*, species.* FROM extsrc.gene INNER JOIN odestatic.species USING (sp_id)
              WHERE lower(ode_ref_id)=lower(%s);''',
            (ode_ref_id,))
    return list(dictify_cursor(cursor))


# end block of Emphasis functions

#*************************************************************
class User:
    def __init__(self, usr_dict):
        self.user_id = usr_dict['usr_id']
        self.first_name = usr_dict['usr_first_name']
        self.last_name = usr_dict['usr_last_name']
        self.email = usr_dict['usr_email']
        self.prefs = usr_dict['usr_prefs']
        self.api_key = usr_dict['apikey']

        usr_admin = usr_dict['usr_admin']
        self.is_curator = usr_admin == 1
        self.is_admin = usr_admin == 2 or usr_admin == 3
        self.last_seen = usr_dict['usr_last_seen']
        self.creation_date = usr_dict['usr_created']
        self.ip_addr = usr_dict['ip_addr']

        self.__projects = None

    @property
    def projects(self):
        if self.__projects is None:
            self.__projects = get_all_projects(self.user_id)

        return self.__projects


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
        if self.user_id is not None:
            try:
                self.user = User(gs_dict)
            except KeyError:
                self.user = None
        else:
            self.user = None
        self.file_id = gs_dict['file_id']
        #self.name = gs_dict['gs_name'].decode('utf-8')
        self.name = gs_dict['gs_name']
        self.abbreviation = gs_dict['gs_abbreviation']
        self.pub_id = gs_dict['pub_id']
        if self.pub_id is not None:
            try:
                self.publication = Publication(gs_dict)
            except KeyError:
                self.publication = None
        else:
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

        # add two values for geneset

        # declare value caches for instance properties
        self.__ontological_associations = None
        self.__geneset_values = None

    @property
    def ontological_associations(self):
        if self.__ontological_associations is None:
            self.__ontological_associations = get_ontologies_for_geneset(self.geneset)
        return self.__ontological_associations

    @property
    def geneset_values(self):
        if self.__geneset_values is None:
            self.__geneset_values = get_geneset_values(self.geneset_id)
        return self.__geneset_values

class TempGeneset(Geneset):
    def __init__(self, gs_dict):
        Geneset.__init__(self, gs_dict)
        self.__temp_geneset_values = None

    @property
    def temp_geneset_values(self):
        if self.__temp_geneset_values is None:
            #self.__geneset_values = get_geneset_values(self.geneset_id)
            self.__temp_geneset_values = get_temp_geneset_values(self.geneset_id)
        return self.__temp_geneset_values

class SimGeneset(Geneset):
    def __init__(self, gs_dict):
        Geneset.__init__(self, gs_dict)
        self.jac_value = gs_dict['jac_value']
        self.gic_value = gs_dict['jac_value']

class Ontology:
    def __init__(self, ont_dict):
        self.ontology_id = ont_dict['ont_id']
        self.reference_id = ont_dict['ont_ref_id']
        self.name = ont_dict['ont_name']
        self.description = ont_dict['ont_description']
        self.children = ont_dict['ont_children']
        self.parents = ont_dict['ont_parents']
        self.ontdb_id = ont_dict['ontdb_id']


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
                '''SELECT * FROM usr WHERE usr_email=%(email)s AND usr_password=%(password_md5)s;''',
                {
                    'email': email,
                    'password_md5': password_md5.hexdigest(),
                }
            )
            users = [User(row_dict) for row_dict in dictify_cursor(cursor)]
            return users[0] if len(users) == 1 else None

## There's a similarly titled get_result_by_runhash, but it's API function.
def get_results_by_runhash(runhash):
    with PooledCursor() as cursor:
        cursor.execute(
            ''' SELECT row_to_json(row, true)
                FROM(	SELECT *
                        FROM production.result
                        WHERE res_runhash = %s
                    ) row; ''', (runhash,))
    return cursor.fetchall();

def get_user(user_id):
    """
    Looks up a User in the database
    :param user_id:     the user's ID
    :return:            the User matching the given ID or None if no such user is found
    """
    with PooledCursor() as cursor:
        cursor.execute('''SELECT * FROM usr WHERE usr_id=%s''', (user_id,))
        users = [User(row_dict) for row_dict in dictify_cursor(cursor)]
        return users[0] if len(users) == 1 else None


def get_user_byemail(user_email):
    """
    Looks up a User in the database
    :param user_email: the email a user entered
    :return: the User matching the given email or None if no such user is found
    """
    with PooledCursor() as cursor:
        cursor.execute('''SELECT * FROM usr WHERE usr_email=%s''', (user_email,))
        users = [User(row_dict) for row_dict in dictify_cursor(cursor)]
        return users[0] if len(users) == 1 else None


def register_user(user_first_name, user_last_name, user_email, user_password):
    """
    Insert a user to the db
    :param user_first_name: the user's first name, if not provided use "Guest" as default
    :param user_last_name:  the user's last name, if not provided use "User" as default
    :param user_email:      the user's email address, if not provided use "" as default
    :param user_password:   the user's password, if not provided use "" as default
    """
    with PooledCursor() as cursor:
        password_md5 = md5(user_password).hexdigest()
        cursor.execute(
            '''INSERT INTO usr (usr_first_name, usr_last_name, usr_email, usr_admin, usr_password)
                        VALUES (%(user_first_name)s, %(user_last_name)s, %(user_email)s, '0', %(user_password)s)''',
            {
                'user_first_name': user_first_name,
                'user_last_name': user_last_name,
                'user_email': user_email,
                'user_password': password_md5
            }
        )
        cursor.connection.commit()
        return get_user_byemail(user_email)


def reset_password(user_email):
    """
    Update a user password
    :param user_email:      the user's email address, if not provided use "" as default
    :param user_password:   the user's password, if not provided use "" as default
    """

    char_set = string.ascii_lowercase + string.ascii_uppercase + string.digits
    new_password = ''.join(random.sample(char_set, 8))
    with PooledCursor() as cursor:
        password_md5 = md5(new_password).hexdigest()
        cursor.execute(
            '''UPDATE usr
               SET usr_password = %s
               WHERE usr_email = %s''', (password_md5, user_email)
        )
        cursor.connection.commit()
    return new_password


def change_password(user_id, new_password):
    """
    Update a user password
    :param user_email:      the user's email address, if not provided use "" as default
    :param new_password_1:   the user's password, if not provided use "" as default
    :param new_password_2:   the user's password, if not provided use "" as default
    """
    with PooledCursor() as cursor:
        password_md5 = md5(new_password).hexdigest()
        cursor.execute(
            '''UPDATE usr
               SET usr_password = %s
               WHERE usr_id = %s''', (password_md5, user_id)
        )
        cursor.connection.commit()
    return


def get_geneset(geneset_id, user_id=None, temp=None):
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
            '''
            SELECT *
            FROM geneset LEFT OUTER JOIN publication ON geneset.pub_id = publication.pub_id
            WHERE gs_id=%(geneset_id)s AND geneset_is_readable(%(user_id)s, %(geneset_id)s);
            ''',
            {
                'geneset_id': geneset_id,
                'user_id': user_id,
            }
        )
        if temp is None:
            genesets = [Geneset(row_dict) for row_dict in dictify_cursor(cursor)]
        elif temp == 'temp':
            #genesets = [Geneset(row_dict) for row_dict in dictify_cursor(cursor)]
            genesets = [TempGeneset(row_dict) for row_dict in dictify_cursor(cursor)]
        return genesets[0] if len(genesets) == 1 else None

def get_similar_genesets(geneset_id, user_id):
    """
    Gets similar genesets if either the geneset is publicly visible or the user
    has permission to view it.
    :param geneset_id:  the geneset ID
    :param user_id:     the user ID that needs permission
    :return:            the Geneset corresponding to the given ID if the
                        user has read permission, with jac_value, None otherwise
    """

    # TODO not sure if we really need to convert to -1 here. The geneset_is_readable function may be able to handle None
    if user_id is 0:
        user_id = -1

    with PooledCursor() as cursor:
        #This SQL is a bit sketchy. The old GW code calls for a sorted list of jac and gic values
        #I have simplified to return the top 150 of left and right ode_gene_ids. Worst case all are from
        #either partition of the list. I will clean up duplicates in the application.
        cursor.execute(
            '''SELECT * FROM
                ((SELECT geneset.*, jac_value, gic_value FROM geneset, geneset_jaccard
                    WHERE gs_id=gs_id_right AND gs_id_left=%(geneset_id)s AND geneset_is_readable(%(user_id)s, %(geneset_id)s)
                    AND gs_status NOT LIKE 'de%%' ORDER BY jac_value DESC LIMIT 150) UNION
                (SELECT geneset.*, jac_value, gic_value FROM geneset, geneset_jaccard
                    WHERE gs_id=gs_id_left AND gs_id_right=%(geneset_id)s AND geneset_is_readable(%(user_id)s, %(geneset_id)s)
                    AND gs_status NOT LIKE 'de%%' ORDER BY jac_value DESC LIMIT 150)) as tmp ORDER BY jac_value DESC;
            ''',
            {
                'geneset_id': geneset_id,
                'user_id': user_id,
                'geneset_id': geneset_id,
                'geneset_id': geneset_id,
                'user_id': user_id,
                'geneset_id': geneset_id,
            }
        )
        simgc = [SimGeneset(row_dict) for row_dict in dictify_cursor(cursor)]
        return simgc

def compare_geneset_jac(gs_id1, gs_id2):
    """
    Compares two genesets together. returns 1 if they are > .95 similar
    :param gs_id1:
    :param gs_id2:
    :return:
    """
    if gs_id2 < gs_id1:
        gs1 = gs_id2
        gs2 = gs_id1
    else:
        gs1 = gs_id1
        gs2 = gs_id2
    with PooledCursor() as cursor:
        cursor.execute(
            '''SELECT jac_value FROM geneset_jaccard
              WHERE gs_id_left=%(gs_id1)s AND gs_id_right=%(gs_id2)s AND jac_value > 0.95;
              ''',
            {
                'gs_id1': gs1,
                'gs_id2': gs2,
            }
        )
    if cursor.fetchone():
        return 1
    else:
        return 0


def get_geneset_no_user(geneset_id):
    """
    Gets the Geneset regardless of whether the user has permission to view it
    :param geneset_id:  the geneset ID
    :param user_id:     the user ID that needs permission
    :return:            the Geneset corresponding to the given ID if the
                        user has read permission, None otherwise
    """

    with PooledCursor() as cursor:
        cursor.execute(
            '''
            SELECT *
            FROM geneset LEFT OUTER JOIN publication ON geneset.pub_id = publication.pub_id
            WHERE gs_id=%(geneset_id)s;
            ''',
            {
                'geneset_id': geneset_id,
            }
        )
        genesets = [Geneset(row_dict) for row_dict in dictify_cursor(cursor)]
        return genesets[0] if len(genesets) == 1 else None


def get_user_groups(usr_id):
    """
    Gets a list of groups that the user belongs to
    :param usr_id:  the user ID
    :return:        The list of groups that the user belongs to
    """

    with PooledCursor() as cursor:
        cursor.execute(
            '''
            SELECT grp_id
            FROM usr2grp
            WHERE usr_id=%(usr_id)s;
            ''',
            {
                'usr_id': usr_id,
            }
        )
        grp_ids = [row_dict['grp_id'] for row_dict in dictify_cursor(cursor)]
        return grp_ids


def get_group_users(grp_id):
    """
    Gets a list of users in a group
    :param usr_id:  the user ID
    :return:        The list of groups that the user belongs to
    """

    with PooledCursor() as cursor:
        cursor.execute(
            '''
            SELECT usr_id
            FROM usr2grp
            WHERE grp_id=%(grp_id)s;
            ''',
            {
                'grp_id': grp_id,
            }
        )
        usr_ids = [row_dict['usr_id'] for row_dict in dictify_cursor(cursor)]
        return usr_ids


def get_geneset_brief(geneset_id, user_id=None):
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
            '''
            SELECT geneset.cur_id, geneset.sp_id, geneset.attribution, geneset.gs_count, geneset.gs_status, geneset.gs_id, geneset.gs_name
            FROM geneset 
            WHERE gs_id=%(geneset_id)s AND geneset_is_readable(%(user_id)s, %(geneset_id)s);
            ''',
            {
                'geneset_id': geneset_id,
                'user_id': user_id,
            }
        )
        genesets = [Geneset(row_dict) for row_dict in dictify_cursor(cursor)]
        return genesets[0] if len(genesets) == 1 else None


def get_genesets_by_user_id(user_id):
    """
    Gets all Genesets owned by the specified user
    :param user_id:     the owning user ID
    :return:            the Genesetx corresponding to the given ID
    """

    # TODO not sure if we really need to convert to -1 here. The
    # geneset_is_readable function may be able to handle None
    #if user_id is None:
    #    user_id = -1

    with PooledCursor() as cursor:
        cursor.execute(
            '''
            SELECT *
            FROM production.geneset
            WHERE usr_id=%(user_id)s;
            ''',
            {
                'user_id': user_id,
            }
        )
        genesets = [Geneset(row_dict) for row_dict in dictify_cursor(cursor)]
        return genesets if len(genesets) > 0 else None


def get_ontologies_for_geneset(geneset_id):
    with PooledCursor() as cursor:
        cursor.execute(
            '''SELECT * FROM ontology NATURAL JOIN geneset_ontology WHERE gs_id=%s AND gso_ref_type<>'Blacklist';''',
            (geneset_id,))
        return [Ontology(row_dict) for row_dict in dictify_cursor(cursor)]


class GenesetValue:
    def __init__(self, gsv_dict):
        self.gs_id = gsv_dict['gs_id']
        self.ode_gene_id = gsv_dict['ode_gene_id']
        self.value = gsv_dict['gsv_value']
        self.hits = gsv_dict['gsv_hits']
        self.source_list = gsv_dict['gsv_source_list']
        self.value_list = gsv_dict['gsv_value_list']
        self.is_in_threshold = gsv_dict['gsv_in_threshold']
        self.date = gsv_dict['gsv_date']
        self.hom = list(set(gsv_dict['hom'])) #had to remove duplicates from list
        self.gene_rank = ((float(gsv_dict['gene_rank'])/0.15)*100)
        self.ode_ref = gsv_dict['ode_ref']
        self.gdb_id = gsv_dict['gdb_id']

class TempGenesetValue:
    def __init__(self, gsv_dict):
        self.gs_id = gsv_dict['gs_id']
        self.ode_gene_id = gsv_dict['ode_gene_id']
        self.value = gsv_dict['gsv_value']
        self.hits = gsv_dict['gsv_hits']
        self.source_list = gsv_dict['gsv_source_list']
        self.value_list = gsv_dict['gsv_value_list']
        self.is_in_threshold = gsv_dict['gsv_in_threshold']
        self.date = gsv_dict['gsv_date']

def get_temp_geneset_values(geneset_id):
    """
    This geneset value query has been augmented to return a list of sp_ids that can be used
    on the geneset information page.
    Also, augmented to add a session call for sorting
    :param geneset_id:
    :returns to geneset class.
    """
    with PooledCursor() as cursor:
        cursor.execute('''SELECT gs_id, ode_gene_id, avg(src_value) as gsv_value,
                                           count(ode_gene_id) as gsv_hits, array_accum(src_id) as gsv_source_list,
                                           array_accum(src_value) as gsv_value_list,'t' as gsv_in_threshold, now() as gsv_date
                                           FROM production.temp_geneset_value
                                           WHERE gs_id=%s GROUP BY gs_id, ode_gene_id ORDER BY ode_gene_id;''' % (geneset_id,))
        return [TempGenesetValue(gsv_dict) for gsv_dict in dictify_cursor(cursor)]

def get_all_geneset_values(gs_id):
    '''
    Generic function to get all geneset values geneset_value.gs_values
    :param geneset_id:
    :return:
    '''
    user_id = flask.session['user_id']
    geneset = get_geneset(gs_id, user_id)
    with PooledCursor() as cursor:
        if geneset.gene_id_type < 0:
            cursor.execute('''SELECT gv.gsv_value as gsv, g.ode_ref_id as ref FROM geneset_value gv, gene g, geneset gs WHERE
                              g.ode_pref='t' AND gv.gs_id=%s AND gs.gs_id=gv.gs_id AND gs.sp_id=g.sp_id AND
                              gv.ode_gene_id=g.ode_gene_id ORDER BY gv.gsv_value ASC''', (gs_id,))
        else:
             cursor.execute('''SELECT gv.gsv_value, g.ode_ref_id FROM geneset_value gv, gene g, geneset gs WHERE
                              gv.gs_id=%s AND gs.gs_id=gv.gs_id AND gs.sp_id=g.sp_id AND gv.ode_gene_id=g.ode_gene_id AND
                              g.ode_pref='t' ORDER BY gv.gsv_value ASC''', (gs_id,))
        return list(dictify_cursor(cursor)) if cursor.rowcount != 0 else None


def get_geneset_values(geneset_id):
    """
    This geneset value query has been augmented to return a list of sp_ids that can be used
    on the geneset information page.
    Also, augmented to add a session call for sorting
    :param geneset_id:
    :returns to geneset class.
    """
    s = ' ORDER BY a.gs_id ASC'
    if 'sort' in session:
        d = session['dir']
        if session['sort'] == 'value':
            s = ' ORDER BY a.gsv_value '+d
        elif session['sort'] == 'priority':
            s = ' ORDER BY a.gene_rank '+d
        elif session['sort'] == 'symbol':
            s = ' ORDER BY a.gsv_source_list '+d
        elif session['sort'] == 'alt':
            s = ' ORDER BY a.ode_ref '+d

    ode_ref = '1'
    if 'extsrc' in session:
        ode_ref = session['extsrc']
        print session['extsrc']


    with PooledCursor() as cursor:
        #cursor.execute('''SELECT * FROM geneset_value WHERE gs_id=%s;''', (geneset_id,))
        cursor.execute('''SELECT a.gs_id, a.ode_gene_id, a.gsv_value, a.gsv_hits, a.gsv_source_list, a.gsv_value_list,
          a.gsv_in_threshold, a.gsv_date, a.hom, a.gene_rank, a.ode_ref, a.gdb_id
          FROM
            (SELECT gsv.*, array_agg(h.sp_id) OVER (partition BY gsv.ode_gene_id, g.gdb_id) AS hom, gi.gene_rank,
              array_agg(g.ode_ref_id) OVER (partition BY g.ode_gene_id) AS ode_ref,
              array_agg(g.gdb_id) OVER (partition BY g.ode_gene_id) AS gdb_id
              FROM homology h, homology i, geneset_value gsv, gene_info gi, gene g
              WHERE i.hom_source_id=h.hom_source_id AND i.ode_gene_id=gsv.ode_gene_id AND gsv.ode_gene_id=gi.ode_gene_id
              AND gsv.ode_gene_id=g.ode_gene_id
              AND (g.gdb_id=%s OR (g.gdb_id=7 AND g.ode_pref='t')) AND gsv.gs_id=%s)
              AS a GROUP BY a.gs_id, a.ode_gene_id, a.gsv_value, a.gsv_hits, a.gsv_source_list, a.gsv_value_list,
                a.gsv_in_threshold, a.gsv_date, a.hom, a.gene_rank, a.ode_ref, a.gdb_id'''+s, (ode_ref, geneset_id,))
        return [GenesetValue(gsv_dict) for gsv_dict in dictify_cursor(cursor)]


class ToolParam:
    def __init__(self, tool_param_dict):
        self.tool_classname = tool_param_dict['tool_classname']
        self.name = tool_param_dict['tp_name']
        self.description = tool_param_dict['tp_description']
        self.default = tool_param_dict['tp_default']
        self.options = json.loads(tool_param_dict['tp_options'])
        self.select_type = tool_param_dict['tp_seltype']
        self.is_visible = tool_param_dict['tp_visible']

    @property
    def label_name(self):
        """
        The name from the DB is prefixed by the owning tool's classname. This property
        strips that string off
        :return: the label friendly name
        """
        prefix = self.tool_classname + '_'
        if self.name.startswith(prefix):
            return self.name[len(prefix):]
        else:
            return self.name


def get_tool_params(tool_classname, only_visible=False):
    """
    Get tool parameters for the tool with the given classname
    :param tool_classname: identifies the tool that we're getting params for
    :param only_visible: if True only return parameters marked visible
    :return: the list of ToolParams
    """
    with PooledCursor() as cursor:
        if only_visible:
            cursor.execute(
                '''SELECT * FROM tool_param WHERE tool_classname=%s AND tp_visible ORDER BY tp_name;''',
                (tool_classname,))
        else:
            cursor.execute('''SELECT * FROM tool_param WHERE tool_classname=%s ORDER BY tp_name;''',
                           (tool_classname,))
        return [ToolParam(d) for d in dictify_cursor(cursor)]


class ToolConfig:
    def __init__(self, tool_dict):
        self.classname = tool_dict['tool_classname']
        self.name = tool_dict['tool_name']
        self.description = tool_dict['tool_description']
        self.requirements = [x.strip() for x in tool_dict['tool_requirements'].split(',')]
        self.is_active = tool_dict['tool_active'] == '1'
        self.sort_priority = tool_dict['tool_sort']
        self.__params = None

    @property
    def params(self):
        if self.__params is None:
            self.__params = OrderedDict(((tp.name, tp)
                                         for tp in get_tool_params(self.classname)))

        return self.__params


def get_tool(tool_classname):
    with PooledCursor() as cursor:
        cursor.execute('''SELECT * FROM tool WHERE tool_classname=%s;''', (tool_classname,))
        tools = [ToolConfig(tool_dict) for tool_dict in dictify_cursor(cursor)]

        return tools[0] if len(tools) == 1 else None


def get_active_tools():
    """
    Get all tools that are marked active in the DB
    :return: a list of active tools
    """
    with PooledCursor() as cursor:
        cursor.execute('''SELECT * FROM tool WHERE tool_active='1' ORDER BY tool_sort;''')
        return [ToolConfig(tool_dict) for tool_dict in dictify_cursor(cursor)]


def get_run_status(run_hash):
    """
    Finds the total number of runs queued up and the number queued up ahead of the give hash
    :param run_hash: we're finding out the queue position of this run
    :return: a tuple where the 1st element is the total number of runs queued and the
             2nd is the number of runs queued ahead of run_hash
    """

    with PooledCursor() as cursor:
        # finds the total number of runs waiting to run
        cursor.execute('''SELECT count(*) FROM result WHERE res_started IS NULL;''')
        total_queued = list(cursor)[0][0]

        # finds the number of runs ahead of us that are waiting to run
        cursor.execute(
            '''
            SELECT count(*)
            FROM
                result AS r1
                CROSS JOIN
                (SELECT * FROM result WHERE res_runhash=%(run_hash)s) as r2
                WHERE r1.res_started IS NULL AND r1.res_created<r2.res_created;
            ''')
        before_queued = list(cursor)[0][0]

        return total_queued, before_queued


def insert_result(usr_id, res_runhash, gs_ids, res_data, res_tool, res_description, res_status, res_api='f'):
    with PooledCursor() as cursor:
        ## res_api isn't part of the database (at least on crick), rather than
        ## screw up table structure, res_api is commented out for now
        #cursor.execute(
        #    '''
        #    INSERT INTO result (usr_id, res_runhash, gs_ids, res_data, res_tool, res_description, res_status, res_started, res_api)
        #    VALUES (%s, %s, %s, %s, %s, %s, %s, now(), %s)
        #    RETURNING res_id;
        #    ''',
        #    (usr_id, res_runhash, ','.join(gs_ids), res_data, res_tool, res_description, res_status, res_api)
        #)
        cursor.execute(
            '''
            INSERT INTO result (usr_id, res_runhash, gs_ids, res_data, res_tool, res_description, res_status, res_started)
            VALUES (%s, %s, %s, %s, %s, %s, %s, now())
            RETURNING res_id;
            ''',
            (usr_id, res_runhash, ','.join(gs_ids), res_data, res_tool, res_description, res_status)
        )
        cursor.connection.commit()

        # return the primary ID for the insert that we just performed
        return cursor.fetchone()[0]


def get_all_userids():
    with PooledCursor() as cursor:
        cursor.execute(
            '''SELECT usr_id, usr_email FROM production.usr limit 15;'''),
    return list(dictify_cursor(cursor))


def get_species_name_by_id(sp_id):
    """
    returns the species name given a valid species id
    """
    with PooledCursor() as cursor:
        cursor.execute('''SELECT sp_name FROM species WHERE sp_id=%s;''', (sp_id,))
        sp_name = cursor.fetchone()[0]
    return sp_name

def get_sp_id():
    """
    returns all species ids
    """
    with PooledCursor() as cursor:
        cursor.execute('''SELECT sp_id FROM species WHERE sp_id > 0 ORDER BY sp_id ASC;''')
        sp_id = list(dictify_cursor(cursor))
    return sp_id

def export_results_by_gs_id(gs_id):
    """
    Write a generic tab file for geneset products
    :param args: gs_id
    :return: status. 1 == success, 0 == failure
    """
    gene = {}
    with PooledCursor() as cursor:
        cursor.execute(
            '''SELECT gsv_source_list[1], gsv_value from geneset_value
              WHERE gs_id=%s;''', (gs_id,)
        )
        for gid in cursor:
            gene[gid[0]] = str(gid[1])
    return gene

def get_gene_sym_by_intersection(geneset_id1, geneset_id2):
    """
    Get all gene info for all genes in both genesets (mainly for jaccard similarity intersection page)
    :return: all the gene ids (ode gene ids) for the genes intersecting
    """
    gene_id1 = []
    gene_id2 = []
    intersect_sym = []
    with PooledCursor() as cursor:
        cursor.execute(
            '''SELECT ode_gene_id
               FROM extsrc.geneset_value
               where gs_id = %s;
            ''', (geneset_id1,))
        for gid in cursor:
            gene_id1.append(gid[0])
        cursor.execute(
            '''SELECT ode_gene_id
               FROM extsrc.geneset_value
               where gs_id = %s;
            ''', (geneset_id2,))
        for gid in cursor:
            gene_id2.append(gid[0])

        intersect_id = list(set(gene_id1).intersection(gene_id2))

        for gene_id in intersect_id:
            cursor.execute(
                '''SELECT gi_symbol
                   FROM extsrc.gene_info
                   where ode_gene_id = %s;
                ''', (gene_id,))
            for gid in cursor:
                intersect_sym.append(gid[0])

        return intersect_sym, intersect_id


def if_gene_has_homology(gene_id):
    """
    Chech if the gene has homolgy (use in intersection page)
    :param gene_id:
    :return:
    """
    with PooledCursor() as cursor:
        cursor.execute(
            '''SELECT hom_id
               FROM extsrc.homology
               where ode_gene_id = %s;
            ''', (gene_id,))
        if cursor.fetchone():
            return 1
        else:
            return 0


# sample api calls begin

# get all genesets associated to a gene by gene_ref_id and gdb_id
# 	if homology is included at the end of the URL also return all

# Tool Information Functions  


def get_file(apikey, task_id, file_type):
    #check to see if user has permissions for the result
    user_id = get_user_id_by_apikey(apikey)
    with PooledCursor() as cursor:
        cursor.execute('''SELECT usr_id FROM production.result WHERE res_runhash=%s''', (task_id,))
    user_id_result = cursor.fetchone()
    if (user_id != user_id_result):
        return "Error: User does not have permission to view the file."

    # if exists
    rel_path = task_id + "." + file_type
    abs_file_path = os.path.join(RESULTS_PATH, rel_path)
    print(abs_file_path)
    if (os.path.exists(abs_file_path)):
        return flask.redirect("/results/" + rel_path)
    else:
        return "Error: No such File! Check documentatin for supported file types of each tool."


def get_link(apikey, task_id, file_type):
    #check to see if user has permissions for the result
    user_id = get_user_id_by_apikey(apikey)
    with PooledCursor() as cursor:
        cursor.execute('''SELECT usr_id FROM production.result WHERE res_runhash=%s''', (task_id,))
    user_id_result = cursor.fetchone()
    if (user_id != user_id_result):
        return "Error: User does not have permission to view the file."

    # if exists
    rel_path = task_id + "." + file_type
    abs_file_path = os.path.join(RESULTS_PATH, rel_path)
    print(abs_file_path)
    if (os.path.exists(abs_file_path)):
        return "/results/" + rel_path
    else:
        return "Error: No such File! Check documentatin for supported file types of each tool."


def get_status(task_id):
    async_result = tc.celery_app.AsyncResult(task_id)
    return async_result.state


#private function that is not called by api
def get_user_id_by_apikey(apikey):
    """
    Looks up a User in the database
    :param user_id:     the user's apikey
    :return:            the User id matching the apikey or None if no such user is found
    """
    with PooledCursor() as cursor:
        cursor.execute('''SELECT usr_id FROM production.usr WHERE apikey=%s''', (apikey,))
    return cursor.fetchone()


#   genesets associated with homologous genes 
def get_genesets_by_gene_id(apikey, gene_ref_id, gdb_name, homology):
    """
    Get all genesets for a specific gene_id
    :return: the geneset into matching the given ID or None if no such gene is found
    """
    curUsrId = get_user_id_by_apikey(apikey)
    if (curUsrId):
        if not homology:
            with PooledCursor() as cursor:
                cursor.execute(
                    ''' SELECT row_to_json(row, true)
                        FROM (  SELECT geneset.*
                                FROM production.geneset
                                WHERE geneset.gs_id in
                                (
                                    SELECT gs_id
                                    FROM (extsrc.gene join odestatic.genedb using(gdb_id))
                                        join extsrc.geneset_value using(ode_gene_id)
                                    WHERE ode_ref_id = %s and gdb_name = %s
                                ) and ( cur_id < 5 or (cur_id = 5 and usr_id = %s) )
                            ) row; ''', (gene_ref_id, gdb_name, curUsrId,))
        else:
            with PooledCursor() as cursor:
                cursor.execute(
                    ''' SELECT row_to_json(row, true)
                        FROM (  SELECT geneset.*
                                FROM production.geneset
                                WHERE geneset.gs_id in
                                (
                                    SELECT gs_id
                                    FROM extsrc.geneset_value
                                    WHERE geneset_value.ode_gene_id in
                                    (
                                        SELECT ode_gene_id
                                        FROM extsrc.homology
                                        WHERE hom_id in
                                        (
                                            SELECT hom_id
                                            FROM extsrc.homology join extsrc.gene using(ode_gene_id)
                                                join odestatic.genedb using(gdb_id)
                                            WHERE ode_ref_id = %s and gdb_name = %s
                                        )
                                    )
                                ) and ( cur_id < 5 or (cur_id = 5 and usr_id = %s) )
                            ) row; ''', (gene_ref_id, gdb_name, curUsrId,))
    else:
        if not homology:
            with PooledCursor() as cursor:
                cursor.execute(
                    ''' SELECT row_to_json(row, true)
                        FROM (  SELECT geneset.*
                                FROM production.geneset
                                WHERE geneset.gs_id in
                                (
                                    SELECT gs_id
                                    FROM (extsrc.gene join odestatic.genedb using(gdb_id))
                                        join extsrc.geneset_value using(ode_gene_id)
                                    WHERE ode_ref_id = %s and gdb_name = %s
                                ) and cur_id < 5
                            ) row; ''', (gene_ref_id, gdb_name,))
        else:
            with PooledCursor() as cursor:
                cursor.execute(
                    ''' SELECT row_to_json(row, true)
                        FROM (  SELECT geneset.*
                                FROM production.geneset
                                WHERE geneset.gs_id in
                                (
                                    SELECT gs_id
                                    FROM extsrc.geneset_value
                                    WHERE geneset_value.ode_gene_id in
                                    (
                                        SELECT ode_gene_id
                                        FROM extsrc.homology
                                        WHERE hom_id in
                                        (
                                            SELECT hom_id
                                            FROM extsrc.homology join extsrc.gene using(ode_gene_id)
                                                join odestatic.genedb using(gdb_id)
                                            WHERE ode_ref_id = %s and gdb_name = %s
                                        )
                                    )
                                ) and cur_id < 5
                            ) row; ''', (gene_ref_id, gdb_name,))
    return cursor.fetchall()


def get_genes_by_geneset_id(geneset_id):
    """
    Get all gene info for a specifics gene_id
    :return: the gene matching the given ID or None if no such gene is found
    """

    with PooledCursor() as cursor:
        cursor.execute(
            ''' SELECT row_to_json(row, true) 
                FROM (  SELECT gene.* 
                        FROM extsrc.gene join extsrc.geneset_value using(ode_gene_id) 
                        where gs_id = %s) row; ''', (geneset_id,))

    return cursor.fetchall()


def get_gene_by_id(gene_id):
    """
    Get all gene info for a specific gene_id
    :return: the gene matching the given ID or None if no such gene is found
    """

    with PooledCursor() as cursor:
        cursor.execute(
            ''' SELECT row_to_json(row, true) 
                FROM (  SELECT * 
                        FROM extsrc.gene_info 
                        where ode_gene_id = %s) row; ''', (gene_id,))

    return cursor.fetchall()


def get_geneset_by_geneset_id(geneset_id):
    """
    Get all gene info for a specifics gene_id
    :return: the gene matching the given ID or None if no such gene is found
    """

    with PooledCursor() as cursor:
        cursor.execute(
            ''' SELECT row_to_json(row, true) 
                FROM (  SELECT * 
                        FROM production.geneset
                        where gs_id = %s) row; ''', (geneset_id,))

    return cursor.fetchall()


def get_geneset_by_user(apikey):
    """
    Get all gene info for a specifics user
    :return: the genesets matching the given apikey or None if no such genesets are found
    """
    apiUsrId = get_user_id_by_apikey(apikey)
    if (apiUsrId):
        with PooledCursor() as cursor:
            cursor.execute(
                ''' SELECT row_to_json(row, true)
                    FROM (  SELECT *
                            FROM production.geneset
                            WHERE usr_id = %s) row; ''', (apiUsrId,))
        return cursor.fetchall()
    else:
        return "No user with that key"


def get_projects_by_user(apikey):
    with PooledCursor() as cursor:
        cursor.execute(
            ''' SELECT row_to_json(row, true)
                FROM(  	SELECT *
                        FROM production.project
                        WHERE usr_id = (SELECT usr_id
                                        FROM production.usr
                                        WHERE apikey = %s)
                    ) row; ''', (apikey,))
    return cursor.fetchall()


def get_probes_by_gene(apikey, ode_ref_id):
    with PooledCursor() as cursor:
        cursor.execute(
            ''' SELECT row_to_json(row, true)
                FROM(	SELECT *
                        FROM odestatic.probe
                        WHERE prb_id IN (	SELECT prb_id
                                            FROM extsrc.probe2gene
                                            WHERE ode_gene_id IN (	SELECT ode_gene_id
                                                                    FROM extsrc.gene
                                                                    WHERE ode_ref_id = %s))
                    ) row; ''', (ode_ref_id,))
    return cursor.fetchall()


def get_platform_by_id(apikey, pf_id):
    with PooledCursor() as cursor:
        cursor.execute(
            ''' SELECT row_to_json(row, true)
                FROM(	SELECT *
                        FROM odestatic.platform
                        WHERE pf_id = %s
                    ) row; ''', (pf_id,))
    return cursor.fetchall();


def get_snp_by_geneid(apikey, ode_ref_id):
    with PooledCursor() as cursor:
        cursor.execute(
            ''' SELECT row_to_json(row, true)
                FROM(	SELECT *
                        FROM extsrc.snp
                        WHERE ode_gene_id IN (	SELECT ode_gene_id
                                                FROM extsrc.gene
                                                WHERE ode_ref_id = %s)
                    ) row; ''', (ode_ref_id,))
    return cursor.fetchall();


def get_publication_by_id(apikey, pub_id):
    with PooledCursor() as cursor:
        cursor.execute(
            ''' SELECT row_to_json(row, true)
                FROM(	SELECT *
                        FROM production.publication
                        WHERE pub_id = %s
                    ) row; ''', (pub_id,))
    return cursor.fetchall();


def get_species_by_id(apikey, sp_id):
    with PooledCursor() as cursor:
        cursor.execute(
            ''' SELECT row_to_json(row, true)
                FROM(	SELECT *
                        FROM odestatic.species
                        WHERE sp_id = %s
                    ) row; ''', (sp_id,))
    return cursor.fetchall();


def get_results_by_user(apikey):
    usr_id = get_user_id_by_apikey(apikey)
    with PooledCursor() as cursor:
        cursor.execute(
            ''' SELECT row_to_json(row, true)
                FROM(	SELECT res_created, res_runhash
                        FROM production.result
                        WHERE usr_id = %s ORDER BY res_created DESC
                    ) row; ''', (usr_id,))
    return cursor.fetchall();


def get_result_by_runhash(apikey, res_runhash):
    usr_id = get_user_id_by_apikey(apikey)
    with PooledCursor() as cursor:
        cursor.execute(
            ''' SELECT row_to_json(row, true)
                FROM(	SELECT *
                        FROM production.result
                        WHERE usr_id = %s and res_runhash = %s
                    ) row; ''', (usr_id, res_runhash))
    return cursor.fetchall();


def get_all_ontologies_by_geneset(gs_id):
    with PooledCursor() as cursor:
        cursor.execute(
            ''' SELECT row_to_json(row, true)
                FROM(
                        SELECT *
                        FROM extsrc.ontology natural join odestatic.ontologydb
                        WHERE ont_id in (	SELECT ont_id
                                            FROM extsrc.geneset_ontology
                                            WHERE gs_id = %s
                                        )
                        or ont_id in    (	SELECT ont_children
                                            FROM extsrc.ontology
                                            WHERE ont_id in (	SELECT ont_id
                                                                FROM extsrc.geneset_ontology
                                                                WHERE gs_id = %s
                                                            )
                                        )
                        or ont_id in	(	SELECT ont_parents
                                            FROM extsrc.ontology
                                            WHERE ont_id in	(	SELECT ont_id
                                                                FROM extsrc.geneset_ontology
                                                                WHERE gs_id = %s
                                                            )
                                        ) order by ont_id
                    ) row; ''', (gs_id, gs_id, gs_id))
    return cursor.fetchall();


#call by API only
def get_genesets_by_projects(apikey, projectids):
    user = get_user_id_by_apikey(apikey)
    projects = '('
    pArray = projectids.split(':')
    formGenesets = ''
    print(user[0])

    for proj in pArray:
        if (len(projects) > 1):
            projects += ','
        projects += proj
    projects += ')'

    query = 'SELECT gs_id FROM production.project2geneset WHERE pj_id in (SELECT pj_id FROM production.geneset WHERE pj_id in '
    query += projects
    query += ' and usr_id = '
    query += str(user[0])
    query += ');'

    with PooledCursor() as cursor:
        cursor.execute(query)

    genesets = cursor.fetchall()

    for geneset in genesets:
        if (len(formGenesets) > 0):
            formGenesets += ':'
        formGenesets += str(geneset[0])

    return formGenesets


def get_geneset_by_project_id(apikey, projectid):
    user = get_user_id_by_apikey(apikey)
    with PooledCursor() as cursor:
        cursor.execute(
            ''' SELECT row_to_json(row, true)
                FROM(  	SELECT gs_id
                        FROM production.project2geneset
                        WHERE pj_id in (SELECT pj_id
                                        FROM production.geneset
                                        WHERE pj_id = %s and usr_id = %s)
                    ) row; ''', (projectid, user))
    return cursor.fetchall()


def get_gene_database_by_id(apikey, gdb_id):
    user = get_user_id_by_apikey(apikey)
    with PooledCursor() as cursor:
        cursor.execute(
            ''' SELECT row_to_json(row, true)
                FROM(  	SELECT *
                        FROM odestatic.genedb
                        WHERE gdb_id = %s
                    ) row; ''', (gdb_id,))
    return cursor.fetchall()


#API only	
def add_project_for_user(apikey, pj_name):
    user = get_user_id_by_apikey(apikey)
    with PooledCursor() as cursor:
        cursor.execute(
            ''' INSERT INTO production.project
                (usr_id, pj_name) VALUES (%s, %s)
                RETURNING pj_id;
                ''', (user, pj_name,))
        cursor.connection.commit()
    return cursor.fetchone()


#API only	
def add_geneset_to_project(apikey, pj_id, gs_id):
    user = get_user_id_by_apikey(apikey)
    with PooledCursor() as cursor:
        cursor.execute(
            ''' INSERT INTO production.project2geneset
                        (pj_id, gs_id) VALUES ((SELECT pj_id
                                                FROM production.project
                                                WHERE usr_id = %s AND pj_id = %s),
                                                (SELECT gs_id
                                                 FROM production.geneset
                                                 WHERE gs_id = %s AND ( usr_id = %s OR
                                                                        cur_id != 5)))
                        RETURNING pj_id, gs_id;
            ''', (user, pj_id, gs_id, user,))
        cursor.connection.commit()
    return cursor.fetchall()


#API only  
def delete_geneset_from_project(apikey, pj_id, gs_id):
    user = get_user_id_by_apikey(apikey)
    with PooledCursor() as cursor:
        cursor.execute(
            '''DELETE FROM production.project2geneset
                        WHERE pj_id = ( SELECT pj_id
                                        FROM production.project
                                        WHERE usr_id = %s AND pj_id = %s)
                                        AND gs_id = %s
                        RETURNING pj_id, gs_id;
            ''', (user, pj_id, gs_id))
        cursor.connection.commit()
    return cursor.fetchall()


def generate_api_key(user_id):
    char_set = string.ascii_lowercase + string.ascii_uppercase + string.digits
    new_api_key = ''.join(random.sample(char_set, 24))
    with PooledCursor() as cursor:
        cursor.execute(
            '''UPDATE usr
               SET apikey = %s
               WHERE usr_id = %s''', (new_api_key, user_id)
        )
        cursor.connection.commit()
    return new_api_key
