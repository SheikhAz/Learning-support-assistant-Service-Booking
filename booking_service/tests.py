import threading
from datetime import timedelta
from unittest.mock import patch

import requests
from django.db import connection
from django.test import TestCase, TransactionTestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from booking_service import services
from booking_service.exceptions import (
    ExternalVerificationFailed,
    ExternalVerificationUnavailable,
    InvalidBookingTimeRange,
    LSAInactive,
    LSANotFound,
    OverlappingBooking,
    ParentNotFound,
)
from booking_service.models import BookingRequest, LSAProfile, Parent


def _future(hours_from_now, minutes=0):
    return timezone.now().replace(microsecond=0) + timedelta(hours=hours_from_now, minutes=minutes)


class ServiceLayerBookingTests(TestCase):
    def setUp(self):
        self.parent = Parent.objects.create(name="Priya Shah", email="priya@example.com", phone="9876543210")
        self.lsa = LSAProfile.objects.create(
            name="Arjun Mehta", email="arjun@example.com", skills="yoga,strength", experience=5,
        )

    @override_settings(ENABLE_EXTERNAL_VERIFICATION=False)
    def test_successful_booking_creation(self):
        start = _future(1)
        end = _future(2)
        booking = services.create_booking(
            parent_id=self.parent.id, lsa_id=self.lsa.id, start_time=start, end_time=end,
        )
        self.assertEqual(booking.status, BookingRequest.Status.PENDING)
        self.assertEqual(BookingRequest.objects.count(), 1)

    @override_settings(ENABLE_EXTERNAL_VERIFICATION=False)
    def test_invalid_time_range_rejected(self):
        start = _future(2)
        end = _future(1)
        with self.assertRaises(InvalidBookingTimeRange):
            services.create_booking(
                parent_id=self.parent.id, lsa_id=self.lsa.id, start_time=start, end_time=end,
            )
        self.assertEqual(BookingRequest.objects.count(), 0)

    @override_settings(ENABLE_EXTERNAL_VERIFICATION=False)
    def test_parent_not_found(self):
        with self.assertRaises(ParentNotFound):
            services.create_booking(
                parent_id=999999, lsa_id=self.lsa.id, start_time=_future(1), end_time=_future(2),
            )

    @override_settings(ENABLE_EXTERNAL_VERIFICATION=False)
    def test_lsa_not_found(self):
        with self.assertRaises(LSANotFound):
            services.create_booking(
                parent_id=self.parent.id, lsa_id=999999, start_time=_future(1), end_time=_future(2),
            )

    @override_settings(ENABLE_EXTERNAL_VERIFICATION=False)
    def test_inactive_lsa_rejected(self):
        self.lsa.is_active = False
        self.lsa.save(update_fields=["is_active"])
        with self.assertRaises(LSAInactive):
            services.create_booking(
                parent_id=self.parent.id, lsa_id=self.lsa.id, start_time=_future(1), end_time=_future(2),
            )

    @override_settings(ENABLE_EXTERNAL_VERIFICATION=False)
    def test_overlapping_booking_rejected(self):
        services.create_booking(
            parent_id=self.parent.id, lsa_id=self.lsa.id,
            start_time=_future(1), end_time=_future(2),
        )
        with self.assertRaises(OverlappingBooking):
            services.create_booking(
                parent_id=self.parent.id, lsa_id=self.lsa.id,
                start_time=_future(1, minutes=30), end_time=_future(2, minutes=30),
            )
        self.assertEqual(BookingRequest.objects.count(), 1)

    @override_settings(ENABLE_EXTERNAL_VERIFICATION=False)
    def test_back_to_back_booking_accepted(self):
        services.create_booking(
            parent_id=self.parent.id, lsa_id=self.lsa.id,
            start_time=_future(1), end_time=_future(2),
        )
        # Starts exactly when the first one ends -> not an overlap.
        booking2 = services.create_booking(
            parent_id=self.parent.id, lsa_id=self.lsa.id,
            start_time=_future(2), end_time=_future(3),
        )
        self.assertIsNotNone(booking2.pk)
        self.assertEqual(BookingRequest.objects.count(), 2)

    @override_settings(ENABLE_EXTERNAL_VERIFICATION=False)
    def test_cancelled_booking_does_not_block_slot(self):
        existing = services.create_booking(
            parent_id=self.parent.id, lsa_id=self.lsa.id,
            start_time=_future(1), end_time=_future(2),
        )
        existing.status = BookingRequest.Status.CANCELLED
        existing.save(update_fields=["status"])

        # Same slot should now be bookable again.
        booking2 = services.create_booking(
            parent_id=self.parent.id, lsa_id=self.lsa.id,
            start_time=_future(1), end_time=_future(2),
        )
        self.assertIsNotNone(booking2.pk)


