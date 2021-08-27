import celery.states as states
import copy
import flask
import json
import uuid
import geneweaverdb as gwdb
import tools.toolcommon as tc
import sys
import os
from itertools import chain

TOOL_CLASSNAME = 'NESS'
ness_blueprint = flask.Blueprint(TOOL_CLASSNAME, __name__)


def run_tool():
    user = flask.g.user

    if not user:
        flask.flash('Please log in to run the tool')
        return flask.redirect('ness')

    form = flask.request.form

    ## Get the list of submitted gene/geneset/ontology entities
    entities = form['NESS_all_terms'].strip().split('\r\n')
    entities = [e for e in entities if e]
    orig_terms = copy.copy(entities)

    if not entities:
        flask.flash('You must add at least one input term')
        return flask.render_template('ness.html', emphgenes={}, foundgenes={})

    for i, e in enumerate(entities):
        ## Parse the IDs out
        e = e.split()[0]
        e = e.strip(':')

        entities[i] = e

    ## Get the RWR restart parameter, default to 0.35 if it can't be parsed or is out
    ## of bounds
    try:
        alpha = float(form['NESS_alpha'])

        if alpha < 0 or alpha >= 1.0:
            alpha = 0.35

    except ValueError:
        alpha = 0.35

    ## Get the number of permutation tests, default to 250 if it can't be parsed or is
    ## out of bounds
    try:
        permutations = float(form['NESS_permutations'])

        if permutations < 0 or permutations > 500:
            permutations = 250

    except ValueError:
        permutations = 250

    task_id = str(uuid.uuid4())
    tool = gwdb.get_tool(TOOL_CLASSNAME)
    desc = '%s on %s' % (tool.name, ','.join(entities))
    params = {
        'original_terms': orig_terms,
        'terms': entities,
        'alpha': alpha,
        'permutations': permutations,
        'user_id': user.user_id
    }

    gwdb.insert_result(
        user.user_id,
        task_id,
        '',
        json.dumps(params),
        tool.name,
        desc,
        desc
    )

    print(tc.fully_qualified_name(TOOL_CLASSNAME))

    async_result = tc.celery_app.send_task(
        tc.fully_qualified_name(TOOL_CLASSNAME),
        kwargs={
            # 'terms': entities,
            'gsids': [],
            'output_prefix': task_id,
            'params': params,
        },
        task_id=task_id
    )

    new_location = flask.url_for(TOOL_CLASSNAME + '.view_result', task_id=task_id)

    try:
        response = flask.make_response(tc.render_tool_pending(async_result, tool))

    except Exception as e:
        sys.stderr.write(str(e))
        raise
        # raise Exception('Problem generating flask response')

    response.status_code = 303
    response.headers['location'] = new_location

    return response

    # return flask.render_template('ness.html', emphgenes={}, foundgenes={})


@ness_blueprint.route('/' + TOOL_CLASSNAME + '-result/<task_id>.html', methods=['GET', 'POST'])
def view_result(task_id):
    async_result = tc.celery_app.AsyncResult(task_id)
    tool = gwdb.get_tool(TOOL_CLASSNAME)
    user = flask.g.user

    if not user:
        flask.flash('Please log in to view your results')
        return flask.redirect('analyze')

    if async_result.state == states.FAILURE:
        async_result = json.loads(async_result.result)

        if async_result['error']:
            flask.flash(async_result['error'])
        else:
            flask.flash('An unkown error occurred. Please contact a GeneWeaver admin.')

        return flask.render_template('ness.html', emphgenes={}, foundgenes={})

    elif async_result.state not in states.READY_STATES:
        return tc.render_tool_pending(async_result, tool)

    async_result = json.loads(async_result.result)

    # results = {'error': None, 'message': None}

    # return flask.render_template('ness.html', emphgenes={}, foundgenes={})
    return flask.render_template(
        'tool/NESS_result.html',
        tool=tool,
        # colors=HOMOLOGY_BOX_COLORS,
        # species_names=SPECIES_NAMES,
        async_result=async_result,
        runhash=task_id,
        # **results
    )


@ness_blueprint.route('/' + TOOL_CLASSNAME + '-status/<task_id>.json')
def status_json(task_id):
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
