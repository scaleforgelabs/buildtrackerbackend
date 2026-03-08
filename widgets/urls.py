from django.urls import path
from . import views

urlpatterns = [
    path('users/<uuid:userId>/dashboard/widgets', views.get_user_dashboard_widgets, name='user_dashboard_widgets'),
    path('workspaces/<uuid:workspaceId>/dashboard/widgets/data/<str:widgetType>', views.get_workspace_widget_data, name='get_workspace_widget_data'),
]
