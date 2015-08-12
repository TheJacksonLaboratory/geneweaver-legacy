__author__ = 'baker'

'''
This file contains functions to parse and upload files from file_contents. In particular it contains functions to
create temp tables that hold upload data and map it back to geneweaver
'''

import re
from geneweaverdb import PooledCursor, get_geneset, get_user, get_species_id_by_name, dictify_cursor

def create_temp_geneset():
    '''
    creates a temp table to hold values for geneset_values
    :param gs_id:
    :return: 'True' or 'False'
    '''
    try:
        with PooledCursor() as cursor:
            cursor.execute('''CREATE TABLE IF NOT EXISTS production.temp_geneset_value (gs_id bigint, ode_gene_id bigint,
                              src_value numeric, src_id varchar)''')
            cursor.execute('''CREATE TABLE IF NOT EXISTS production.temp_geneset_meta (gs_id bigint, sp_id int, gdb_id int)''')
            cursor.connection.commit()
        return 'True'
    except:
        return 'False'

def create_temp_geneset_from_value(gsid):
    '''
    This function creates a temp_geneset_value record for a gs_id if it exists
    :param gsid:
    :return: null
    '''
    create_temp_geneset()
    with PooledCursor() as cursor:
        cursor.execute('''SELECT gs_id FROM temp_geneset_value WHERE gs_id=%s''', (gsid,))
        is_geneset_value = cursor.rowcount
        cursor.execute('''SELECT gs_id FROM temp_geneset_meta WHERE gs_id=%s''', (gsid,))
        is_geneset_meta = cursor.rowcount
        if is_geneset_value == 0 and is_geneset_meta == 0:
            with PooledCursor() as cursor:
                cursor.execute('''DELETE FROM temp_geneset_value WHERE gs_id=%s''', (gsid,))
                cursor.execute('''INSERT INTO temp_geneset_value (SELECT gs_id, ode_gene_id, gsv_value_list[1], gsv_source_list[1]
                                FROM geneset_value WHERE gs_id=%s)''', (gsid,))
                cursor.connection.commit()
    return

def get_file_contents_by_gsid(gsid):
    '''
    Return the file contents from the file table given the gs_id if file contents exist
    :param gsid:
    :return:
    '''
    with PooledCursor() as cursor:
            cursor.execute('''SELECT file.file_contents FROM file, geneset WHERE file.file_id=geneset.file_id AND
                              geneset.gs_id=%s''', (gsid,))
            results = cursor.fetchone()
    if results[0] is None:
        return 0
    else:
        with PooledCursor() as cursor:
            cursor.execute('''SELECT f.file_contents, g.sp_id, g.gs_gene_id_type FROM file f, geneset g WHERE g.gs_id=%s
                              AND g.file_id=f.file_id''', (gsid,))
            results = cursor.fetchall()
        return results

def get_temp_geneset_gsid(gsid):
    '''
    Get geneset value from temp_geneset_meta if it exists
    :param gsid:
    :return:
    '''
    with PooledCursor() as cursor:
        cursor.execute('''SELECT sp_id FROM temp_geneset_meta WHERE gs_id=%s''', (gsid,))
        results = cursor.fetchone()[0] if cursor.rowcount != 0 else 0
        return results

def update_species_by_gsid(rargs):
    '''
    (1) convert sp_name into id, (2) insert gs_id if it doesn't exist, (3) update temp_geneset_meta table with sp_id,
    (4) rebuild temp_geneset_value table with new species
    :param rargs: user_id, gs_id, altSpecies
    :return:
    '''
    user_id = rargs['user_id']
    gs_id = rargs['gs_id']
    altSpecies = rargs['altSpecies']
    u = get_user(user_id)
    g = get_geneset(gs_id, user_id, temp=None)
    if u.is_admin or u.is_curator or g:
        create_temp_geneset()
        with PooledCursor() as cursor:
            sp_id = get_species_id_by_name(altSpecies)
            cursor.execute('''INSERT INTO temp_geneset_meta (gs_id) SELECT %s WHERE NOT EXISTS (SELECT gs_id FROM
                              temp_geneset_meta WHERE gs_id=%s)''', (gs_id, gs_id,))
            cursor.execute('''UPDATE temp_geneset_meta SET sp_id=%s WHERE gs_id=%s''', (sp_id, gs_id,))
            cursor.execute('''DELETE FROM temp_geneset_value WHERE gs_id=%s''', (gs_id,))
            cursor.connection.commit()
            reparse_file_contents_simple(gs_id, sp_id)
            cursor.connection.commit()
            return {'error': 'None'}
    else:
        return {'error': 'You do not have permission to alter this table'}

