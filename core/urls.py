from django.urls import path
from . import views
from rest_framework_simplejwt.views import TokenRefreshView

urlpatterns = [
    path('', views.index, name='index'),
    path('cached-data/', views.cached_data, name='cached_data'),
    path('trigger-task/', views.trigger_task, name='trigger_task'),
    path('auth/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
]
