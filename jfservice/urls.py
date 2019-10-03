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
    url(r'^calculator/$', views.calculator, name='calculator'),
    url(r'^contract_list/$', views.contract_list, name='contract_list'),
]