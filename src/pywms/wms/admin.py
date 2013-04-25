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
    
Created on Sep 6, 2011

@author: ACrosby
'''
#from fvcom_compute.wms.models import Node, Cell, Time, Level
#import fvcom_compute.wms.grid_init_script as gridinit
from django.contrib import admin
#from django.db import models
from pywms.wms.models import Dataset, Server, Group

class DatasetAdmin(admin.ModelAdmin):
    list_display = ('name', 'title', 'keep_up_to_date')
    list_filter = ('keep_up_to_date',)
    
class ServerAdmin(admin.ModelAdmin):
    list_display = ('title', 'keywords', 'contact_person', 'contact_email')
    
class GroupAdmin(admin.ModelAdmin):
    list_display = ('name', 'abstract')
    #list_display = ('datasets',)
    pass

admin.site.register(Dataset, DatasetAdmin)
admin.site.register(Server, ServerAdmin)
admin.site.register(Group, GroupAdmin)

"""
def Update_Geographic_Grid(self, request, queryset):        
    short_description = "Reload grid to populate server database."
    from netCDF4 import Dataset, num2date
    #import datetime
    #import win32com.client
    #import numpy
    url = "http://www.smast.umassd.edu:8080/thredds/dodsC/fvcom/hindcasts/30yr_gom3"
    nc = Dataset(url)
    lat = nc.variables['lat'][:]
    lon = nc.variables['lon'][:]
    latc = nc.variables['latc'][:]
    lonc = nc.variables['lonc'][:]
    nv = nc.variables['nv'][:,:]
    times = nc.variables['time']
    time = num2date(times[:], units=times.units)
    #def MakeCell(a, b, c, d, e, f):
    #    c = Cell(index=a, lat=b, lon=c, node1=d, node2=e, node3=f)
    #    c.save()
    #def MakeNode(a, b, c):
    #    n = Node(index=a, lat=b, lon=c)
    #    n.save()
    #def MakeTime(a, b):
    #    t = Time(date=a, index=b)
    #    t.save()
    
    if queryset.model == Cell:
        queryset.delete()
    #    map(MakeCell, range(len(latc))+1, latc, lonc, nv[0, :], nv[1, :], nv[2, :])
        for i in range(len(latc)):
            c = Cell(index=i+1, lat=latc[i], lon=lonc[i], node1=nv[0, i], node2=nv[1, i], node3=nv[2, i])
            c.save()
    elif queryset.model == Node:
        queryset.delete()
        
        #map(MakeNode, range(len(lat))+1, lat, lon)
        for i in range(len(lat)):
            n = Node(index=i+1, lat=lat[i], lon=lon[i])
            n.save()  
    elif queryset.model == Time:
        queryset.delete()
        #map(MakeTime, time, range(len(time))+1)
        for i,d in enumerate(time):
        #d = datetime.datetime(int(time[i][0]), int(time[i][1]), int(time[i][2]),\
        #    int(time[i][3]), int(time[i][4]), int(time[i][5]))
            t = Time(date=d, index=i+1)
            t.save()
    
    
    

admin.site.register(Node)
admin.site.register(Cell)
admin.site.register(Time)
admin.site.register(Level)
admin.site.add_action(Update_Geographic_Grid)
"""
