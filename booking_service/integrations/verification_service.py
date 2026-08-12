import logging
from dataclasses import dataclass
from typing import Optional

import requests
from django.conf import settings

logger = logging.getLogger(__name__)


class VerificationServiceError(Exception):
    """
    Raised for any failure talking to the verification service:
    timeouts, connection errors, non-2xx responses, or malformed
    response bodies. Callers should catch this single exception type
    rather than reaching into `requests` internals.
    """


@dataclass(frozen=True)
class VerificationResult:
    verified: bool
    reason: Optional[str] = None
    reference_id: Optional[str] = None


class VerificationServiceClient:
    def __init__(self, endpoint_url=None, timeout=None, api_key=None):
        self.endpoint_url = (endpoint_url or settings.VERIFICATION_SERVICE_URL)
        self.timeout = timeout if timeout is not None else settings.VERIFICATION_SERVICE_TIMEOUT
        self.api_key = api_key if api_key is not None else settings.VERIFICATION_SERVICE_API_KEY

    def _headers(self):
        headers = {'Content-Type': 'application/json'}
        if self.api_key:
            headers['Authorization'] = f'Bearer {self.api_key}'
        return headers

    def verify_request(self, *, parent_id, lsa_id, start_time, end_time):
        url = self.endpoint_url
        payload = {
            'parent_id': parent_id,
            'lsa_id': lsa_id,
            'start_time': start_time.isoformat(),
            'end_time': end_time.isoformat(),
        }
        logger.info(
            "Calling verification service: url=%s parent_id=%s lsa_id=%s",
            url, parent_id, lsa_id,
        )

        try:
            response = requests.post(
                url,
                json=payload,
                headers=self._headers(),
                timeout=self.timeout,
            )
        except requests.exceptions.Timeout as exc:
            logger.warning(
                "Verification service timed out after %ss: url=%s",
                self.timeout, url,
            )
            raise VerificationServiceError("Verification service timed out.") from exc
        except requests.exceptions.ConnectionError as exc:
            logger.error(
                "Verification service connection failed: url=%s",
                url,
            )
            raise VerificationServiceError("Could not connect to verification service.") from exc
        except requests.exceptions.RequestException as exc:
            logger.error(
                "Verification service request failed: url=%s error_type=%s",
                url, type(exc).__name__,
            )
            raise VerificationServiceError("Verification service request failed.") from exc

        if not (200 <= response.status_code < 300):
            logger.warning(
                "Verification service returned non-2xx: url=%s status=%s",
                url, response.status_code,
            )
            raise VerificationServiceError(
                f"Verification service returned HTTP {response.status_code}."
            )

        try:
            data = response.json()
        except ValueError as exc:
            logger.error(
                "Verification service returned invalid JSON: url=%s",
                url,
            )
            raise VerificationServiceError("Verification service returned an invalid response.") from exc

        if 'verified' not in data:
            logger.error(
                "Verification service response missing 'verified' field: url=%s",
                url,
            )
            raise VerificationServiceError("Verification service returned an unexpected response shape.")

        result = VerificationResult(
            verified=bool(data.get('verified')),
            reason=data.get('reason'),
            reference_id=data.get('reference_id'),
        )

        logger.info(
            "Verification service responded: parent_id=%s lsa_id=%s verified=%s reference_id=%s",
            parent_id, lsa_id, result.verified, result.reference_id,
        )

        return result


_default_client = None


def _get_default_client():
    global _default_client
    if _default_client is None:
        _default_client = VerificationServiceClient()
    return _default_client


def verify_request(*, parent_id, lsa_id, start_time, end_time):
    return _get_default_client().verify_request(
        parent_id=parent_id,
        lsa_id=lsa_id,
        start_time=start_time,
        end_time=end_time,
    )
