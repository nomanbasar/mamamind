from django.urls import path

from .views import (
    ReminderListCreateView,
    ReminderDetailView,
    ReminderOwnerListView,
)

urlpatterns = [
    path("", ReminderListCreateView.as_view()),
    path("owners/", ReminderOwnerListView.as_view()),
    path("<int:reminder_id>/", ReminderDetailView.as_view()),
]