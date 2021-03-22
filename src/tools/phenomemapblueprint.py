import json
import uuid
import os
from tools.JSON2TSV import JSON2TSV
import celery.states as states
import flask

import config
import geneweaverdb as gwdb
import tools.toolcommon as tc


TOOL_CLASSNAME = 'PhenomeMap'
phenomemap_blueprint = flask.Blueprint(TOOL_CLASSNAME, __name__)

# Max number of nodes, edges, and depths that can be used with the VZ plots
MAX_NODES = 50
MAX_EDGES =65
MAX_DEPTHS = 30

"""
HiSim Result and Parameter Docs

The HiSim tool requires (and returns) the following tool parameters:

    EmphasisGenes
    Homology
    gs_dict
    output_prefix
    PhenomeMap_DisableBootstrap
    PhenomeMap_GenesInNode
    PhenomeMap_HideUnEmphasized
    PhenomeMap_Homology
    PhenomeMap_MaxInNode
    PhenomeMap_MaxLevel
    PhenomeMap_MinGenes
    PhenomeMap_MinOverlap
    PhenomeMap_NodeCutoff
    PhenomeMap_p-Value
    PhenomeMap_Permutations
    PhenomeMap_PermutationTimeLimit
    PhenomeMap_UseFDR

The result returned from the tool and celery is a JSON encoded dictionary with
the following fields:

    result_image:   filename of the final image, should be <run-hash>.graphml
    error:          a string indicating any errors during the tool run
    result_map:     not sure, but looks like a string of SVG code
    parameters:     a dict containing the arguments used to run the tool. Has
                    fields for each of the parameters mentioned above.
    gs_ids:         an array of strings for each gs_id analyzed

The HiSim tool also writes several files to the results folder that aren't
included in the return result (but probably should be).
One of these is a csv file (that isn't actually in the csv format...)
containing nodes, edges, and intersections. However it doesn't seem like the
data from this file is actually used at any time (although it is read from for
some reason).
Another is a JSON file containing the nodes and edges needed for the d3js viz.
"""

@phenomemap_blueprint.route('/run-phenome-map.html', methods=['POST'])
def run_tool():
    # TODO need to check for read permissions on genesets

    form = flask.request.form

    # pull out the selected geneset IDs
    selected_geneset_ids = tc.selected_geneset_ids(form)
    # Used only when rerunning the tool from the results page
    if 'genesets' in form:
        add_genesets = form['genesets'].split(' ')
        edited_add_genesets = [gs[2:] for gs in add_genesets]
        selected_geneset_ids = selected_geneset_ids + edited_add_genesets

    if len(selected_geneset_ids) < 2:
        flask.flash(('You need to select at least 2 genesets as input for '
                    'this tool.'))

        return flask.redirect('/analyze')

    # gather the params into a dictionary
    homology_str = 'Homology'
    params = {homology_str: None}
    for tool_param in gwdb.get_tool_params(TOOL_CLASSNAME, True):
        params[tool_param.name] = form[tool_param.name]
        if tool_param.name.endswith('_' + homology_str):
            params[homology_str] = form[tool_param.name]
    if params[homology_str] != 'Excluded':
        params[homology_str] = 'Included'

    # TODO include logic for "use emphasis" (see prepareRun2(...) in Analyze.php)

    # insert result for this run
    user_id = None
    if 'user_id' in flask.session:
        user_id = flask.session['user_id']
    else:
        flask.flash('Please log in to run the tool.')

        return flask.redirect('/analyze')

    # Gather emphasis gene ids and put them in paramters
    emphgeneids = []
    user_id = flask.session['user_id']
    emphgenes = gwdb.get_gene_and_species_info_by_user(user_id)
    for row in emphgenes:
        emphgeneids.append(str(row['ode_gene_id']))
    params['EmphasisGenes'] = emphgeneids

    task_id = str(uuid.uuid4())
    tool = gwdb.get_tool(TOOL_CLASSNAME)
    desc = '{} on {} GeneSets'.format(tool.name, len(selected_geneset_ids))
    gwdb.insert_result(
        user_id,
        task_id,
        selected_geneset_ids,
        json.dumps(params),
        tool.name,
        desc,
        desc)
    async_result = tc.celery_app.send_task(
        tc.fully_qualified_name(TOOL_CLASSNAME),
        kwargs={
            'gsids': selected_geneset_ids,
            'output_prefix': task_id,
            'params': params,
        },
        task_id=task_id)

    # render the status page and perform a 303 redirect to the
    # URL that uniquely identifies this run
    new_location = flask.url_for(TOOL_CLASSNAME + '.view_result', task_id=task_id)
    response = flask.make_response(tc.render_tool_pending(async_result, tool))
    response.status_code = 303
    response.headers['location'] = new_location

    return response


