GeneWeaver 2.0 Setup and Deployment
===================================

Documentation for setting up and deploying the GeneWeaver application.

## System Requirements

GeneWeaver is designed to run on Linux and requires a relatively recent
release. It has been tested on CentOS 6/7 and Red Hat distributions but should
run on other distributions with minimal changes. 

To begin, you'll need the following application dependencies:

RedHat/Fedora/CentOS:

    $ sudo yum install boost boost-devel cairo cairo-devel git graphviz libffi libffi-devel libpqxx libpqxx-devel postgresql-server postgresql-devel python2 rabbitmq-server sphinx
	
Debian/Ubuntu:

	$ sudo apt-get install libboost-all-dev libcairo2 libcairo2-dev git graphviz libffi6 libffi-dev libpqxx-4.0 libpqxx-dev postgresql postgresql-server-dev-9.5 python2.7 rabbitmq-server sphinxsearch

Ensure that the following applications meet these version requirements:

* python == __2.7.*__
* PostgreSQL >= __9.2__
* Graphviz >= __2.3__
* RabbitMQ >= __3.3.*__
* Sphinx >= __2.1.*__


## Configuring PostgreSQL

*This will eventually change to support installing and setting up a skeleton
DB*

In most cases, installing the Postgres server will automatically create a new
postgres user to own and administer the server. If this user does not already
exist, create it:

    $ useradd -d /var/lib/pgsql postgres

Switch to the postgres user account:

    $ sudo su - postgres

Initialize a database cluster to store the database(s):

    $ initdb -D /var/lib/pgsql/data

Start the server:
    
    $ pg_ctl start -D /var/lib/pgsql/data -l logfile

Add a role for future connections. We typically use 'odeadmin':

	$ createuser -s odeadmin

Create a new database. We typically use 'geneweaver':

	$ createdb geneweaver 

### Performance Tuning

The defalut postgres settings are not optimal for dealing with large data sets.
It is advised that you alter memory and cache parameters for a more performant
database, especially if the database will be on its own server or you plan on
utilizing variant annotation functions. 

Copy the lines below to the *end* of the postgres configuration file which 
should be found at `/var/lib/pgsql/data/postgresql.conf`. Each setting is 
commented and you should alter them depending on your needs and available
resources. The settings below were based on a server with 24GB of RAM.

```
## The amount of memory postgres uses for caching data. A good value (assuming
## a separate database server) is 1/4 the available RAM.
shared_buffers = 7168MB

## An estimate of memory available for disk caching and used by the query
## planner. Conservative value is 1/2 the available memory and a more
## aggressive amount is 3/4.
effective_cache_size = 18432MB

## Postgres writes DB transactions in segments of 16MB and everytime a number
## of these files (parameter below) has been written, a checkpoint occurs.
## Doing these frequently is resource intensive and requires a lot of overhead.
## The default is 3 (3 * 16MB = 48MB). A good value for larger datasets is
## anywhere from 32 (512MB) to 256 (4GB). Keep in mind large settings use
## more disk and cause longer recovery times.
checkpoint_segments = 64

## Memory used for in-memory sorts. This setting is used per connection and
## must be set with care. e.g. if it is set to 50MB and 30 users submit 
## queries, you will be using 1.5GB of real memory. If a query involves a 
## merge sort of 8 tables you are using (8 * 50MB = 400MB) of memory. For 
## applications that don't have many users at once, the value can be set 
## higher. Required whenever ORDER BY, DISTINCT, merge joins, or IN is used 
## in a query.
work_mem = 128MB

## Memory used by maintenance operations (e.g. VACUUM, CREATE INDEX). Only a
## single maintenance operation can be executed at a time so this value can be
## much higher than work_mem.
maintenance_work_mem = 512MB
```

If you altered any settings you will need to restart the server. 

    $ pg_ctl restart -D /var/lib/pgsql/data -m fast -l logfile

You can now log out of the postgres user account.

### Dumping the Database

If you already have a copy of the DB, you can skip this section. Dumping a
current instance of the GWDB is done in two parts. First, a copy of the schema
is saved:

    $ pg_dump -U odeadmin -Fc -Cs geneweaver > gw-schema.custom

Next, the data is stored separately. To speed up the restore process, we
exclude two large tables, geneset_jaccard and result: 

    $ pg_dump -U odeadmin -Fc -a -T extsrc.geneset_jaccard -T production.result geneweaver > gw-data.custom

### Restoring from a DB Dump

First restore the schema:
	
	$ pg_restore --no-owner -d geneweaver -U postgres -s gw-schema.custom

