import json
import uuid
import os
from tools.JSON2TSV import JSON2TSV
import celery.states as states
import flask

import config
import geneweaverdb as gwdb
import tools.toolcommon as tc


TOOL_CLASSNAME = 'SimiliarVariantSet'
similiar_variantset_blueprint = flask.Blueprint(TOOL_CLASSNAME, __name__)

@similiar_variantset_blueprint.route('/run-similiar-variant-set.html', methods=['POST'])
def run_tool():
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
    '''
    async_result = tc.celery_app.send_task(
        tc.fully_qualified_name(TOOL_CLASSNAME),
        kwargs={
            'gsids': selected_geneset_ids,
            'output_prefix': task_id,
            'params': params,
        },
        task_id=task_id)
    '''