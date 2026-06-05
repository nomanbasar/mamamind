from django.urls import path

from .views import AdminDashboardOverviewView, AdminUserListView, AdminSubscriptionListView, AdminRevenueView, AdminAnalyticsView

urlpatterns = [
    path("dashboard/overview/", AdminDashboardOverviewView.as_view()),
    path("users/", AdminUserListView.as_view()),
    path("subscriptions/", AdminSubscriptionListView.as_view()),
    path("revenue/", AdminRevenueView.as_view()),
    path("analytics/", AdminAnalyticsView.as_view()),
]