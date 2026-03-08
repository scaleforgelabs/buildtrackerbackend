from django.urls import path
from . import user_org_views

urlpatterns = [
    path('<uuid:id>/', user_org_views.get_user_organization, name='get_user_organization'),
    path('<uuid:id>/update/', user_org_views.update_user_organization, name='update_user_organization'),
    path('<uuid:id>/delete/', user_org_views.delete_user_organization, name='delete_user_organization'),
    path('<uuid:id>/usage/', user_org_views.get_user_organization_usage, name='get_user_organization_usage'),
    path('<uuid:id>/usage/calculate/', user_org_views.calculate_user_organization_usage, name='calculate_user_organization_usage'),
    path('<uuid:id>/limits/check/', user_org_views.check_user_organization_limits, name='check_user_organization_limits'),
]