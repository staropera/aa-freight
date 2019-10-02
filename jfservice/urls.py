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
]