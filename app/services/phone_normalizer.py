"""
Jordanian phone number normalizer and validator.

Normalizes phone numbers to standard 10-digit Jordanian format:
    07[789]XXXXXXX (e.g. 0791234567)

Handles:
- Arabic-Indic numerals (٠-٩) and Persian numerals (۰-۹)
- Country code variations: +962, 00962, 962
- 9-digit local numbers missing leading 0 (79xxxxxxx -> 079xxxxxxx)
- Spaces, dashes, parentheses, dots
"""

import re

ARABIC_INDIC_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")
EASTERN_ARABIC_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹", "0123456789")

VALID_PREFIXES = ("077", "078", "079")


class PhoneValidationError(ValueError):
    """Raised when a phone number cannot be parsed as a valid Jordanian mobile number."""
    pass


def normalize_jordanian_phone(raw_phone: str) -> str:
    """
    Normalize any representation of a Jordanian mobile number to 10-digit format: 07XXXXXXXX.

    Args:
        raw_phone: Input string containing phone number.

    Returns:
        10-digit string starting with 077, 078, or 079.

    Raises:
        PhoneValidationError: If input is invalid or not a Jordanian mobile number.
    """
    if not raw_phone or not isinstance(raw_phone, str):
        raise PhoneValidationError("رقم الهاتف مطلوب وغير صالح")

    # Step 1: Convert Eastern Arabic and Arabic-Indic numerals to standard ASCII
    clean = raw_phone.translate(ARABIC_INDIC_DIGITS).translate(EASTERN_ARABIC_DIGITS)

    # Step 2: Remove all non-digit characters (except leading + for prefix handling)
    clean = clean.strip()
    has_plus = clean.startswith("+")
    digits = re.sub(r"\D", "", clean)

    if not digits:
        raise PhoneValidationError("رقم الهاتف لا يحتوي على أرقام صالحة")

    # Step 3: Handle country code variations (+962, 00962, 962)
    if digits.startswith("00962"):
        digits = digits[5:]
    elif digits.startswith("962"):
        digits = digits[3:]

    # Step 4: Handle 9-digit format (79XXXXXXX -> 079XXXXXXX)
    if len(digits) == 9 and digits.startswith(("77", "78", "79")):
        digits = "0" + digits

    # Step 5: Validate final length and prefix
    if len(digits) != 10:
        raise PhoneValidationError(
            f"رقم الهاتف يجب أن يتكون من 10 أرقام (المدخل: {digits})"
        )

    if not digits.startswith(VALID_PREFIXES):
        raise PhoneValidationError(
            f"رقم الهاتف يجب أن يبدأ بـ 077 أو 078 أو 079 (المدخل: {digits})"
        )

    return digits


def is_valid_jordanian_phone(raw_phone: str) -> bool:
    """Check if raw_phone is a valid Jordanian mobile number without raising an exception."""
    try:
        normalize_jordanian_phone(raw_phone)
        return True
    except PhoneValidationError:
        return False