Next, restore the data. The -j option specifies the number of cores to use
during the restore process. The --disable-triggers option must be used
otherwise the restore will fail. This will take several hours.

	$ pg_restore -a -d geneweaver -Fc --disable-triggers -j 6 -S odeadmin -U odeadmin gw-data.custom


## Running RabbitMQ

RabbitMQ is the message broker used by Celery to distribute GW tool runs. It
can be run in the background:

	$ rabbitmq-server start &

Or it can be configured to start on boot and daemonized:

	$ chkconfig rabbitmq-server on
	$ /sbin/service rabbitmq-server start

Or daemonization using systemctl: 

	$ systemctl start rabbitmq-server.service


## Configuring Sphinx

A sample sphinx config can be found in the `sample-configs/` directory.
The following example stores the Sphinx config and indices under `/var/lib`. 
Create a folder to hold the Sphinx config file and indices:

	$ sudo mkdir /var/lib/sphinx/geneweaver
	$ sudo cp geneweaver-configs/sphinx/sphinx.conf geneweaver-configs/sphinx/stopwords.txt /var/lib/sphinx/geneweaver

You'll have to make several edits to the sphinx configuration. First, edit the
`source base` section to point to the newly set up Postgres DB.

Both `source geneset_src` and `source geneset_delta_src` sections contain an 
`sql_query` variable that should be edited to support any species that are 
currently found in the database. You'll have to associate the sp_id with a 
common species name.

Under the `index geneset` section, specify the full path of the geneset index
using the `path` variable. This path can be anywhere on the system--we
typically use the sphinx folder. Set the `stopwords` variable to the full
path containing the list of stop words we copied into the sphinx folder above.
Make the same changes under the `index geneset_delta` section too.

Create a 'log' directory; 'chown [sphinxuser]'.

Under the `searchd` section, change the `log`, `query_log`, and
`pid_file` variables to point to full paths for each of those files.

Installing Sphinx will usually create a user to own the search server. If a
sphinx user does not exist, create one:

	$ useradd -d /var/lib/sphinx sphinx

Generate the search indices:

	$ sudo -usphinx indexer --all --config /var/lib/sphinx/geneweaver/sphinx.conf

Start the server as the sphinx user:

	$ sudo -usphinx searchd --config /var/lib/sphinx/geneweaver/sphinx.conf


## Configuring the Python Environment

Python 2.7 should automatically come installed with pip. If it is missing from
your system, bootstrap the installation by downloading and executing the pip
installer:

	$ wget https://bootstrap.pypa.io/get-pip.py && python get-pip.py

### Configuring virtualenv (optional)

Installing virtualenv is optional but it creates an easy to use, stand-alone
environment in which to install python packages and set up the application.
Installation may require sudo privileges. Use pip to install:

	$ pip install virtualenv

Create the GeneWeaver virtual environment. In this example the GeneWeaver
application will reside under `/srv`:

	$ mkdir /srv/geneweaver && cd /srv/geneweaver
	$ virtualenv venv

Activate the environment:

	$ source venv/bin/activate

You can now install any python packages without contaminating the global python
environment. To deactivate the environment use:

	$ deactivate

### Installing Packages

GeneWeaver requires the following python packages:

* cairosvg
* celery
* flask
* flask-admin
* flask-restful
* numpy
* psycopg2
* requests
* urllib3

These can be installed individually using pip (which should also install their
dependencies) or using our requirements.txt which also includes all
dependendent packages. The requirements file can be found in the
`sample-configs` directory.

	$ pip install -r requirements.txt

GeneWeaver also utilizes Sphinx's python API. The python package can no longer
be found in any of the PyPi repos but we have a custom package that can be
retrieved and installed: 

	$ wget http://geneweaver.org/sphinxapi.tar.gz
	$ pip install sphinxapi.tar.gz


## Deploying GeneWeaver

Retrieve the GeneWeaver web application and toolset from the BitBucket repo.
Create a new project folder if you haven't already:

	$ mkdir /srv/geneweaver && cd /srv/geneweaver
	$ git clone https://YOUR_USERNAME@bitbucket.org/geneweaver/website-py.git
	$ git clone https://YOUR_USERNAME@bitbucket.org/geneweaver/tools.git

### Configuring the Web Application

Provided all previous installations were successful, the web application should
be ready to start. First, edit `src/config.py` and change the `CONFIG_PATH`
variable to point to a location to store the GeneWeaver config file.

The config file doesn't need to exist, GeneWeaver will generate one for you to
edit at the path you provide. Run the application once to generate the config
file:

	$ cd website-py
	$ python src/application.py

Edit the newly generated configuration file with the proper application,
celery, database, and sphinx information. In most cases, the default celery
configuration is appropriate.

