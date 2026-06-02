from django.urls import path

from .views import (
    AdminSubscriptionPlanListCreateView,
    AdminSubscriptionPlanDetailView,
    PublicSubscriptionPlanListView,
    CurrentSubscriptionView,
    SubscriptionHistoryView,
    StripeCheckoutView,
    StripeWebhookView,
    CancelSubscriptionView,
)


urlpatterns = [
    path("admin/plans/", AdminSubscriptionPlanListCreateView.as_view()),
    path("admin/plans/<int:id>/", AdminSubscriptionPlanDetailView.as_view()),

    path("plans/", PublicSubscriptionPlanListView.as_view()),
    path("current/", CurrentSubscriptionView.as_view()),
    path("history/", SubscriptionHistoryView.as_view()),

    path("checkout/", StripeCheckoutView.as_view()),
    path("cancel/", CancelSubscriptionView.as_view()),

    path("stripe/webhook/", StripeWebhookView.as_view()),
]