from django.urls import path
from . import views

urlpatterns = [
    path('<uuid:workspaceId>/wiki/documents/', views.wiki_documents, name='wiki_documents'),
    path('<uuid:workspaceId>/wiki/documents/<uuid:id>/', views.wiki_document_detail, name='wiki_document_detail'),
    path('<uuid:workspaceId>/wiki/search/', views.wiki_search, name='wiki_search'),
]