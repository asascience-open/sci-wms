Configure
============

================
Getting Started
================

Refer to this section if you are setting up SCI-WMS for the first time.

***************
The Admin Site
***************

SCI-WMS comes with an administration site built into the server. 
This allows users to add and remove datasets, as well as setup 
and manage groups. (It is essentially the default Django admin 
interface, but it works well for our purposes.)

The admin page can be found on a running instance at **http://server:port/admin** .

The default username is **sciwmsuser**, and the default password is **sciwmspassword**. 
The first thing you should do after getting your server started is to login into the 
administration utility and change the password for this user, or remove the default user and add your 
own.

.. caution::
    Depending on the version of Django you have installed, you 
    may have a problem logging into the admin site, even with 
    the correct password and username. An easy way to solve this 
    problem is to run the following command in a terminal to reset 
    the *sciwmsuser* password using Django's management functionality::
    
        cd sci-wms/src/pywms && python manage.py changepassword sciwmsuser
        
************************
The Openlayers Test Page
************************

The server also comes with a very simple client using *openlayers.js* that can be used for testing 
the GetMap capability of the layers that have been setup in the server. In order for this test page 
to work correctly a number of things must be done. The datasets must be added to the server, the 
dataset *cache* must be initialized (more on this later), and the domain or IP must be added to the 
Sites list in the Admin app.

Add your IP, localhost, or the domain (including ports if applicable) to the Sites list by removing the
default entry and adding your's as a new entry. The "Domain Name" field should be in the following form, omitting "http://" 
and the trailing "/":

    server:port
    
Choose an appropriate nickname for the "Display Name" field.

======================
SCI-WMS Administration
======================

*******************
Adding Datasets
*******************

Here is where we describe how to add datasets.

****************************************
Dataset Cache Initialization & Updating
****************************************

Here is where we describe how to initialize the dataset topology cache, and what updating is.