Create a results directory with 777 permissions. The path will be placed in the config file.

### Configuring the Toolset

Like the web application, edit `tools/config.py` change the `CONFIG_PATH`
variable to point to a location to store the tool config file. From the tools
parent directory, you can run the tools once to generate a default config.
If you installed virtualenv, be user to run the tools from that environment.

	$ celery -A tools.celeryapp worker --loglevel=info

Edit the config with the appropriate information.

If you need to upgrade an older version of the toolset running celery 3.x,
follow these steps:

1. Pull the latest version of the `tools` and `website-py` repos.
2. Upgrade the package requirements using pip `$ pip install -r website-py/sample-configs/requirements.txt`.
3. Restart the tool and web applications.

#### NOTE: The tool table may be incompatible with the celeryapp.py tool list. You may drop the tool table data and reload with ODE-data-only-tool.dump to correct.

#### Compiling the Graph Tools

We use several highly optimized software implementations written in C/C++.
This suite of tools can be found in the `TOOLBOX/` directory and should be
compiled prior to running the toolset written in Python. 

Ensure gcc and other development tools exist on your system. If they are
missing, install them:

	$ sudo yum install gcc g++ make

These tools can be compiled using the "master" makefile located in TOOLBOX.

	$ cd tools/TOOLBOX && make && cd ../..

#### Compiling the Distribution Generator

The distribution generator tool is written in C++ and used to generate a null distribution with which we can use to assess the significance of a jaccard similarity result. It is located in the `tools/cpp_tools` directory. This tool requires two dependencies, `libpqxx` and `libpqxx-devel` which should have been installed earlier. 

This tool will generate a connection to the database and requires you to set the proper connection info. If you have been following this guide, the only connection parameter you should have to change is the database host address. This must be changed in the following files: `distribution_generator.cpp`, `drone.cpp`, and `fileGenerator.cpp`. `fileGenerator.cpp` contains two separate lines where the host address must be changed.

To change all the necessary lines in a single sitting, run the following command in the tools directory:

    $ cd tools
    $ find . -name "*.cpp" -exec sed -i "s/129.62.148.19/DATABASE_IP/g" '{}' \;

Then compile the distribution generator:

    $ cd cpp_tools && make

### Running the Application

GeneWeaver should now be ready to run. Start the tools application from the
parent directory of the tools:

	$ celery -A tools.celeryapp worker --loglevel=info

Start the web application from the website-py directory:

	$ cd website-py
	$ python src/application.py

By default the web app runs on port 5000. You can point your browser to the
host you assigned and you should see the GeneWeaver home page. They application
may require sudo privileges to establish a connection on the given port.

### Serving Application Requests Through Nginx

Handling multiple requests using the Flask application alone may result in some
performance issues. A web server can be used to handle user requests and route
those requests to the web app. Start by installing nginx:

	$ sudo yum install nginx

Serving Flask applications with nginx requires an additional deployment
application such as uWSGI:

	$ pip install uwsgi

Copy the sample uWSGI config, `uwsgi.ini` to an easily accessible 
directory such as `/srv/geneweaver`. Change the `chdir`, `venv`, and `socket`
variables to match your installation directories. If you want to change the
number of worker processes to spawn, and the number of threads per process,
change the `processes` and `threads` variables.

There is a sample nginx config file in the `sample-configs` directory. The
default nginx config, typically found in `/etc/nginx` should only require minor
edits. Copy the custom geneweaver location blocks, `location /` and `location
@geneweaver` from the sample nginx config to the one in `/etc/nginx`. Also
ensure that the `uwsgi_pass` variable points to the correct socket location 
found in the uWSGI config. Start the nginx service:
	
	$ sudo systemctl start nginx

Start uWSGI using the given configuration file:

	$ uwsgi --ini uwsgi.ini

GeneWeaver should now be accessible using just the server name or IP address;
all requests are routed through the default HTTP port (80).

### Managing GeneWeaver with Supervisor (optional)

Supervisor is a system management utility that can be used to control the
GeneWeaver application. Start by installing it:

	$ sudo yum install supervisor

Copy the sample supervisord config from the `sample-configs` directory to a 
directory of your choosing. Here we use the geneweaver application directory:

	$ cp sample-configs/supervisord.conf /srv/geneweaver

Create a folder to store the supervisord logs, or store them in any directory
you wish:

	$ mkdir /srv/geneweaver/supervisord

Now edit the `supervisord.conf` file to match your installation and log
directories. After editing, you can start the supervisor:

	$ sudo supervisord -c /srv/geneweaver/supervisord.conf

To manage your applications use:

	$ sudo supervisorctl -c /srv/geneweaver/supervisord.conf
