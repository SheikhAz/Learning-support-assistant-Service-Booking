from django.urls import path
from . import views

urlpatterns = [
    path('working/', views.working, name='Working'),
    path('v1/bookings/', views.BookingRequestCreateView.as_view(), name='booking-create'),
    path('v1/lsas/search/', views.LSASearchView.as_view(), name='lsa-search'),
]
