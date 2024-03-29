__author__ = 'baker'
'''
This file contains functions to export an edge list for the k-partite view. The first line in the file declares the
number of vertices in each partite set, followed by the total number of edges in the graph. The numbers must be
tab-separated. The number of partite sets is implied by how many tab-separated numbers are contained in the first line.
For example, the line

5     8      3      4     35

declares that there are 5 vertices in the first partite set, 8 in the second, 3 in the third, 4 in the fourth,
and that there are 35 edges in the graph. By implication, the graph has four partite sets.

Each subsequent line in the file lists an edge. Tabs are used to indicate to which partite sets the two endpoints
(vertices) of the edge belong. If a vertex label appears prior to the first tab on the line, the vertex is in the
first partite set. If the label appears after exactly one tab, the vertex is in the second partite set. If the label
appears after exactly two tabs, the vertex is in the third partite set. And so on. Here are some example edges that
illustrate the format.
a<tab>e
a is in the first partite set, e is in the second partite set.
a<tab><tab>h
a is in the first partite set, h is in the third partite set.
<tab>e<tab>i
e is in the second partite set, i is in the third partite set.
w<tab><tab><tab><tab>x
w is in the first partite set, x is in the fifth partite set.
<tab><tab>y<tab><tab>z
y is in the third partite set, z is in the fifth partite set.

'''

from geneweaverdb import PooledCursor, dictify_cursor, get_genesets_for_project, get_genes_by_geneset_id, \
    get_genesets_for_project
from flask import session
from flask import redirect
from flask import flash
import os.path
import re
import copy



def get_genes_from_proj_intersection(proj1, proj2, hom=True):
    '''
    Takes two project ids and returns a list of intersecting genes
    :param proj1:
    :param proj2:
    :return: list of genes
    '''
    #genes = []
    if not hom:
        with PooledCursor() as cursor:
            cursor.execute('''SELECT gv.ode_gene_id FROM geneset_value gv, project2geneset p2g
                              WHERE p2g.pj_id=%s AND p2g.gs_id=gv.gs_id
                              INTERSECT
                              SELECT gv.ode_gene_id FROM geneset_value gv, project2geneset p2g
                              WHERE p2g.pj_id=1430 and p2g.gs_id=gv.gs_id''', (proj1, proj2,))
    else:
        with PooledCursor() as cursor:
            cursor.execute('''SELECT DISTINCT h1.ode_gene_id FROM geneset_value gv, project2geneset p2g, homology h1,
                              homology h2 WHERE p2g.pj_id=%s AND p2g.gs_id=gv.gs_id AND gv.ode_gene_id=h1.ode_gene_id
                              AND h1.hom_id=h2.hom_id
                              INTERSECT
                              SELECT DISTINCT h1.ode_gene_id FROM geneset_value gv, project2geneset p2g, homology h1,
                              homology h2 WHERE p2g.pj_id=%s AND p2g.gs_id=gv.gs_id AND gv.ode_gene_id=h1.ode_gene_id
                              AND h1.hom_id=h2.hom_id''', (proj1, proj2,))
    res = list(dictify_cursor(cursor)) if cursor.rowcount != 0 else None

    #res = cursor.fetchall()
    #if res is not None:
    #    for r in res:
    #        print r[0]
    #        genes.append(r[0])
    return res


def intersect_geneset(gsid1, gsid2, hom=True):
    '''
    Return TRUE if two genesets share a ode_gene_id
    :param gsid1:
    :param gsid2:
    :return: boolean
    '''
    if not hom:
        with PooledCursor() as cursor:
            cursor.execute('''SELECT ode_gene_id FROM geneset_value WHERE gs_id=%s
                              INTERSECT
                              SELECT ode_gene_id FROM geneset_value WHERE gs_id=%s''', (gsid1, gsid2,))
    else:
        with PooledCursor() as cursor:
            cursor.execute('''SELECT DISTINCT h1.ode_gene_id FROM geneset_value gv, homology h1, homology h2
                              WHERE gv.gs_id=%s AND gv.ode_gene_id=h2.ode_gene_id AND h2.hom_id=h1.hom_id
                              INTERSECT
                              SELECT DISTINCT h1.ode_gene_id FROM geneset_value gv, homology h1, homology h2
                              WHERE gv.gs_id=%s AND gv.ode_gene_id=h2.ode_gene_id AND h2.hom_id=h1.hom_id''', (gsid1, gsid2,))
    return True if cursor.rowcount != 0 else False

