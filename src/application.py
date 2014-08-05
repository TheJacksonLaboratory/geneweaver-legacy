import flask
import genesetblueprint
import geneweaverdb

app = flask.Flask(__name__)
app.register_blueprint(genesetblueprint.geneset_blueprint)

# TODO this key must be changed to something secret. Comment out the print message when this is done
print '==================================================='
print 'THIS VERSION OF GENEWEAVER IS NOT SECURE. YOU MUST'
print 'REGENERATE THE SECRET KEY BEFORE DEPLOYMENT. SEE'
print '"How to generate good secret keys" AT'
print 'http://flask.pocoo.org/docs/quickstart/ FOR DETAILS'
print '==================================================='
app.secret_key = '\x91\xe6\x1e \xb2\xc0\xb7\x0e\xd4f\x058q\xad\xb0V\xe1\xf22\xa5\xec\x1e\x905'

# TODO the newsArray should probably be moved to a configuration file
newsArray = [
    (
        "2013: GeneWeaver user publication",
        '''
        <a href="http://www.ncbi.nlm.nih.gov/pubmed/23123364">Potential translational
        targets revealed by linking mouse grooming behavioral phenotypes to gene
        expression using public databases</a> Andrew Roth, Evan J. Kyzar, Jonathan Cachat,
        Adam Michael Stewart, Jeremy Green, Siddharth Gaikwad, Timothy P. O'Leary,
        Boris Tabakoff, Richard E. Brown, Allan V. Kalueff. Progress in Neuro-Psychopharmacology
        & Biological Psychiatry 40:313-325.
        '''
    ),
    (
        "2013: GeneWeaver user publication (Includes Deposited Data)",
        '''
        <a href="http://www.ncbi.nlm.nih.gov/pubmed/23329330">Mechanistic basis of infertility
        of mouse intersubspecific hybrids</a> Bhattacharyya T, Gregorova S, Mihola O, Anger M,
        Sebestova J, Denny P, Simecek P, Forejt J. PNAS 2013 110 (6) E468-E477.
        '''
    ),
    (
        "2012: GeneWeaver Publication",
        '''
        <a href="http://www.ncbi.nlm.nih.gov/pubmed/23195309">Cross species integration of
        functional genomics experiments.</a>Jay, JJ. Int Rev Neurobiol 104:1-24.
        '''
    ),
    (
        "Oct 2012: GeneWeaver user publication",
        '''
        <a href="http://www.ncbi.nlm.nih.gov/pubmed/22961259">The Mammalian Phenotype Ontology
        as a unifying standard for experimental and high-throughput phenotyping data.</a>
        Smith CL, Eppig JT. Mamm Genome. 23(9-10):653-68
        '''
    ),
]


# the context processor will inject global variables for us so
# that we can refer to them from our flask templates
@app.context_processor
def inject_globals():
    # TODO you need to care about escaping
    global_map = {
        'newsArray': newsArray
    }

    # lookup the current user
    session = flask.session
    user_id = session.get('user_id')
    print 'user ID in session:', user_id
    if user_id:
        if flask.request.remote_addr == session.get('remote_addr'):
            global_map['user'] = geneweaverdb.get_user(user_id)
        else:
            # if IP addresses don't match we're going to reset the session for
            # a bit of extra safety
            _logout(session)

    return global_map


def _logout(session):
    try:
        del session['user_id']
    except KeyError:
        pass

    try:
        del session['remote_addr']
    except KeyError:
        pass


def _form_login():
    user = None
    _logout(flask.session)

    form = flask.request.form
    if 'usr_email' in form:
        # TODO deal with login failure
        user = geneweaverdb.authenticate_user(form['usr_email'], form['usr_password'])
        if user is not None:
            flask.session['user_id'] = user.user_id
            remote_addr = flask.request.remote_addr
            if remote_addr:
                flask.session['remote_addr'] = remote_addr

    flask.g.user = user
    return user


@app.route('/logout.json', methods=['GET', 'POST'])
def json_logout():
    _logout(flask.session)
    return flask.jsonify({'success': True})


@app.route('/login.json', methods=['POST'])
def json_login():
    print flask.request.json
    print flask.request.form
    json_result = dict()
    user = _form_login()
    if user is None:
        json_result['success'] = False
    else:
        json_result['success'] = True
        json_result['usr_first_name'] = user.first_name
        json_result['usr_last_name'] = user.last_name
        json_result['usr_email'] = user.email

    return flask.jsonify(json_result)


@app.route('/analyze.html')
def render_analyze():
    return flask.render_template('analyze.html')


@app.route('/search.html')
def render_search():
    return flask.render_template('search.html')


@app.route('/manage.html')
def render_manage():
    return flask.render_template('my_genesets.html')


@app.route('/help.html')
def render_help():
    return flask.render_template('help.html')


@app.route('/index.html', methods=['GET', 'POST'])
@app.route('/', methods=['GET', 'POST'])
def render_home():
    return flask.render_template('index.html')

if __name__ == '__main__':
    app.debug = True
    app.run()
