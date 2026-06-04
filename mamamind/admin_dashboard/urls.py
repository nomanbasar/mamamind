from django.urls import path

from .views import AdminDashboardOverviewView, AdminUserListView

urlpatterns = [
    path("overview/", AdminDashboardOverviewView.as_view()),
    path("users/", AdminUserListView.as_view()),
]