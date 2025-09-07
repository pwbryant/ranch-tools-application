# urls.py
from django.urls import path
from .views import DatabaseManagementView

urlpatterns = [
    path('database-management/', DatabaseManagementView.as_view(), name='database_management'),
    # Or use the FormView version:
    # path('database-management/', DatabaseManagementFormView.as_view(), name='database_management'),
]