from django.urls import path
from . import views

urlpatterns = [
    path('waitlist/', views.waitlist, name='waitlist'),
]