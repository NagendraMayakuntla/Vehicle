"""SMS alert sender using Twilio API."""

import os
from typing import Optional
from loguru import logger


class SMSSender:
    """Sends SMS alerts via Twilio.

    Requires environment variables:
    - TWILIO_ACCOUNT_SID
    - TWILIO_AUTH_TOKEN
    - TWILIO_FROM_NUMBER
    """

    def __init__(
        self,
        account_sid: Optional[str] = None,
        auth_token: Optional[str] = None,
        from_number: Optional[str] = None,
        to_numbers: list = None,
    ):
        self.account_sid = account_sid or os.getenv("TWILIO_ACCOUNT_SID", "")
        self.auth_token = auth_token or os.getenv("TWILIO_AUTH_TOKEN", "")
        self.from_number = from_number or os.getenv("TWILIO_FROM_NUMBER", "")
        self.to_numbers = to_numbers or []
        self._client = None

        if self.account_sid and self.auth_token:
            try:
                from twilio.rest import Client
                self._client = Client(self.account_sid, self.auth_token)
            except ImportError:
                logger.warning("Twilio package not installed. SMS alerts disabled.")

    @property
    def is_configured(self) -> bool:
        return self._client is not None and bool(self.from_number) and bool(self.to_numbers)

    def send(self, alert) -> bool:
        """Send an SMS alert to all configured numbers.

        Args:
            alert: An Alert object with title and message.

        Returns:
            True if at least one SMS was sent successfully.
        """
        if not self.is_configured:
            logger.warning("SMS sender not configured. Skipping.")
            return False

        body = f"[{alert.priority.name}] {alert.title}\n{alert.message}"
        if alert.location:
            body += f"\nLocation: {alert.location}"

        success = False
        for number in self.to_numbers:
            try:
                self._client.messages.create(
                    body=body,
                    from_=self.from_number,
                    to=number,
                )
                logger.info(f"SMS sent to {number}: {alert.alert_id}")
                success = True
            except Exception as e:
                logger.error(f"Failed to send SMS to {number}: {e}")

        return success

    def add_recipient(self, phone_number: str):
        """Add a phone number to the recipients list."""
        if phone_number not in self.to_numbers:
            self.to_numbers.append(phone_number)

    def remove_recipient(self, phone_number: str):
        """Remove a phone number from the recipients list."""
        self.to_numbers = [n for n in self.to_numbers if n != phone_number]
