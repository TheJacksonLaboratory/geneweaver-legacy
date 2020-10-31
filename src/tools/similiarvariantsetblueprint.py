import json
import uuid
import os
from tools.JSON2TSV import JSON2TSV
import celery.states as states
import flask
from flask import request
import config
import geneweaverdb as gwdb
import tools.toolcommon as tc


TOOL_CLASSNAME = 'SimilarVariantSet'
RESULTS_PATH = config.get('application', 'results')
similiar_variantset_blueprint = flask.Blueprint(TOOL_CLASSNAME, __name__)


@similiar_variantset_blueprint.route('/run-similar-variant-set2.html', methods=['GET'])
def test():
    return "Test"

@similiar_variantset_blueprint.route('/run-similar-variant-set.html', methods=['GET'])
def run_tool():
    print("Tool running")
    gs_id = request.args.get('gs_id')
    task_id = str(uuid.uuid4())
    tool = gwdb.get_tool(TOOL_CLASSNAME)
    #user_id = flask.session['user_id']
    desc = '{} on {}'.format(tool, 'GS' + str(gs_id))
    print("Description: %s", desc)

    '''
    gwdb.insert_result(
        user_id,
        task_id,
        selected_geneset_ids,
        json.dumps(params),
        tool.name,
        desc,
        desc)

    '''
    print("Sending task")
    async_result = tc.celery_app.send_task(
        tc.fully_qualified_name(TOOL_CLASSNAME),
        kwargs={
            'gsids': [gs_id],
            'output_prefix': task_id,
            'params': {},
        },
        task_id=task_id
    )
    print("Task sent")
    new_location = flask.url_for(TOOL_CLASSNAME + '.view_result', task_id=task_id)
    print("New Loc: %s" % new_location)
    response = flask.make_response(tc.render_tool_pending(async_result, tool))
    response.status_code = 303
    response.headers['location'] = new_location
    return response

def get_results(async_result):
    if async_result.state in states.PROPAGATE_STATES:
        raise BooleanResultError('error while processing:')

    elif async_result.state == states.FAILURE:
        results = json.loads(async_result.result)

        if results['error']:
            raise BooleanResultError(results['error'])
        else:
            raise BooleanResultError('An unknown error occurred. Please contact a GeneWeaver admin.')

    elif async_result.state in states.READY_STATES:
        results = json.loads(async_result.result)

        if 'error' in results and results['error']:
            raise BooleanResultError(results['error'])
        else:
            return results

def read_results_file(task_id):
    with open(RESULTS_PATH + '/' + task_id + '.json', 'r') as f:
        json_results = f.readline()
        f.close()
    return json.loads(json_results)

@similiar_variantset_blueprint.route('/' + TOOL_CLASSNAME + '-result/<task_id>.html', methods=['GET'])
def view_result(task_id):
    async_result = tc.celery_app.AsyncResult(task_id)
    tool = gwdb.get_tool(TOOL_CLASSNAME)
    print(tool)

    try:
        results = get_results(async_result)
    except BooleanResultError as e:
        flask.flash(e.message)
        return flask.redirect('/analyze')

    if results:
        # added emphgeneids for the table in the boolean algebra result html file

        json_results = read_results_file(task_id)
        print(json_results)

        return flask.render_template(
            'tool/SimilarVariantSet.html',
            json_results=json_results,
            async_result=results,
            tool=tool,
            task_id=task_id)

    else:
        # render a page telling their results are pending
        return tc.render_tool_pending(async_result, tool)

@similiar_variantset_blueprint.route('/' + TOOL_CLASSNAME + '-status/<task_id>.json')
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
