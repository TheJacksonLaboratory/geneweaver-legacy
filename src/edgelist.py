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

from geneweaverdb import PooledCursor, dictify_cursor, get_genesets_for_project, get_genes_by_geneset_id
from flask import session

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
                        part.append(str(v.geneset_id) + '\t\t' + str(g['ode_gene_id']) + '\n')
                    elif partition == 2:
                        part.append('\t' + str(v.geneset_id) + '\t' + str(g['ode_gene_id']) + '\n')
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
                part.append(str(n) + '\t' + str(m) + '\t\t\n')
    list(set(part))
    return part


def create_kpartite_file_from_gene_intersection(taskid, results, proj1, proj2, homology=True):
    '''
    This function takes two project ids, finds the intersection of genes and constructs
    the a task.kel file (which stands for K-clique Edge List (kel). This is a tab-delimited
    value file with values in the columns separated by tabs, with each column representing
    a partition. The file has a \n EOF character.
    :param taskid:
    :param proj1:
    :param proj2:
    :param homology: Default = True
    :return: /results-dir/[task_id].kel
    '''
    # Set variables
    #############################################
    # Comment out this line when running offline
    #usr_id = 48
    usr_id = session['user_id']
    RESULTS = results + '/'
    #############################################
    out = ''
    homology = homology if homology is True else False

    # Get the intersecting set of genes between proj1 and proj2 as a list
    genes = get_genes_from_proj_intersection(proj1, proj2, homology)
    print genes

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
    return





