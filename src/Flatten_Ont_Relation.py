import sys
from collections import OrderedDict, defaultdict
from hashlib import md5
import json
import string
import random
import psycopg2
from psycopg2 import Error
from psycopg2.extras import execute_values
from psycopg2.pool import ThreadedConnectionPool
from tools import toolcommon as tc
import os
import flask
from flask import session
import config
import notifications
from curation_assignments import CurationAssignment
import pubmedsvc
import annotator as ann
import re


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


# the global threaded connection pool that should be used for all DB
# connections in this application
pool = GeneWeaverThreadedConnectionPool(
    5, 20,
    database=config.get('db', 'database'),
    user=config.get('db', 'user'),
    password=config.get('db', 'password'),
    host=config.get('db', 'host'),
    port=config.getInt('db', 'port')
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
        if sys.version_info[0] < 3:
            # TODO: Should be deprecated with python2
            d[col[0]] = row[i].decode('utf-8') if type(row[i]) == str else row[i]
        else:
            d[col[0]] = row[i] if type(row[i]) == str else row[i]
        OrderedDict(sorted(d.items()))
    return d


def dictify_cursor(cursor):
    """converts all cursor rows into dictionaries where the keys are the column names"""
    return (_dictify_row(cursor, row) for row in cursor)


def Union(list1, list2):
    return list(set(list1) | set(list2))


def flatten(parent: int, tree_dict: dict, is_flattened:dict, loops_record: list,path_tracer: list):
    path_tracer.append(parent)
    #print(f'current parent: {parent} \t current children: {tree_dict[parent]}')
    # print(f'current path_tracer is {path_tracer}')
    is_flattened[parent] = 'C'

    appending_list=set([])
    for n in list(tree_dict[parent]):
        # print(f"travel to {n} from {tree_dict[parent]}")
        if n not in tree_dict:
            #print("leaf node")
            continue
        elif is_flattened[n] == 'T':
            #tree_dict[parent] = Union(tree_dict[parent], tree_dict[n])
            appending_list=appending_list | tree_dict[n]
        elif is_flattened[n] == 'C':
            print("detect a loop!")
            print(f'path tracer: {path_tracer}')

            loop=path_tracer[path_tracer.index(n):]
            loops_record.append(loop)
            print(f"loop start from {path_tracer.index(n)} to {len(path_tracer)}")
            print(f'loop is: {loop}\n\n')


        else:
            # if the sub tree is not flattened
            #print(f"flattening {n}")
            flatten(n, tree_dict, is_flattened,loops_record,path_tracer)
            # tree_dict[parent] = Union(tree_dict[parent], tree_dict[n])
            appending_list = appending_list | tree_dict[n]

    # print(type(tree_dict[parent]))
    # print(type(appending_list))
    tree_dict[parent]=tree_dict[parent] | appending_list
    is_flattened[parent] = 'T'
    path_tracer.remove(parent)
    # print(f'after removing: {path_tracer}')
    # print(f'------------------------------------------\n')


'''
test code


test_dict = {
    'A': ['B', 'C', 'D'],
    'B': ['E', 'F', 'G', 'H'],
    'C': ['I'],
    'D': ['J', 'K'],
    'G': ['L'],
    'L': ['M'],
    'H': ['N'],
    'M': ['O', 'B'],
    'O': ['P', 'Q']

}

is_flatterned = {}
for parent in test_dict.keys():
    is_flatterned[parent] = 'F'

print(is_flatterned)
loops_record = []
path_tracer=[]
for parent, children in test_dict.items():
    if is_flatterned[parent] == 'F':
        flatten(parent, test_dict, is_flatterned, loops_record,path_tracer)

print(test_dict)
print(f"{loops_record}")
'''


with PooledCursor() as cursor:
    cursor.execute(
        # TODO: documentation
        '''
    select left_ont_id,right_ont_id from extsrc.ontology_relation where right_ont_id NOT IN(
    select left_ont_id
     from extsrc.ontology_relation
     where right_ont_id In (select ont_id from extsrc.ontology where ont_parents = 0 and ont_children != 0) and or_type='is_a'
    union
     select ont_id
     from extsrc.ontology
     where ont_parents = 0
       and ont_children != 0) and or_type='is_a';
        '''
    )

    child_parent = cursor.fetchall()

    #start to conver the list of tupe into the dictionary which the key is the parent and value is the children
    tree_dict={}
    is_flattened={}

    for child,parent in child_parent:

        if (parent in tree_dict) and (parent != child):
            tree_dict[parent].add(child)
        elif parent != child:
            tree_dict[parent]={child}
            is_flattened[parent]='F'

    # print(tree_dict)
    loops_record = []
    path_tracer = []
    for parent, children in tree_dict.items():
        if is_flattened[parent] == 'F':
            flatten(parent, tree_dict, is_flattened, loops_record, path_tracer)

    print('finish!')
    # print(len(tree_dict.keys()))
    #
    # new_loops_records=set([])
    # for loop in loops_record:
    #     # print(loop)
    #     new_loops_records.update(loop)
    # cursor.execute(
    #     '''
    #     select distinct ontdb_id
    #     from extsrc.ontology
    #     where ont_id IN (%s)
    #     ''',(list(new_loops_records))
    # )
    #
    # print("done!")
    # print(cursor.fetchall())
