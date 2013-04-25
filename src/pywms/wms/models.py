'''
COPYRIGHT 2010 Alexander Crosby

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

from django.db import models
from netCDF4 import Dataset

class Dataset(models.Model):
    uri             = models.CharField(max_length=1000)
    name            = models.CharField(max_length=200, help_text="Name/ID to use. No special characters or spaces ('_','0123456789' and A-Z are allowed).")
    title           = models.CharField(max_length=200, help_text="Human Readable Title")
    abstract        = models.CharField(max_length=2000, help_text="Short Description of Dataset")
    keep_up_to_date = models.BooleanField()
    #test_date       = models.CharField(max_length=200, help_text="Optional (YYYY-MM-DDTHH:mm:ss)", blank=True)
    test_layer      = models.CharField(max_length=200, help_text="Optional", blank=True)
    test_style      = models.CharField(max_length=200, help_text="Optional", blank=True)
    #groups = models.ManyToManyField(Group)
    def __unicode__(self):
        return self.name
    
class Group(models.Model):
    name = models.CharField(max_length=200)
    abstract = models.CharField(max_length=2000, blank=True, help_text="Short Description of the Group")
    datasets = models.ManyToManyField(Dataset, blank=True, help_text="Choose the datasets to add to this group, or create a dataset to add to this group")
    def __unicode__(self):
        return self.name
    
class Server(models.Model):
    # Server
    title    = models.CharField(max_length=1000, help_text="Server Title", blank=True)
    abstract = models.CharField(max_length=2000, help_text="Server Abstract", blank=True)
    keywords = models.CharField(max_length=2000, help_text="Comma Separated List of Keywords", blank=True)
    
    # Contact
    contact_person          = models.CharField(max_length=1000, help_text="Person to Contact (Optional)", blank=True)
    contact_organization    = models.CharField(max_length=1000, help_text="Contact Organization (Optional)", blank=True)
    contact_position        = models.CharField(max_length=1000, help_text="Contact Position (Optional)", blank=True)
    contact_street_address  = models.CharField(max_length=1000, help_text="Street Address (Optional)", blank=True)
    contact_city_address    = models.CharField(max_length=1000, help_text="Address: City (Optional)", blank=True)
    contact_state_address   = models.CharField(max_length=1000, help_text="Address: State or Providence (Optional)", blank=True)
    contact_code_address    = models.CharField(max_length=1000, help_text="Address: Postal Code (Optional)", blank=True)
    contact_country_address = models.CharField(max_length=1000, help_text="Address: Country (Optional)", blank=True)
    contact_telephone       = models.CharField(max_length=1000, help_text="Contact Telephone Number (Optional)", blank=True)
    contact_email           = models.CharField(max_length=1000, help_text="Contact Email Address (Optional)", blank=True)

    