def get_jaccard(pjid1, pjid2, threshold):
    '''
    Return the jaccard of two projects if it exists, 0 otherwise
    :param pjid1: int
    :param pjid2: int
    :return: float
    '''
    pj1 = pjid1 if pjid1 < pjid2 else pjid2
    pj2 = pjid2 if pjid2 > pjid1 else pjid1
    # If the two genesets are the same, should we be returning 1?
    if pj1 == pj2:
        return 1
    with PooledCursor() as cursor:
        cursor.execute('''SELECT jac_value FROM geneset_jaccard WHERE gs_id_left=%s AND gs_id_right=%s AND
                          jac_value > %s''', (pj1, pj2, threshold,))
        return cursor.fetchone()[0] if cursor.rowcount != 0 else 0


def edge_gene2proj(genes, projDict, partition):
    '''
    Takes a list of genes and a dictionary of genesets. If a gene exists in a geneset, then an edge
    is created.
    :param genes:
    :param projDict1:
    :return: list of edges, formated based on the partition
    '''
    part = []
    for v in projDict:
        genesetGenes = get_genes_by_geneset_id(v.geneset_id)
        for gg in genesetGenes:
            for g in genes:
                ## If the gene exists in the geneset
                if int(gg[0]['ode_gene_id']) == int(g['ode_gene_id']):
                    if partition == 1:
                        part.append('gs_' + str(v.geneset_id) + '\t\t' + 'gi_' + str(g['ode_gene_id']) + '\n')
                    elif partition == 2:
                        part.append('\t' + 'gs_' + str(v.geneset_id) + '\t' + 'gi_' + str(g['ode_gene_id']) + '\n')
    return set(part)


def edge_proj2proj(projDict1, projDict2):
    '''
    Take two partitions of genesets and return a list of which genesets intersect based on mapping genes
    :param projDict1:
    :param projDict2:
    :return: list of edged, formated for part1\part2\t\t
    '''
    part = []
    for n in projDict1:
        for m in projDict2:
            if intersect_geneset(n, m):
                part.append('gs_' + str(n) + '\t' + 'gs_' + str(m) + '\t\t\n')
    list(set(part))
    return part

def create_kpartite_file_from_jaccard_overlap(taskid, results, projs, threshold):
    '''
    This function takes a taskid and results dir for writing. It also takes a LIST of projects and a threshold. By
    looping through the list, we write all possible combinations of geneset pairs over the given threshold (threshold).
    This file is writen as a *.kel file with values in the columns seperated by tabs, with weach column representing a
    partition. The file has a \n EOF character.
    :param taskid: string
    :param results: string
    :param projs: list
    :param threshold: float
    :return:
    '''
    # Set variables
    ##########################################
    # Comment out these lines as appropriate
    # for running offline
    #usr_id = 48
    usr_id = session['user_id']
    RESULTS = results
    ###########################################
    fileout = ''
    genesets = {}
    counts = {}

    print("theshold value selected : ", threshold)

    # Dictionary of dictionaries
    # Each entry
    # Project: {i, k}

    # make a dictionary of proj -> genesets
    for p in projs:
        genesets[p] = get_genesets_for_project(p, usr_id)

    for p in projs:
        counts[p] = 0
        for g in genesets[p]:
            counts[p] += 1

    ignored = []
    ign_projects = []

    edge_count = 0

    # Loop through all of the proj_ids, and return jaccard values where they exist, 0 otherwise
    for i in range(0, len(projs)):
        for j in range(0, len(projs)):
            k = i + j + 1
            # Set up the proper number of tabs between the two columns that are being populated
            pretab = '\t' * i
            endtab = '\t' * ((len(projs) - 1) - k)
            midtab = '\t' * (k - i)
            if k < len(projs):
                # Need to keep counts of each row in the counts dictionary
                #if i not in counts:
                #    counts[i] = 1
                # Shouldn't there only be one vertex per partition, since each partition is a project??
                #else:
                #    counts[i] += 1
                #if k not in counts:
                #    counts[k] = 1
                #else:
                #    counts[k] += 1
                # Now another inner loop (maybe need to be recursive?) to find all combinations of values
                # against eachother.

                for m in genesets[projs[i]]:
                    for n in genesets[projs[k]]:
                        jac_value = get_jaccard(m.geneset_id, n.geneset_id, threshold)
                        if jac_value > 0:
                            fileout += pretab + str(m.geneset_id) + midtab + str(n.geneset_id) + endtab + '\n'
                            edge_count = edge_count + 1
                        else:
                            if str(m.geneset_id) not in fileout and str(m.geneset_id) not in ignored:
                                ignored.append(str(m.geneset_id))
                                ign_projects.append(str(projs[i]))
                            if str(n.geneset_id) not in fileout and str(n.geneset_id) not in ignored:
                                ignored.append(str(n.geneset_id))
                                ign_projects.append(str(projs[k]))


    ig = ''
    for i in range(0, len(ignored)):
        if ignored[i] not in fileout:
            ig += ign_projects[i] + '\t' + ignored[i] + '\n'

    # Add the row counts to the top of the page
    values = []
    for i in range(0, len(projs)):
        values.append(str(counts[projs[i]]))
    temp = str.join('\t', (values))
    temp = temp + '\t' + str(edge_count)
    fileout = temp + '\n' + fileout

    # print results to a file
    print("file contains:")
    print(fileout)
    print("filepath:", RESULTS + taskid + '.kel')
    out = open(RESULTS + taskid + '.kel', 'wb')
    out.write(fileout)
    out.close()
    out = open(RESULTS + taskid + '.ign', 'wb')
    out.write(ig)
    out.close()