@phenomemap_blueprint.route('/run-phenome-map-api.html', methods=['POST'])
def run_tool_api(apikey, homology, minGenes, permutationTimeLimit, maxInNode, permutations, disableBootstrap,
                 minOverlap, nodeCutoff, geneIsNode, useFDR, hideUnEmphasized, p_Value, maxLevel, genesets):
    print('dbg run tool api')
    # TODO need to check for read permissions on genesets
    user_id = gwdb.get_user_id_by_apikey(apikey)

    # pull out the selected geneset IDs
    # gather the params into a dictionary
    homology_str = 'Homology'
    params = {homology_str: None}

    for tool_param in gwdb.get_tool_params(TOOL_CLASSNAME, True):
        if tool_param.name.endswith('_' + 'MinGenes'):
            params[tool_param.name] = minGenes
            if minGenes not in ['1', '2', '3', '4', '5', '6', '7', '8', '9', '10', '15', '20', '25']:
                params[tool_param.name] = '1'
        if tool_param.name.endswith('_' + 'PermutationTimeLimit'):
            params[tool_param.name] = permutationTimeLimit
            if permutationTimeLimit not in ['5', '10', '15', '20']:
                params[tool_param.name] = '5'
        if tool_param.name.endswith('_' + 'MaxInNode'):
            params[tool_param.name] = maxInNode
            if maxInNode not in ['4', '8', '12', '16', '20', '24', '28', '32']:
                params[tool_param.name] = '4'
        if tool_param.name.endswith('_' + 'Permutations'):
            params[tool_param.name] = permutations
            if permutations not in ['100000', '50000', '25000', '5000', '1000', '500', '100', '0']:
                params[tool_param.name] = '0'
        if tool_param.name.endswith('_' + 'DisableBootstrap'):
            params[tool_param.name] = disableBootstrap
            if disableBootstrap not in ['False', 'True']:
                params[tool_param.name] = 'False'
        if tool_param.name.endswith('_' + 'MinOverlap'):
            params[tool_param.name] = minOverlap
            if minOverlap not in ['0%', '5%', '10%', '15%', '20%', '25%', '50%', '75%']:
                params[tool_param.name] = '0%'
        if tool_param.name.endswith('_' + 'NodeCutoff'):
            params[tool_param.name] = nodeCutoff
            if nodeCutoff not in ['Auto', '1.0', '0.1', '0.01', '0.001', '0.0001', '0.00001']:
                params[tool_param.name] = 'Auto'
        if tool_param.name.endswith('_' + 'GeneIsNode'):
            params[tool_param.name] = geneIsNode
            if geneIsNode not in ['All', 'Exclusive']:
                params[tool_param.name] = 'All'
        if tool_param.name.endswith('_' + 'UseFDR'):
            params[tool_param.name] = useFDR
            if useFDR not in ['False', 'True']:
                params[tool_param.name] = 'False'
        if tool_param.name.endswith('_' + 'HideUnEmphasized'):
            params[tool_param.name] = hideUnEmphasized
            if hideUnEmphasized not in ['False', 'True']:
                params[tool_param.name] = 'False'
        if tool_param.name.endswith('_' + 'p-Value'):
            params[tool_param.name] = p_Value
            if p_Value not in ['1.0', '0.5', '0.10', '0.05', '0.01']:
                params[tool_param.name] = '1.0'
        if tool_param.name.endswith('_' + 'MaxLevel'):
            params[tool_param.name] = maxLevel
            if maxLevel not in ['0', '10', '20', '40', '60', '80', '100']:
                params[tool_param.name] = '40'
        if tool_param.name.endswith('_' + homology_str):
            params[homology_str] = 'Excluded'
            params[tool_param.name] = 'Excluded'
            if homology != 'Excluded':
                params[homology_str] = 'Included'
                params[tool_param.name] = 'Included'

    # TODO include logic for "use emphasis" (see prepareRun2(...) in Analyze.php)
    selected_geneset_ids = genesets.split(":")
    if len(selected_geneset_ids) < 2:
        # TODO add nice error message about missing genesets
        raise Exception('there must be at least two genesets selected to run this tool')


    # insert result for this run
    user_id = None
    if 'user_id' in flask.session:
        user_id = flask.session['user_id']
    else:
        # TODO add nice error message about missing user ID.
        raise Exception('internal error: user ID missing')

    task_id = str(uuid.uuid4())
    tool = gwdb.get_tool(TOOL_CLASSNAME)
    desc = '{} on {} GeneSets'.format(tool.name, len(selected_geneset_ids))
    gwdb.insert_result(
        user_id,
        task_id,
        selected_geneset_ids,
        json.dumps(params),
        tool.name,
        desc,
        desc)

    async_result = tc.celery_app.send_task(
        tc.fully_qualified_name(TOOL_CLASSNAME),
        kwargs={
            'gsids': selected_geneset_ids,
            'output_prefix': task_id,
            'params': params,
        },
        task_id=task_id)

    return task_id


