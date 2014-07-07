"""
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

This file demonstrates writing tests using the unittest module. These will pass
when you run "manage.py test".

Replace this with more appropriate tests for your application.
"""

import os
from time import sleep

from django.test import TestCase
from django.conf import settings
from django.contrib.auth.models import User
import django.contrib.auth.hashers as hashpass

from sciwms.apps.wms.models import Dataset, Group, Server
import sciwms.libs.data.caching

resource_path = os.path.join(settings.PROJECT_ROOT, 'apps', 'wms', 'resources')
cache_path = os.path.join(settings.PROJECT_ROOT, 'apps', 'wms', "topology")
if not os.path.exists(cache_path):
    os.makedirs(cache_path)

def remove_cache(name):
    try:
        os.unlink(os.path.join(cache_path, name+".nc"))
        os.unlink(os.path.join(cache_path, name+".idx"))
        os.unlink(os.path.join(cache_path, name+".dat"))
    except:
        pass

def wait_on_cache(name):
    c = 0
    while( not (
        os.path.exists(os.path.join(cache_path, name+".nc")) and
        os.path.exists(os.path.join(cache_path, name+".idx")) and
        os.path.exists(os.path.join(cache_path, name+".dat")))
    ) and (c < 10):
        sleep(3)
        print "Waiting on topology cache..."
        c += 1
        pass

def add_server():
    s = Server.objects.create()
    s.save()

def add_dataset(filename, name):
    d = Dataset.objects.create(
        name = name,
        description = 'test description',
        uri = os.path.join(resource_path, filename))
    d.save()
    sciwms.libs.data.caching.update_dataset_cache(d)

def add_user():
    u = User(username="testuser",
             first_name="test",
             last_name="user",
             email="test@yser.comn",
             password=hashpass.make_password("test"),
             is_active=True,
             is_superuser=True,
            )
    u.save()


class SimpleTest(TestCase):
    def test_basic_addition(self):
        """
        Tests that 1 + 1 always equals 2.
        """
        self.assertEqual(1 + 1, 2)

    def test_index(self):
        add_server()
        response = self.client.get('/index.html')
        self.assertEqual(response.status_code, 200)


class TestUgrid(TestCase):

    def setUp(self):
        add_dataset("TEST_FVCOM_MASSBAY.nc", 'TEST_FVCOM_MASSBAY_nc')
        wait_on_cache('TEST_FVCOM_MASSBAY_nc')

    def tearDown(self):
        remove_cache('TEST_FVCOM_MASSBAY_nc')

    def test_scalar(self):
        response = self.client.get('http://localhost:8080/wms/TEST_FVCOM_MASSBAY_nc?service=WMS&request=GetMap&version=1.1.1&layers=sea_water_temperature&styles=contourf_average_jet_0.0_40.0_grid_False&format=image/png&transparent=true&height=256&width=256&srs=EPSG:3857&bbox=-7885855.334125064,5185487.998866358,-7866287.454884058,5205055.878107364')
        self.assertEqual(response.status_code, 200)

    def test_getCaps(self):
        response = self.client.get('http://localhost:8080/wms/TEST_FVCOM_MASSBAY_nc?request=GetCapabilities', HTTP_HOST='example.com')
        self.assertEqual(response.status_code, 200)

'''
TODO: make NASA_SCB20111015.nc CF-compliant (standard_name)
class TestCgrid(TestCase):

    def setUp(self):
        add_dataset("NASA_SCB20111015.nc", 'NASA_SCB20111015_nc')
        wait_on_cache('NASA_SCB20111015_nc')

    def tearDown(self):
        remove_cache('NASA_SCB20111015_nc')

    def test_scalar(self):
        response = self.client.get('http://localhost:8080/wms/NASA_SCB20111015_nc?service=WMS&request=GetMap&version=1.1.1&layers=sea_water_temperature&styles=contourf_average_jet_0.0_40.0_grid_False&format=image/png&transparent=true&height=256&width=256&srs=EPSG:3857&bbox=-7885855.334125064,5185487.998866358,-7866287.454884058,5205055.878107364')
        self.assertEqual(response.status_code, 200)

    def test_getCaps(self):
        response = self.client.get('http://localhost:8080/wms/NASA_SCB20111015_nc?request=GetCapabilities', HTTP_HOST='example.com')
        self.assertEqual(response.status_code, 200)
'''