class ExternalVerificationServiceTests(TestCase):
    def setUp(self):
        self.parent = Parent.objects.create(name="Priya Shah", email="priya2@example.com", phone="9876543211")
        self.lsa = LSAProfile.objects.create(
            name="Neha Kapoor", email="neha@example.com", skills="physio", experience=3,
        )

    def _make_response(self, status_code=200, json_data=None, raise_json_error=False):
        class FakeResponse:
            def __init__(self):
                self.status_code = status_code

            def json(self):
                if raise_json_error:
                    raise ValueError("invalid json")
                return json_data or {}

        return FakeResponse()

    @override_settings(ENABLE_EXTERNAL_VERIFICATION=True)
    @patch("booking.integrations.verification_service.requests.post")
    def test_external_verification_success(self, mock_post):
        mock_post.return_value = self._make_response(200, {"verified": True, "reference_id": "ref-1"})
        booking = services.create_booking(
            parent_id=self.parent.id, lsa_id=self.lsa.id, start_time=_future(1), end_time=_future(2),
        )
        self.assertIsNotNone(booking.pk)
        mock_post.assert_called_once()

    @override_settings(ENABLE_EXTERNAL_VERIFICATION=True)
    @patch("booking.integrations.verification_service.requests.post")
    def test_external_verification_rejected(self, mock_post):
        mock_post.return_value = self._make_response(200, {"verified": False, "reason": "not eligible"})
        with self.assertRaises(ExternalVerificationFailed):
            services.create_booking(
                parent_id=self.parent.id, lsa_id=self.lsa.id, start_time=_future(1), end_time=_future(2),
            )
        self.assertEqual(BookingRequest.objects.count(), 0)

    @override_settings(ENABLE_EXTERNAL_VERIFICATION=True)
    @patch("booking.integrations.verification_service.requests.post")
    def test_external_verification_timeout(self, mock_post):
        mock_post.side_effect = requests.exceptions.Timeout("timed out")
        with self.assertRaises(ExternalVerificationUnavailable):
            services.create_booking(
                parent_id=self.parent.id, lsa_id=self.lsa.id, start_time=_future(1), end_time=_future(2),
            )

    @override_settings(ENABLE_EXTERNAL_VERIFICATION=True)
    @patch("booking.integrations.verification_service.requests.post")
    def test_external_verification_connection_error(self, mock_post):
        mock_post.side_effect = requests.exceptions.ConnectionError("refused")
        with self.assertRaises(ExternalVerificationUnavailable):
            services.create_booking(
                parent_id=self.parent.id, lsa_id=self.lsa.id, start_time=_future(1), end_time=_future(2),
            )

    @override_settings(ENABLE_EXTERNAL_VERIFICATION=True)
    @patch("booking.integrations.verification_service.requests.post")
    def test_external_verification_non_2xx_response(self, mock_post):
        mock_post.return_value = self._make_response(500, {})
        with self.assertRaises(ExternalVerificationUnavailable):
            services.create_booking(
                parent_id=self.parent.id, lsa_id=self.lsa.id, start_time=_future(1), end_time=_future(2),
            )

    @override_settings(ENABLE_EXTERNAL_VERIFICATION=True)
    @patch("booking.integrations.verification_service.requests.post")
    def test_external_verification_invalid_json(self, mock_post):
        mock_post.return_value = self._make_response(200, raise_json_error=True)
        with self.assertRaises(ExternalVerificationUnavailable):
            services.create_booking(
                parent_id=self.parent.id, lsa_id=self.lsa.id, start_time=_future(1), end_time=_future(2),
            )

    @override_settings(ENABLE_EXTERNAL_VERIFICATION=True)
    @patch("booking.integrations.verification_service.requests.post")
    def test_external_verification_missing_verified_field(self, mock_post):
        mock_post.return_value = self._make_response(200, {"reference_id": "ref-2"})
        with self.assertRaises(ExternalVerificationUnavailable):
            services.create_booking(
                parent_id=self.parent.id, lsa_id=self.lsa.id, start_time=_future(1), end_time=_future(2),
            )


