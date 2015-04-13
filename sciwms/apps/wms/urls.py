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

from django.conf.urls import patterns, url

urlpatterns = patterns( '',

                        url(r'^index', 'sciwms.apps.wms.views.index', name='index'),
                        url(r'^$', 'sciwms.apps.wms.views.index'),

                        url(r'^documentation', 'sciwms.apps.wms.views.documentation', name='documentation'),
                        url(r'^demo', 'sciwms.apps.wms.views.demo', name='demo'),

                        # JSONish GetCapabilities
                        url(r'^datasets$',  'sciwms.apps.wms.views.datasets'),

                        url(r'^login', 'sciwms.apps.wms.views.login', name='login'),
                        url(r'^logout', 'sciwms.apps.wms.views.logout', name='logout'),

                        url(r'^add', 'sciwms.apps.wms.views.add', name='add'),

                        #url(r'^datasets/(?P<dataset>.*)', 'sciwms.apps.wms.views.wms', name="dataset"),
                        #url(r'^refresh/(?P<dataset>.*)', 'sciwms.apps.wms.views.refresh', name='refresh'),
                        #url(r'^remove/(?P<dataset>.*)', 'sciwms.apps.wms.views.remove', name='remove'),

                        url(r'(?P<dataset>.*)/edit', 'sciwms.apps.wms.views.edit', name='edit'),
                        url(r'(?P<dataset>.*)/refresh', 'sciwms.apps.wms.views.refresh', name='refresh'),
                        url(r'(?P<dataset>.*)/remove', 'sciwms.apps.wms.views.remove', name='remove'),
                        url(r'(?P<dataset>.*)', 'sciwms.apps.wms.views.wms', name="dataset"),

                        # Datasets
                        #url(r'^datasets$',  'sciwms.apps.wms.views.datasets'),
                        #url(r'^datasets/$', 'sciwms.apps.wms.views.datasets'),
                        #url(r'^datasets/(?P<dataset>.*)/update', 'sciwms.apps.wms.views.update_dataset', name="update_dataset"),
                        
                        # Colormaps
                        #url(r'^colormaps', 'sciwms.apps.wms.views.colormaps'),

                        #url(r'^add_dataset', 'sciwms.apps.wms.views.add'),  # This is a POST based view
                        #url(r'^add_to_group', 'sciwms.apps.wms.views.add_to_group'),
                        #url(r'^remove_dataset', 'sciwms.apps.wms.views.remove'),
                        #url(r'^remove_from_group', 'sciwms.apps.wms.views.remove_from_group'),

                        #url(r'^groups/(?P<group>.*)/', 'sciwms.apps.wms.views.groups'),
                        #url(r'^groups/(?P<group>.*)', 'sciwms.apps.wms.views.groups')
                    )