def reparse_file_contents_simple(gs_id, species=None, gdb=None):
    '''
    This is a simple parser. It does not take into consideration MicroArray data. Or any funky arrangement of tabs and
    newline characters in the file_contents attribute.
    :param gs_id:
    :return: 'True' or error msg
    '''
    file_contents = get_file_contents_by_gsid(gs_id)
    if file_contents == 0:
        return 'Error: No File Contents'
    else:
        for r in file_contents:
            ## set variables
            species = r[1] if species is None else species
            gdb = r[2] if gdb is None else gdb
            newlines = r[0].split('\n')
            if len(newlines) == 1:
                newlines = r[0].split('\r')
            if gdb < 0:
                gdb = -1 * int(gdb)
                if len(newlines) < 1:
                    return 'Error: No File Contents after loading.'
                else:
                    ##
                    ## Loop through all file_content lines
                    for newline in newlines:
                        if re.match(r'#.*$', newline):
                            print '[+] First Line Ignored ...'
                        elif re.match(r'^from', newline):
                            print '[+] From batch....'
                        else:
                            ##
                            ## catching tab delimited values
                            #values = newline.split()
                            values = re.findall(r'\S+', newline)
                            gene = None
                            try:
                                gene = values[0]
                            except:
                                print 'value error: ' + newline
                                #print r[0]
                            v = 1.0
                            if len(values) == 2:
                                v = values[1]
                                try:
                                    v = float(v.strip('\n\r '))
                                except ValueError:
                                    pass
                            ##
                            ## Get ode_gene_ids
                            if gene != '' and isinstance(v, float):
                                gene = str(gene.strip('\n\r '))
                                g = gene.lower()
                                with PooledCursor() as cursor:
                                    cursor.execute('SELECT ode_gene_id FROM gene WHERE LOWER(ode_ref_id) LIKE LOWER(%s) '
                                                   'AND sp_id=%s AND gdb_id=%s', (g, species, gdb,))
                                    s = cursor.fetchall()
                                if len(s) != 0:
                                    for i in s:
                                        with PooledCursor() as cursor:
                                            cursor.execute('''INSERT INTO production.temp_geneset_value
                                                              VALUES (%s, %s, %s, %s)''', (gs_id, i[0], v, gene,))
                                            cursor.connection.commit()
                    return 'True'

def insert_into_geneset_value_by_gsid(gsid):
    '''
    Given a gs_id, insert the rows into extsrc.geneset_value table from our temp table.
    :param gsid:
    :return: 'True' or error msg
    '''
    with PooledCursor() as cursor:
        cursor.execute('''SELECT gs_id FROM production.temp_geneset_value WHERE gs_id=%s''', (gsid,))
        g = cursor.fetchone()
        if g is not None:
            if int(g[0]) == int(gsid):
                with PooledCursor() as cursor:
                    cursor.execute('''DELETE FROM extsrc.geneset_value WHERE gs_id=%s;''' % (gs_id,))
                    cursor.execute('''INSERT INTO extsrc.geneset_value (gs_id, ode_gene_id, gsv_value, gsv_hits, gsv_source_list,
                                     gsv_value_list, gsv_in_threshold, gsv_date)
                                         SELECT gs_id, ode_gene_id, avg(src_value) as gsv_value,
                                           count(ode_gene_id) as gsv_hits, array_accum(src_id) as gsv_source_list,
                                           array_accum(src_value) as gsv_value_list,'t' as gsv_in_threshold, now() as gsv_date
                                           FROM production.temp_geneset_value
                                           WHERE gs_id=%s GROUP BY gs_id,ode_gene_id ORDER BY ode_gene_id;''' % (gs_id,))
                    cursor.execute('''DELETE FROM production.temp_geneset_value WHERE gs_id=%s;''' % (gs_id,))
                    cursor.connection.commit()
        else:
            return 'Error: Temp table does not contain gs_id'