def create_kpartite_file_from_gene_intersection(taskid, results, proj1, proj2, homology):
    '''
    This function takes two project ids, finds the intersection of genes and constructs
    the a task.kel file (which stands for K-clique Edge List (kel). This is a tab-delimited
    value file with values in the columns separated by tabs, with each column representing
    a partition. The file has a \n EOF character.
    :param taskid:
    :param proj1:
    :param proj2:
    :return: /results-dir/[task_id].kel
    '''
    # Set variables
    #############################################
    # Comment out this line when running offline
    #usr_id = 48
    usr_id = session['user_id']
    RESULTS = results
    #############################################
    out = ''

    homology = homology if homology is True else False

    # Get the intersecting set of genes between proj1 and proj2 as a list
    genes = get_genes_from_proj_intersection(proj1, proj2, homology)

    # Catches if there are no intersections for the projects selected
    # Will redirect user to analyze page
    if genes is None:
        return -1

    if len(genes) > 50:
        return -2

    if len(genes) > 0:
        # Get all geneset and genes in a project as a list[dictify(cursor)]
        projDict1 = get_genesets_for_project(proj1, usr_id)
        projDict2 = get_genesets_for_project(proj2, usr_id)

        # Populate the edges between the intersecting genes and projDict1, called partition1
        partition1 = edge_gene2proj(genes, projDict1, 1)

        # Populate the edges between the intersecting genes and projDict2, called partition2
        partition2 = edge_gene2proj(genes, projDict2, 2)

        # Populate the edges between the intersectin of the lists of geneset ids in projDict1 and projDict2
        partition3 = edge_proj2proj([v.geneset_id for v in projDict1], [v.geneset_id for v in projDict2])

        # Create the first line (1st part, 2nd part, 3rd part, total)
        # and write out to RESULTS directory
        firstLine = str(len(partition1) + len(partition3)) + '\t' + str(len(partition2) + len(partition3)) + '\t' + str(len(partition1) + len(partition2)) + '\t' + str(len(partition1) + len(partition2) + len(partition3)) + '\n'

        file = firstLine + ''.join(partition1) + ''.join(partition2) + ''.join(partition3) + '\n'

        #print "file contains:"
        #print file
        out = open(RESULTS + taskid + '.kel', 'wb')
        out.write(file)
        out.close()

