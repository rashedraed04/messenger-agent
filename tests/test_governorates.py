"""
Tests for matching free-text governorate names to the 12 Jordanian governorates.
"""

import pytest

from app.services.governorates import GOVERNORATES, match_governorate


@pytest.mark.parametrize("text, expected", [
    ("عمان", "عمّان"),
    ("عمّان", "عمّان"),
    ("Amman", "عمّان"),
    ("اربد", "إربد"),
    ("الزرقا", "الزرقاء"),
    ("السلط", "البلقاء"),
    ("عمان - خلدا", "عمّان"),
    ("معان", "معان"),
    ("Aqaba", "العقبة"),
])
def test_known_names_match(text, expected):
    assert match_governorate(text) == expected


@pytest.mark.parametrize("text", ["", "   ", "دبي", "xyz"])
def test_unknown_names_do_not_match(text):
    assert match_governorate(text) is None


def test_all_twelve_governorates_listed():
    assert len(GOVERNORATES) == 12
