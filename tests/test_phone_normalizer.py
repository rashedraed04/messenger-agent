"""
Unit tests for Jordanian phone normalizer.
"""

import pytest
from app.services.phone_normalizer import (
    PhoneValidationError,
    is_valid_jordanian_phone,
    normalize_jordanian_phone,
)


def test_standard_format():
    assert normalize_jordanian_phone("0791234567") == "0791234567"
    assert normalize_jordanian_phone("0789876543") == "0789876543"
    assert normalize_jordanian_phone("0771122334") == "0771122334"


def test_arabic_indic_numerals():
    assert normalize_jordanian_phone("٠٧٩١٢٣٤٥٦٧") == "0791234567"
    assert normalize_jordanian_phone("٠٧٨١١٢٢٣٣٤") == "0781122334"
    assert normalize_jordanian_phone("٠٧٧٩٩٨٨٧٧٦") == "0779988776"


def test_country_code_plus_962():
    assert normalize_jordanian_phone("+962791234567") == "0791234567"
    assert normalize_jordanian_phone("+962 78 123 4567") == "0781234567"
    assert normalize_jordanian_phone("+962-77-123-4567") == "0771234567"


def test_country_code_00962():
    assert normalize_jordanian_phone("00962791234567") == "0791234567"
    assert normalize_jordanian_phone("00962 78 123 4567") == "0781234567"


def test_without_leading_zero():
    assert normalize_jordanian_phone("791234567") == "0791234567"
    assert normalize_jordanian_phone("781234567") == "0781234567"
    assert normalize_jordanian_phone("771234567") == "0771234567"


def test_spaces_dashes_parentheses():
    assert normalize_jordanian_phone("(079) 123-4567") == "0791234567"
    assert normalize_jordanian_phone("079.123.4567") == "0791234567"
    assert normalize_jordanian_phone(" 079 123 4567 ") == "0791234567"


def test_invalid_prefixes():
    with pytest.raises(PhoneValidationError):
        normalize_jordanian_phone("0761234567")  # 076 does not exist

    with pytest.raises(PhoneValidationError):
        normalize_jordanian_phone("0801234567")  # 080 is invalid


def test_invalid_length():
    with pytest.raises(PhoneValidationError):
        normalize_jordanian_phone("079123456")  # 9 digits

    with pytest.raises(PhoneValidationError):
        normalize_jordanian_phone("07912345678")  # 11 digits


def test_non_digit_garbage():
    with pytest.raises(PhoneValidationError):
        normalize_jordanian_phone("لا يوجد رقم")

    with pytest.raises(PhoneValidationError):
        normalize_jordanian_phone("")


def test_is_valid_helper():
    assert is_valid_jordanian_phone("0791234567") is True
    assert is_valid_jordanian_phone("+962781234567") is True
    assert is_valid_jordanian_phone("٠٧٧١٢٣٤٥٦٧") is True
    assert is_valid_jordanian_phone("12345") is False
    assert is_valid_jordanian_phone("abcd") is False