def create_json_from_triclique_output(taskid, results):
    """
    This function is not finished becuase I am not sure of the exact format for all possible values of k
    :param taskid: this is prepended to .kel files
    :param results: from the results directory
    :return: true
    """

    # List of lists of values represented by partitions
    partitions = []

    # The strategy is to make a matrix of size n (the length of the indentifier list). Loop through the list, and find
    # the identifiers at the appropriate index, and then check to see if they exist in separate partitions (or lists)
    # within the partitions list

    # Read in file. Only add values after the edge triclique
    start_parsing = False
    fh = open(os.path.join(results, taskid + '.mkc'), 'r')
    for line in fh:
        if start_parsing:
            if not re.match("[ \n\t\r]", line):
                temp_line = [item for item in re.split(r"[\t\s ]+", line) if item]
                partitions.append(temp_line)
        else:
            matchObj = re.match('edge maximum k-clique', line)
            if matchObj:
                start_parsing = True
    fh.close()
    if len(partitions) == 0:
        return 1

    # make a flattened list of unique values in partitions and then
    # create an empty matrix based on that list
    identifiers = [item for sublist in partitions for item in sublist]
    sorted(set(identifiers))
    n = len(identifiers)

    Matrix = [[0 for x in range(n)] for x in range(n)]


    # Loop through the Matrix and, foreach i,j, check the partition matrix to see if they show up together
    # this can be modified later to test for weight
    for i in range(n):
        for j in range(n):
            Matrix[i][j] = get_matrix_value(i, j, identifiers, partitions)


    # Print matrix
    row = []
    json = '['
    for i in range(n):
        json += '['
        for j in range(n):
            row.append(str(Matrix[i][j]))
        json += ','.join(row)
        json += '],'
        row = []
    json = json[:-1]
    json += ']'

    f = open(results + '/' + taskid + '.json', 'wb')
    f.write(json)
    f.close()

    create_csv_from_mkc(taskid, results, identifiers, partitions)

    return Matrix


def get_matrix_value(i, j, identifiers, partitions):
    """
    Find out if identifier ar i, j are in the same or different partitions.
    :param i:
    :param j:
    :param identifiers: sorted list
    :param partitions: list of list
    :return: float. 1.0 or 0.0
    """
    # Get the actual value in the sorted list of identifiers
    id1 = identifiers[i]
    id2 = identifiers[j]
    print("In get_matrix_value")
    print(id1)
    print(id2)
    print("Identifiers" + str(identifiers))
    print("Partitions: " + str(partitions))

    # Set variables
    id1Found = []
    id2Found = []
    p = 0

    # Loop through the list of lists to see if values are true
    for n in partitions:
        if id1 in n:
            id1Found.append(p)
        if id2 in n:
            id2Found.append(p)
        p += 1

    if len(set(id2Found).intersection(id1Found)) > 0:
        #print set(id2Found).intersection(id1Found)
        return 0.0
    else:
        # TODO: query to the database to get the frequency of the gene in the geneset or project
        # Will have to be different for Jaccard and Exact gene overlap
        geneset_id = ''
        if re.match("^gs_", id1):
            geneset_id = id1[3:]
        else:
            geneset_id = id2[3:]
        with PooledCursor() as cursor:
            cursor.execute(cursor.mogrify("SELECT gs_count FROM geneset WHERE gs_id =' " + geneset_id + " ' "))
            gs_count = cursor.fetchone()
        return 1.0/gs_count[0]


