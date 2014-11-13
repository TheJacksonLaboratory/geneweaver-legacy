import celery.states as states
import flask
import json
import uuid

import geneweaverdb as gwdb
import toolcommon as tc

TOOL_CLASSNAME = 'BooleanAlgebra'
boolean_algebra_blueprint = flask.Blueprint(TOOL_CLASSNAME, __name__)

@boolean_algebra_blueprint.route('/run-boolean-algebra.html', methods=['POST'])
def run_tool():
    # TODO need to check for read permissions on genesets

    form = flask.request.form

    # pull out the selected geneset IDs
    selected_geneset_ids = tc.selected_geneset_ids(form)
    if len(selected_geneset_ids) < 2:
        # TODO add nice error message about missing genesets
        flask.flash("Warning: You need at least 2 genes!")
        return flask.redirect('analyze.html')

    else:
        params = {}
        for tool_param in gwdb.get_tool_params(TOOL_CLASSNAME, True):
            params[tool_param.name] = form[tool_param.name]
            params['at_least'] = form["BooleanAlgebra_min_sets"]

        # TODO include logic for "use emphasis" (see prepareRun2(...) in Analyze.php)

        # insert result for this run
        user_id = None
        if 'user_id' in flask.session:
            user_id = flask.session['user_id']
        else:
            flask.flash("Internal error: user ID missing")
            return flask.redirect('analyze.html')

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

        print params['at_least']

        # render the status page and perform a 303 redirect to the
        # URL that uniquely identifies this run
        new_location = flask.url_for(TOOL_CLASSNAME + '.view_result', task_id=task_id)
        response = flask.make_response(tc.render_tool_pending(async_result, tool))
        response.status_code = 303
        response.headers['location'] = new_location

        return response


@boolean_algebra_blueprint.route('/' + TOOL_CLASSNAME + '-result/<task_id>.html', methods=['GET', 'POST'])
def view_result(task_id):
    # TODO need to check for read permissions on task
    async_result = tc.celery_app.AsyncResult(task_id)
    tool = gwdb.get_tool(TOOL_CLASSNAME)
    if 'user_id' in flask.session:
        user_id = flask.session['user_id']

    if async_result.state in states.PROPAGATE_STATES:
        # TODO render a real descriptive error page not just an exception
        raise Exception('error while processing: ' + tool.name)
    elif async_result.state in states.READY_STATES:
        # results are ready. render the page for the user
        return flask.render_template(
            'tool/BooleanAlgebra_result.html',
            async_result=json.loads(async_result.result),
            tool=tool)
    else:
        # render a page telling their results are pending
        return tc.render_tool_pending(async_result, tool)


@boolean_algebra_blueprint.route('/' + TOOL_CLASSNAME + '-status/<task_id>.json')
def status_json(task_id):
    # TODO need to check for read permissions on task
    async_result = tc.celery_app.AsyncResult(task_id)

    return flask.jsonify({
        'isReady': async_result.state in states.READY_STATES,
        'state': async_result.state,
    })