class LSASearchTests(TestCase):
    def setUp(self):
        self.parent = Parent.objects.create(name="Ravi Kumar", email="ravi@example.com", phone="9876500000")
        self.yoga_lsa = LSAProfile.objects.create(
            name="Yoga LSA", email="yoga@example.com", skills="yoga,meditation", experience=4,
        )
        self.strength_lsa = LSAProfile.objects.create(
            name="Strength LSA", email="strength@example.com", skills="strength,crossfit", experience=6,
        )
        self.inactive_lsa = LSAProfile.objects.create(
            name="Inactive LSA", email="inactive@example.com", skills="yoga", experience=2, is_active=False,
        )

    def test_skill_search_filters_correctly(self):
        results = list(services.search_lsas(skill="yoga"))
        self.assertIn(self.yoga_lsa, results)
        self.assertNotIn(self.strength_lsa, results)
        # Inactive LSAs are excluded regardless of skill match.
        self.assertNotIn(self.inactive_lsa, results)

    def test_unavailable_lsa_excluded_from_availability_search(self):
        start = _future(1)
        end = _future(2)
        BookingRequest.objects.create(
            parent=self.parent, lsa=self.yoga_lsa, start_time=start, end_time=end,
        )
        results = list(services.search_lsas(start_time=start, end_time=end))
        self.assertNotIn(self.yoga_lsa, results)
        self.assertIn(self.strength_lsa, results)

    def test_search_has_no_n_plus_one_queries(self):
        for i in range(10):
            LSAProfile.objects.create(
                name=f"LSA {i}", email=f"lsa{i}@example.com", skills="strength", experience=1,
            )

        start = _future(1)
        end = _future(2)
        with CaptureQueriesContext(connection) as ctx:
            list(services.search_lsas(start_time=start, end_time=end))
        self.assertEqual(len(ctx.captured_queries), 1)


class BookingAPITests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.parent = Parent.objects.create(name="Sana Iyer", email="sana@example.com", phone="9876511111")
        self.lsa = LSAProfile.objects.create(
            name="Karan Bose", email="karan@example.com", skills="nutrition", experience=2,
        )

    @override_settings(ENABLE_EXTERNAL_VERIFICATION=False)
    def test_create_booking_endpoint_success(self):
        payload = {
            "parent": self.parent.id,
            "lsa": self.lsa.id,
            "start_time": _future(1).isoformat(),
            "end_time": _future(2).isoformat(),
        }
        response = self.client.post("/api/v1/bookings/", payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    @override_settings(ENABLE_EXTERNAL_VERIFICATION=False)
    def test_create_booking_endpoint_parent_not_found_returns_404(self):
        payload = {
            "parent": 999999,
            "lsa": self.lsa.id,
            "start_time": _future(1).isoformat(),
            "end_time": _future(2).isoformat(),
        }
        response = self.client.post("/api/v1/bookings/", payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    @override_settings(ENABLE_EXTERNAL_VERIFICATION=False)
    def test_create_booking_endpoint_overlap_returns_409(self):
        payload = {
            "parent": self.parent.id,
            "lsa": self.lsa.id,
            "start_time": _future(1).isoformat(),
            "end_time": _future(2).isoformat(),
        }
        self.client.post("/api/v1/bookings/", payload, format="json")
        response = self.client.post("/api/v1/bookings/", payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)

    def test_lsa_search_endpoint(self):
        response = self.client.get("/api/v1/lsas/search/", {"skill": "nutrition"})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        names = [item["name"] for item in response.data]
        self.assertIn(self.lsa.name, names)


class ConcurrentBookingTests(TransactionTestCase):
    @override_settings(ENABLE_EXTERNAL_VERIFICATION=False)
    def test_concurrent_overlapping_bookings_only_one_succeeds(self):
        parent = Parent.objects.create(name="Concurrent Parent", email="conc@example.com", phone="9876522222")
        lsa = LSAProfile.objects.create(
            name="Concurrent LSA", email="conc-lsa@example.com", skills="yoga", experience=1,
        )
        start = _future(1)
        end = _future(2)

        results = {}
        barrier = threading.Barrier(2)

        def attempt(key):
            barrier.wait(timeout=5)
            try:
                services.create_booking(
                    parent_id=parent.id, lsa_id=lsa.id, start_time=start, end_time=end,
                )
                results[key] = "success"
            except OverlappingBooking:
                results[key] = "overlap"
            finally:
                connection.close()

        t1 = threading.Thread(target=attempt, args=("t1",))
        t2 = threading.Thread(target=attempt, args=("t2",))
        t1.start()
        t2.start()
        t1.join(timeout=10)
        t2.join(timeout=10)

        outcomes = list(results.values())
        self.assertEqual(outcomes.count("success"), 1)
        self.assertEqual(outcomes.count("overlap"), 1)
        self.assertEqual(BookingRequest.objects.filter(lsa=lsa).count(), 1)
