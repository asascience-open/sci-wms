Deployment
==========


============
Quick Start
============

To start sci-wms with the Django development server on port :7000, type the following commands::

    cd sci-wms/src/pywms && python manage.py runserver 0.0.0.0:7000
    
This server is not considered secure for production implementations, 
and it is recommended you use an alternative wsgi server like *Gunicorn*.

=========================
Using the Gunicorn Server
=========================

There are many ways to serve Django based web applications like SCI-WMS. 
We recommend using Gunicorn and proxying to the server with a production 
grade HTTP server like *nginx*. SCI-WMS comes with example configuration 
files for nginx and Gunicorn.

To start SCI-WMS with the Gunicorn WSGI server use the following commands 
in the terminal::

    gunicorn_django -c sci-wms/src/pywms/config_public.py sci-wms/src/pywms/settings.py
    
===================
Proxying with nginx
===================

A generic nginx proxy configuration can be found in *sci-wms/deploy/nginx.conf*. 
Edit the configuration file to suit your deployment needs, and then run the following to symlink 
the configuration into nginx's enabled websites::

    sudo ln -s /full/path/to/sci-wms/deploy/nginx.conf /etc/nginx/sites-enabled/sci-wms.conf
    
Restart the nginx server for the changes to take effect::

    sudo /etc/init.d/nginx restart
    
=======================
Management with Upstart
=======================

If you are on Ubuntu or a similar distro, you can have the *Upstart* utility manage the SCI-WMS/Gunicorn server. 
An example Upstart configuration can be found in *sci-wms/deploy/upstart.conf*. Place the completed configuration 
into the */etc/init/sci-wms.conf*, and you will be able to use the following commands to manage the server::

    start sci-wms   #start the server
    stop sci-wms    #stop the server
    restart sci-wms #restart the server

===========================
Management with Supervisord
===========================

More to come...

