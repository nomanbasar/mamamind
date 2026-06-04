from django.urls import path

from .views import AdminDashboardOverviewView, AdminUserListView

urlpatterns = [
    path("dashboard/overview/", AdminDashboardOverviewView.as_view()),
    path("users/", AdminUserListView.as_view()),
]