def create_csv_from_mkc(taskid, results, identifiers, partitions):
    HOMOLOGY_BOX_COLORS = ['#6699FF', '#FFCC00', '#FF0000', '#58D87E', '#588C7E', '#F2E394', '#1F77B4', '#F2AE72', '#F2AF28', '#D96459',
                       '#D93459', '#5E228B', '#698FC6']

    f = open(results + '/' + taskid + '.csv', 'wb')
    f.write("name,gs_name,abbr,something,color\n")

    # Get rid of the first two elements in identifiers (project ids)
    print("identifiers before:", identifiers)
    genesets = list(identifiers)
    print("genesets:", genesets)
    gs_ids = []
    gi_ids = []
    for item in genesets:
        if re.match("^gs_", item):
            gs_ids.append(item[3:])
        else:
            gi_ids.append(item[3:])
    print("genesets:", gs_ids)
    print("genes:", gi_ids)
    # Get rid of gs_ and gi
    for x in range(0,len(identifiers)):
        identifiers[x] = identifiers[x][3:]
    for item in partitions:
        for x in range(0, len(item)):
            item[x] = item[x][3:]

    proj_names = list()

    for p in range(len(gs_ids)):
        with PooledCursor() as cursor:
            cursor.execute(cursor.mogrify("SELECT gs_name FROM geneset WHERE gs_id =' " + gs_ids[p] + " ' "))

        temp = (list(dictify_cursor(cursor)))
        temp = temp[0]
        temp = temp.values()
        proj_names.append(temp)

    p_names = []
    for val in proj_names:
        temp = val[0].encode('ascii')
        temp2 = temp.replace(',','')
        p_names.append(temp2)

    print("project_names", p_names)

    gs_names = []
    # SQL query to the database to get the names of the genes
    for g in range(len(gi_ids)):
        with PooledCursor() as cursor:
            cursor.execute(cursor.mogrify("SELECT ode_ref_id FROM gene WHERE ode_pref='t' and gdb_id=7 and ode_gene_id = ' " + gi_ids[g] + " ' "))
        temp = (list(dictify_cursor(cursor)))
        temp = temp[0]
        temp = temp.values()
        gs_names.append(temp)

    g_names = []

    for val in p_names:
        g_names.append(val)

    for val in gs_names:
        g_names.append(val[0].encode('ascii'))

    abbr = []
    for g in range(len(gs_ids)):
        with PooledCursor() as cursor:
            cursor.execute(cursor.mogrify("SELECT gs_abbreviation FROM geneset WHERE gs_id = ' " + gs_ids[g] + " ' "))
        temp = (list(dictify_cursor(cursor)))
        temp = temp[0]
        temp = temp.values()
        abbr.append(temp)
    for g in gs_names:
        abbr.append(g)

    g_abbr=[]
    for val in abbr:
        g_abbr.append(val[0].encode('ascii'))


    print("g_names:", g_names)

    count = 0
    for i in range(len(partitions)):
        for j in range(len(partitions[i])):
            f.write(str(identifiers[count]) + ',' + g_names[count] + ',' + g_abbr[count] + ',0,' + HOMOLOGY_BOX_COLORS[i] + '\n')
            print(str(identifiers[count]) + ',' + g_names[count] + ',' + g_abbr[count] + ',0,' + HOMOLOGY_BOX_COLORS[i])
            count = count + 1
    f.close()


def create_json_from_triclique_output_jaccard(taskid, results):
    """
    This function is not finished becuase I am not sure of the exact format for all possible values of k
    :param taskid: this is prepended to .kel files
    :param results: from the results directory
    :return: true
    """
    usr_id = session['user_id']
    # List of lists of values represented by partitions
    partitions = []

    # The strategy is to make a matrix of size n (the length of the indentifier list). Loop through the list, and find
    # the identifiers at the appropriate index, and then check to see if they exist in separate partitions (or lists)
    # within the partitions list

    # Read in file. Only add values after the edge triclique
    start_parsing = False
    fh = open(os.path.join(results, taskid + '.mkcj'), 'r')
    for line in fh:
        if start_parsing:
            if not re.match("[ \n\t\r]", line):
                temp_line = [item for item in re.split(r"[\t\s ]+", line) if item]
                partitions.append(temp_line)
        else:
            matchObj = re.match('edge maximum k-clique', line)
            if matchObj:
                start_parsing = True
    fh.close()
    if len(partitions) == 0:
        return 1

    fh = open(os.path.join(results, taskid + '.ign'), 'r')
    ignored = []
    for line in fh:
        temp_line = [item for item in re.split(r"[\t\s]+", line) if item]
        ignored.append(temp_line)

    print("IGNORED,", ignored)
    # Combine those that are in the same project
    gsets = []
    for item in ignored:
        pjid = item[0]
        gsid = item[1]
        temp = get_genesets_for_project(pjid, usr_id)
        tempadd = []
        for item in temp:
            tempadd.append(str(int(item.geneset_id)))
        gsets.append(tempadd)
    print("gsets", list(gsets))
    for i in range(0,len(gsets)):
        for j in range(0, len(partitions)):
            p = copy.copy(partitions[j])
            p.append(ignored[i][1])
            set(sorted(set(p)))
            print(p)
            print(sorted(set(gsets[i])))
            if set(sorted(set(gsets[i]))).issubset(p):
                partitions[j].append(ignored[i][1])



    # make a flattened list of unique values in partitions and then
    # create an empty matrix based on that list
    identifiers = [item for sublist in partitions for item in sublist]
    sorted(set(identifiers))
    n = len(identifiers)

    print("partitions", partitions)
    print("identifiers", identifiers)

    Matrix = [[0 for x in range(n)] for x in range(n)]


    # Loop through the Matrix and, foreach i,j, check the partition matrix to see if they show up together
    # this can be modified later to test for weight
    for i in range(n):
        for j in range(n):
            Matrix[i][j] = get_matrix_value_jaccard(i, j, identifiers, partitions, ignored)


    # Print matrix
    row = []
    json = '['
    for i in range(n):
        json += '['
        for j in range(n):
            row.append(str(Matrix[i][j]))
        json += ','.join(row)
        json += '],'
        row = []
    json = json[:-1]
    json += ']'

    f = open(results + '/' + taskid + '.json', 'wb')
    f.write(json)
    f.close()

    create_csv_from_mkc_jaccard(taskid, results, identifiers, partitions)

    return Matrix

