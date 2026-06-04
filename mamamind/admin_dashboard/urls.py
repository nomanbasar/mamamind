from django.urls import path

from .views import AdminDashboardOverviewView, AdminUserListView, AdminSubscriptionListView

urlpatterns = [
    path("dashboard/overview/", AdminDashboardOverviewView.as_view()),
    path("users/", AdminUserListView.as_view()),
    path("subscriptions/", AdminSubscriptionListView.as_view()),
]