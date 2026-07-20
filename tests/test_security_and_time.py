"""Credential encryption and the timezone rules behind the 'already started today' check."""
from datetime import date, datetime, timezone

import pytest
from cryptography.fernet import Fernet

from app.core.config import settings
from app.utils.security import (
    CredentialDecryptionError,
    decrypt_password,
    encrypt_password,
)
from app.utils.time import local_day_bounds_utc, to_local_display, utc_now


class TestCredentialEncryption:
    def test_a_password_round_trips(self):
        assert decrypt_password(encrypt_password("s3cr3t!")) == "s3cr3t!"

    def test_the_ciphertext_does_not_contain_the_plaintext(self):
        assert "s3cr3t!" not in encrypt_password("s3cr3t!")

    def test_encryption_is_non_deterministic(self):
        """Fernet includes a random IV, so identical passwords differ on disk."""
        assert encrypt_password("same") != encrypt_password("same")

    def test_a_ciphertext_from_another_key_raises_a_specific_error(self):
        foreign = Fernet(Fernet.generate_key()).encrypt(b"secret").decode()
        with pytest.raises(CredentialDecryptionError):
            decrypt_password(foreign)

    def test_garbage_raises_a_specific_error_rather_than_leaking_a_fernet_exception(self):
        with pytest.raises(CredentialDecryptionError):
            decrypt_password("not-a-token")


class TestLocalDayBounds:
    def test_the_window_is_a_full_day(self):
        start, end = local_day_bounds_utc(date(2026, 7, 20))
        assert (end - start).total_seconds() == 24 * 3600

    def test_bounds_are_naive_to_match_stored_columns(self):
        start, end = local_day_bounds_utc(date(2026, 7, 20))
        assert start.tzinfo is None and end.tzinfo is None

    def test_under_utc_the_window_is_midnight_to_midnight(self, monkeypatch):
        monkeypatch.setattr(settings, "ATTENDANCE_TIMEZONE", "UTC")
        start, end = local_day_bounds_utc(date(2026, 7, 20))
        assert start == datetime(2026, 7, 20, 0, 0)
        assert end == datetime(2026, 7, 21, 0, 0)

    def test_the_window_is_shifted_for_an_offset_timezone(self, monkeypatch):
        """
        Regression: rows were written with server-local `datetime.now()` while the
        day window was computed from naive midnight, so the two disagreed by the
        server's UTC offset and 'already started today' could span the wrong hours.
        """
        monkeypatch.setattr(settings, "ATTENDANCE_TIMEZONE", "Asia/Riyadh")  # UTC+3, no DST
        start, end = local_day_bounds_utc(date(2026, 7, 20))
        assert start == datetime(2026, 7, 19, 21, 0)
        assert end == datetime(2026, 7, 20, 21, 0)

    def test_an_unknown_timezone_falls_back_to_utc_instead_of_crashing(self, monkeypatch):
        monkeypatch.setattr(settings, "ATTENDANCE_TIMEZONE", "Mars/Olympus_Mons")
        start, _ = local_day_bounds_utc(date(2026, 7, 20))
        assert start == datetime(2026, 7, 20, 0, 0)


class TestUtcNow:
    def test_is_naive_and_close_to_real_utc(self):
        now = utc_now()
        assert now.tzinfo is None
        real_utc = datetime.now(timezone.utc).replace(tzinfo=None)
        assert abs((real_utc - now).total_seconds()) < 5


class TestDisplayTime:
    def test_a_stored_utc_time_is_rendered_in_the_local_timezone(self, monkeypatch):
        monkeypatch.setattr(settings, "ATTENDANCE_TIMEZONE", "Asia/Riyadh")
        assert to_local_display(datetime(2026, 7, 20, 6, 30)).startswith("09:30 AM")
