import logging

from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework.views import APIView

from . import services
from .exceptions import (
    ExternalVerificationFailed,
    ExternalVerificationUnavailable,
    InvalidBookingTimeRange,
    LSAInactive,
    LSANotFound,
    OverlappingBooking,
    ParentNotFound,
)
from .serializers import (
    BookingRequestCreateSerializer,
    BookingRequestSerializer,
    LSAProfileSerializer,
    LSASearchQuerySerializer,
)
logger = logging.getLogger(__name__)

@api_view(['GET'])
def working(request):
    return Response({"status": "ok", "service": "lsa-booking"})

class BookingRequestCreateView(APIView):
    def post(self, request):
        serializer = BookingRequestCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        try:
            booking = services.create_booking(
                parent_id=data['parent'],
                lsa_id=data['lsa'],
                start_time=data['start_time'],
                end_time=data['end_time'],
            )
        except (ParentNotFound, LSANotFound) as exc:
            return Response(
                {"detail": str(exc)},
                status=status.HTTP_404_NOT_FOUND,
            )
        except (LSAInactive, InvalidBookingTimeRange, ExternalVerificationFailed) as exc:
            return Response(
                {"detail": str(exc)},
                status=status.HTTP_400_BAD_REQUEST,
            )
        except ExternalVerificationUnavailable as exc:
            return Response(
                {"detail": str(exc)},
                status=status.HTTP_502_BAD_GATEWAY,
            )
        except OverlappingBooking as exc:
            return Response(
                {"detail": str(exc)},
                status=status.HTTP_409_CONFLICT,
            )
        except Exception:
            logger.exception("Unexpected error while creating a booking.")
            return Response(
                {"detail": "An unexpected error occurred while creating the booking."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        output = BookingRequestSerializer(booking)
        return Response(output.data, status=status.HTTP_201_CREATED)


class LSASearchView(APIView):
    def get(self, request):
        query_serializer = LSASearchQuerySerializer(data=request.query_params)
        query_serializer.is_valid(raise_exception=True)
        params = query_serializer.validated_data

        lsas = services.search_lsas(
            skill=params.get('skill'),
            start_time=params.get('start_time'),
            end_time=params.get('end_time'),
        )

        output = LSAProfileSerializer(lsas, many=True)
        return Response(output.data, status=status.HTTP_200_OK)