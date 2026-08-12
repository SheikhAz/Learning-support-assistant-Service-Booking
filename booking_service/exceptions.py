class BookingError(Exception):
    """Base class for all booking-related domain errors."""


class ParentNotFound(BookingError):
    """Raised when the referenced Parent does not exist."""


class LSANotFound(BookingError):
    """Raised when the referenced LSA profile does not exist."""


class LSAInactive(BookingError):
    """Raised when attempting to book an LSA that is not active."""


class InvalidBookingTimeRange(BookingError):
    """Raised when end_time is not strictly after start_time."""


class OverlappingBooking(BookingError):
    """Raised when the requested slot overlaps an existing booking for the same LSA."""


class ExternalVerificationFailed(BookingError):
    """Raised when the external verification service explicitly rejects the request."""


class ExternalVerificationUnavailable(BookingError):
    """Raised when the external verification service could not be reached or errored."""
