from django.conf.urls import url
from . import views

app_name = 'jfservice'

urlpatterns = [
    url(r'^$', views.index, name='index'),
    url(
        r'^create_or_update_service/$', 
        views.create_or_update_service, 
        name='create_or_update_service'
    ),
    url(r'^add_location/$', views.add_location, name='add_location'),
    url(r'^add_location_2/$', views.add_location_2, name='add_location_2'),
    url(r'^calculator/$', views.calculator, name='calculator'),
    url(r'^contract_list/$', views.contract_list, name='contract_list'),    
    url(r'^calculator_pricing_info/(?P<pricing_pk>[0-9]+)/$', views.calculator_pricing_info, name='calculator_pricing_info'),
]