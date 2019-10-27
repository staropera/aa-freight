from django.conf.urls import url
from . import views

app_name = 'freight'

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
    url(r'^calculator/(?P<pricing_pk>[0-9]+)/$', views.calculator, name='calculator'),    
    
    url(r'^contract_list_active/$', views.contract_list_active, name='contract_list_active'),
    url(r'^contract_list_user/$', views.contract_list_user, name='contract_list_user'),
    url(r'^contract_list_data/(?P<category>.+)/$', views.contract_list_data, name='contract_list_data'),    
]