def create_csv_from_mkc_jaccard(taskid, results, identifiers, partitions):
    HOMOLOGY_BOX_COLORS = ['#6699FF', '#FFCC00', '#FF0000', '#58D87E', '#588C7E', '#F2E394', '#1F77B4', '#F2AE72', '#F2AF28', '#D96459',
                       '#D93459', '#5E228B', '#698FC6']

    f = open(results + '/' + taskid + '.csv', 'wb')
    f.write("name,gs_name,abbr,something,color\n")

    # Get rid of the first two elements in identifiers (project ids)
    print("identifiers before:", identifiers)
    genesets = list(identifiers)
    temp_names = []
    gs_names = []

    for p in range(len(genesets)):
        with PooledCursor() as cursor:
            cursor.execute(cursor.mogrify("SELECT gs_name FROM geneset WHERE gs_id =' " + genesets[p] + " ' "))

        temp = (list(dictify_cursor(cursor)))
        temp = temp[0]
        temp = temp.values()
        temp_names.append(temp)

    for val in temp_names:
        temp = val[0].encode('ascii')
        temp2 = temp.replace(',','')
        gs_names.append(temp2)
    abbr = []
    for g in range(len(genesets)):
        with PooledCursor() as cursor:
            cursor.execute(cursor.mogrify("SELECT gs_abbreviation FROM geneset WHERE gs_id = ' " + genesets[g] + " ' "))
        temp = (list(dictify_cursor(cursor)))
        temp = temp[0]
        temp = temp.values()
        abbr.append(temp)
    for g in gs_names:
        abbr.append(g)

    g_abbr=[]
    for val in abbr:
        g_abbr.append(val[0].encode('ascii'))

    print(abbr)

    count = 0
    for i in range(len(partitions)):
        for j in range(len(partitions[i])):
            print(str(identifiers[count]) + ',' + gs_names[count] + ',' + g_abbr[count] + ',0,' + HOMOLOGY_BOX_COLORS[i] + '\n')
            f.write(str(identifiers[count]) + ',' + gs_names[count] + ',' + g_abbr[count] + ',0,' + HOMOLOGY_BOX_COLORS[i] + '\n')
            count = count + 1
    f.close()

def get_matrix_value_jaccard(i, j, identifiers, partitions, ignored):
    """
    Find out if identifier ar i, j are in the same or different partitions.
    :param i:
    :param j:
    :param identifiers: sorted list
    :param partitions: list of list
    :return: float. 1.0 or 0.0
    """
    # Get the actual value in the sorted list of identifiers
    id1 = identifiers[i]
    id2 = identifiers[j]
    print("In get_matrix_value_jaccard")
    print(id1)
    print(id2)
    print("Identifiers" + str(identifiers))
    print("Partitions: " + str(partitions))

    # Set variables
    id1Found = 0
    id2Found = 0
    p = 0
    in_both = 0

    for item in ignored:
        if id1 in item or id2 in item:
            return 0.0

    # Find which partition each identifier is in
    index = 0
    bound = len(partitions)
    for n in range(0, bound):
        if i >= len(partitions[n]) + index:
            index += len(partitions[n])
        else:
            id1Found = n
            break
    index = 0
    for m in range(0, bound):
        if j >= len(partitions[m]) + index:
            index += len(partitions[m])
        else:
            id2Found = m
            break

    if id1Found == id2Found:
        return 0.0
    else:
        # Return similarity
        gs_id1 = id1 if id1 < id2 else id2
        gs_id2 = id2 if id2 > id1 else id1
        with PooledCursor() as cursor:
            cursor.execute('''SELECT jac_value FROM geneset_jaccard WHERE gs_id_left=%s AND gs_id_right=%s''', (gs_id1, gs_id2,))
        return cursor.fetchone()[0] if cursor.rowcount != 0 else 0
