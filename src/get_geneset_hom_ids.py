from psycopg2.pool import ThreadedConnectionPool
import flask
import config
import time
start_time = time.time()

import requests

# edit once deployed, currently running on crick server
agr_url = 'http://127.0.0.1:5000/agr-service/'
app = flask.Flask(__name__)

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

def get_geneset_hom_ids_v3(gs_id):
    with PooledCursor() as cursor:
        cursor.execute('''SELECT hom_id, ode_ref_id, gene.ode_gene_id, gdb_id FROM extsrc.gene INNER JOIN extsrc.geneset_value gsv
                                ON gene.ode_gene_id=gsv.ode_gene_id INNER JOIN production.geneset g ON gsv.gs_id=g.gs_id
                                LEFT JOIN extsrc.homology h ON  gene.ode_gene_id = h.ode_gene_id
                                WHERE gdb_id IN (10,11,12,13,14,15,16) AND gs_status not like 'de%%' AND g.gs_id=%s''', (gs_id,))
        genes = cursor.fetchall()
        for g in genes:
            g = list(g)
            ode_gene_id = g[0]
            ode_ref_id = g[1]
            gdb_id = g[2]
            response = requests.get(
                f"{str(agr_url)}ortholog/get_id_by_from_gene/{str(ode_gene_id)}/{str(ode_ref_id)}/{str(gdb_id)}")
            if(response.ok):
                g.append(response.json())
            else:
                g.append("NA")
        return genes

info = get_geneset_hom_ids_v3(338314)
print(info)

print("\n--- %s seconds ---" % (time.time() - start_time))