@phenomemap_blueprint.route('/' + TOOL_CLASSNAME + '-result/<task_id>.csv')
def download_csv(task_id):
    async_result = tc.celery_app.AsyncResult(task_id)
    tool = gwdb.get_tool(TOOL_CLASSNAME)

    if async_result.state in states.PROPAGATE_STATES:
        # TODO render a real descriptive error page not just an exception
        raise Exception('error while processing: ' + tool.name)
    elif async_result.state in states.READY_STATES:
        # return flask.send_file('/var/www/html/dev-geneweaver/results/' + str(async_result) + '.csv', 'text/csv', True, 'HiSimGraph_Result.csv')
        resultpath = config.get('application', 'results')
        filepath = os.path.join(resultpath, str(async_result) + '.csv')
        return flask.send_file(filepath, 'text/csv', True, 'HiSimGraph_Result.csv')


@phenomemap_blueprint.route('/' + TOOL_CLASSNAME + '-result/<task_id>.bmp?svg=<svg>')
def download_bmp(task_id):
    async_result = tc.celery_app.AsyncResult(task_id)
    tool = gwdb.get_tool(TOOL_CLASSNAME)
    print("svg = " + svg)
    if async_result.state in states.PROPAGATE_STATES:
        # TODO render a real descriptive error page not just an exception
        raise Exception('error while processing: ' + tool.name)
    elif async_result.state in states.READY_STATES:
        # return flask.send_file('/var/www/html/dev-geneweaver/results/' + str(async_result) + '.bmp', 'text/csv', True, 'HiSimGraph_Result.bmp')
        resultpath = config.get('application', 'results')
        filepath = os.path.join(resultpath, str(async_result) + '.bmp')
        return flask.send_file(filepath, 'text/csv', True, 'HiSimGraph_Result.bmp')


@phenomemap_blueprint.route('/' + TOOL_CLASSNAME + '-result/<task_id>.html', methods=['GET', 'POST'])
def view_result(task_id):
    """
    """
    tool = gwdb.get_tool(TOOL_CLASSNAME)
    resultpath = config.get('application', 'results')

    # TODO need to check for read permissions on task
    async_result = tc.celery_app.AsyncResult(task_id)

    if async_result.state == states.FAILURE:

        results = json.loads(async_result.result)

        if results['error']:
            flask.flash(results['error'])
        else:
            flask.flash(
                'An unkown error occurred. Please contact a GeneWeaver admin.'
            )

            return flask.redirect('/analyze')

    elif async_result.state in states.PROPAGATE_STATES:
        # TODO render a real descriptive error page not just an exception
        raise Exception('error while processing: ' + tool.name)

    elif async_result.state in states.READY_STATES:
        results = json.loads(async_result.result)

        if 'error' in results and results['error']:
            flask.flash(results['error'])

            return flask.redirect('/analyze')

        json_file = os.path.join(resultpath, task_id + '.json')
        json_result = ''

        with open(json_file, 'r') as fl:
            for ln in fl:
                json_result += ln

        # This module converts the json format that the Geneweaver HiSIM graph results are set as and turns it into a
        #  representation that can be used in the VZ plots.
        j2t = JSON2TSV()

        # Compute the node_list and the edge list from the graph
        node_result, edge_result = j2t.generate_graph("",j2t.load(json_result))
        nodes = node_result.split("\n")[1:]
        max_depth = -1
        for e in nodes:
          depth = e.split('\t')[0]
          try:
              depth = int(depth)
          except:
              depth = -1
          if depth > max_depth:
              max_depth = depth


        subway_availiable = False
        # Laod testing the VZ plots indicated that have 50 n 65 m and 30 d are able to be displayed
        if len(nodes)  < MAX_NODES and len(edge_result.split("\n")) < MAX_EDGES and max_depth < MAX_DEPTHS:
            subway_availiable = True


        return flask.render_template(
            'tool/PhenomeMap_result.html',
            data=json_result,
            async_result=results,
            tool=tool,
            tsv_edges=str(edge_result),
            tsv_nodes=(node_result),
            data=json_result,
            task=task_id,
            async_result=results,
            tool=tool,
            subway_availiable=subway_availiable)
    else:
        # render a page telling their results are pending
        return tc.render_tool_pending(async_result, tool)



@phenomemap_blueprint.route('/' + TOOL_CLASSNAME + '-status/<task_id>.json')
def status_json(task_id):
    # TODO need to check for read permissions on task
    async_result = tc.celery_app.AsyncResult(task_id)

    if async_result.state == states.PENDING:
        ## We haven't given the tool enough time to setup
        if not async_result.info:
            progress = None
            percent = None

        else:
            progress = async_result.info['message']
            percent = async_result.info['percent']

    elif async_result.state == states.FAILURE:
        progress = 'Failed'
        percent = ''

    else:
        progress = 'Done'
        percent = ''

    return flask.jsonify({
        'isReady': async_result.state in states.READY_STATES,
        'state': async_result.state,
        'progress': progress,
        'percent': percent
    })

