import logging

from django.conf import settings
from django.db import transaction
from django.db.models import Exists, OuterRef

from .exceptions import (
    ExternalVerificationFailed,
    ExternalVerificationUnavailable,
    InvalidBookingTimeRange,
    LSAInactive,
    LSANotFound,
    OverlappingBooking,
    ParentNotFound,
)
from .integrations.verification_service import VerificationServiceError, verify_request
from .models import BookingRequest, LSAProfile, Parent
logger = logging.getLogger(__name__)
def _get_parent(parent_id):
    try:
        return Parent.objects.get(pk=parent_id)
    except Parent.DoesNotExist:
        raise ParentNotFound(f"Parent with id={parent_id} does not exist.")
def _get_parent_unlocked(parent_id):
    if not Parent.objects.filter(pk=parent_id).exists():
        raise ParentNotFound(f"Parent with id={parent_id} does not exist.")


def _get_active_lsa_unlocked(lsa_id):
    try:
        lsa = LSAProfile.objects.get(pk=lsa_id)
    except LSAProfile.DoesNotExist:
        raise LSANotFound(f"LSA profile with id={lsa_id} does not exist.")
    if not lsa.is_active:
        raise LSAInactive(f"LSA profile with id={lsa_id} is not active.")
    return lsa


def _get_active_lsa_locked(lsa_id):
    try:
        lsa = (
            LSAProfile.objects
            .select_for_update()
            .get(pk=lsa_id)
        )
    except LSAProfile.DoesNotExist:
        raise LSANotFound(
            f"LSA profile with id={lsa_id} does not exist."
        )
    if not lsa.is_active:
        raise LSAInactive(
            f"LSA profile with id={lsa_id} is not active."
        )
    return lsa


def _validate_time_range(start_time, end_time):
    if end_time <= start_time:
        raise InvalidBookingTimeRange("end_time must be strictly after start_time.")


def _has_overlap(lsa, start_time, end_time, exclude_booking_id=None):
    qs = BookingRequest.objects.filter(
        lsa=lsa,
        start_time__lt=end_time,
        end_time__gt=start_time,
    ).exclude(status=BookingRequest.Status.CANCELLED)

    if exclude_booking_id is not None:
        qs = qs.exclude(pk=exclude_booking_id)

    return qs.exists()


@transaction.atomic
def _create_booking_atomic(*, parent_id, lsa_id, start_time, end_time):
    parent = _get_parent(parent_id)
    lsa = _get_active_lsa_locked(lsa_id)

    if _has_overlap(lsa, start_time, end_time):
        logger.info(
            "Rejected overlapping booking for lsa_id=%s (%s - %s)",
            lsa_id, start_time, end_time,
        )
        raise OverlappingBooking(
            "This LSA already has a booking that overlaps the requested time slot."
        )

    booking = BookingRequest.objects.create(
        parent=parent,
        lsa=lsa,
        start_time=start_time,
        end_time=end_time,
        status=BookingRequest.Status.PENDING,
    )

    logger.info(
        "Created booking id=%s parent_id=%s lsa_id=%s (%s - %s)",
        booking.pk, parent_id, lsa_id, start_time, end_time,
    )

    return booking


def create_booking(*, parent_id, lsa_id, start_time, end_time):
    _get_parent_unlocked(parent_id)
    _get_active_lsa_unlocked(lsa_id)

    _validate_time_range(start_time, end_time)

    if settings.ENABLE_EXTERNAL_VERIFICATION:
        try:
            result = verify_request(
                parent_id=parent_id, lsa_id=lsa_id, start_time=start_time, end_time=end_time,
            )
        except VerificationServiceError as exc:
            logger.error(
                "External verification unavailable for parent_id=%s lsa_id=%s: %s",
                parent_id, lsa_id, exc,
            )
            raise ExternalVerificationUnavailable(
                "The verification service is currently unavailable. Please try again shortly."
            ) from exc

        if not result.verified:
            logger.info(
                "Booking verification failed for parent_id=%s lsa_id=%s reason=%s",
                parent_id, lsa_id, result.reason,
            )
            raise ExternalVerificationFailed(
                f"Booking could not be verified (reason: {result.reason})."
            )

    return _create_booking_atomic(
        parent_id=parent_id, lsa_id=lsa_id, start_time=start_time, end_time=end_time,
    )


def search_lsas(*, skill=None, start_time=None, end_time=None):
    queryset = LSAProfile.objects.filter(is_active=True)

    if skill:
        queryset = queryset.filter(skills__icontains=skill)

    if start_time and end_time:
        overlapping_bookings = BookingRequest.objects.filter(
            lsa=OuterRef('pk'),
            start_time__lt=end_time,
            end_time__gt=start_time,
        ).exclude(status=BookingRequest.Status.CANCELLED)

        queryset = queryset.annotate(
            has_conflicting_booking=Exists(overlapping_bookings)
        ).filter(has_conflicting_booking=False)

    return queryset.order_by('name')
