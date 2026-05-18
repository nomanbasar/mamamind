from django.urls import path

from .views import (
    ContactMessageCreateView,
    ContactMessageListView,
    ContactMessageDetailView,
)


urlpatterns = [
    path("messages/", ContactMessageCreateView.as_view()),
    path("admin/messages/", ContactMessageListView.as_view()),
    path("admin/messages/<int:id>/", ContactMessageDetailView.as_view()),
]