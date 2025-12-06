# urls.py
from django.urls import path
from .views import DatabaseManagementView

urlpatterns = [
    path('database-management/', DatabaseManagementView.as_view(), name='database_management'),
]