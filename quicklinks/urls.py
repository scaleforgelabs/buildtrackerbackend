from django.urls import path
from . import views

urlpatterns = [
    path('users/<uuid:userId>/quick-links/', views.user_quick_links, name='user_quick_links'),
    path('users/<uuid:userId>/quick-links/<uuid:id>/', views.quick_link_detail, name='quick_link_detail'),
    path('users/<uuid:userId>/quick-links/reorder/', views.reorder_quick_links, name='reorder_quick_links'),
    path('workspaces/<uuid:workspaceId>/quick-links/shared/', views.workspace_shared_links, name='workspace_shared_links'),
    path('users/<uuid:userId>/recent-items/', views.user_recent_items, name='user_recent_items'),
]