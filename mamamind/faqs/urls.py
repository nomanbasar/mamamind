from django.urls import path

from .views import FAQListCreateView, FAQDetailView


urlpatterns = [
    path("", FAQListCreateView.as_view()),
    path("<int:id>/", FAQDetailView.as_view()),
    
]