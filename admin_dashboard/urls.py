from django.urls import path
from . import views

urlpatterns = [
    path('stats/', views.admin_stats_view, name='admin-stats'),
    path('users/', views.admin_users_view, name='admin-users'),
    path('users/<uuid:user_id>/role/', views.admin_update_user_role_view, name='admin-update-user-role'),
    path('users/<uuid:user_id>/delete/', views.admin_delete_user_view, name='admin-delete-user'),
    path('users/<uuid:user_id>/suspend/', views.admin_suspend_user_view, name='admin-suspend-user'),
    path('workspaces/', views.admin_workspaces_view, name='admin-workspaces'),
    path('analytics/', views.admin_analytics_view, name='admin-analytics'),
    path('subscriptions/', views.admin_subscriptions_view, name='admin-subscriptions'),
    path('newsletter/', views.admin_newsletter_view, name='admin-newsletter'),
    # Content Hub
    path('content/', views.admin_content_list_view, name='admin-content-list'),
    path('content/<int:post_id>/', views.admin_content_update_view, name='admin-content-update'),
    # Sales CRM
    path('leads/', views.admin_leads_list_view, name='admin-leads-list'),
    path('leads/<int:lead_id>/', views.admin_lead_update_view, name='admin-lead-update'),
    # Lead Contacts
    path('leads/<int:lead_id>/contacts/', views.admin_lead_contacts_list_view, name='admin-lead-contacts-list'),
    path('leads/<int:lead_id>/contacts/add/', views.admin_lead_contact_create_view, name='admin-lead-contact-create'),
    path('leads/<int:lead_id>/contacts/<int:contact_id>/', views.admin_lead_contact_detail_view, name='admin-lead-contact-detail'),
    path('leads/<int:lead_id>/contacts/<int:contact_id>/email/', views.admin_send_contact_email_view, name='admin-contact-email'),
]
