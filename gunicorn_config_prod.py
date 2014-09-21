'''
COPYRIGHT 2010 RPS ASA

This file is part of SCI-WMS.

    SCI-WMS is free software: you can redistribute it and/or modify
    it under the terms of the GNU General Public License as published by
    the Free Software Foundation, either version 3 of the License, or
    (at your option) any later version.

    SCI-WMS is distributed in the hope that it will be useful,
    but WITHOUT ANY WARRANTY; without even the implied warranty of
    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
    GNU General Public License for more details.

    You should have received a copy of the GNU General Public License
    along with SCI-WMS.  If not, see <http://www.gnu.org/licenses/>.
'''

import os
import sys
import multiprocessing

worker = "gevent"

if worker is "gevent":
    try:
        #must import gevent monkey patching before threading library
        #http://stackoverflow.com/questions/8774958/keyerror-in-module-threading-after-a-successful-py-test-run
        import gevent.monkey; gevent.monkey.patch_thread()
    except:
        worker="sync"
elif worker is "eventlet":
    try:
        import eventlet
    except:
        worker="sync"
elif worker is "tornado":
    try:
        pass
    except:
        worker="sync"
else:
    # default to basic sync worker if other libs are 
    # not installed
    worker="sync"

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "sciwms.settings.prod")

bind = "127.0.0.1:8080"
workers = multiprocessing.cpu_count() + 1
worker_class = worker
debug = False
timeout = 120
#graceful_timeout = 120
max_requests = 20
keepalive = 5
backlog = 20
access_log_file = os.path.abspath(os.path.join(os.path.dirname(__file__), "sciwms", "logs", "sciwms_gunicorn_access.log"))
error_log_file = os.path.abspath(os.path.join(os.path.dirname(__file__), "sciwms", "logs", "sciwms_gunicorn_error.log"))
loglevel = "warning"


def on_starting(server):
    sys.path.insert(1, os.path.dirname(os.path.realpath(__file__)))
    import sciwms.apps.wms.startup as startup
    startup.run()
