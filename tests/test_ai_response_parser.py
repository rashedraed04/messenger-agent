"""
Unit tests for AI response parser.
"""

from app.ai.response_parser import parse_ai_response


def test_clean_json_parsing():
    raw = """{
      "response_text": "يا هلا فيك! عطر سوفاج متوفر",
      "extracted_slots": {
        "products": [{"name_match": "سوفاج", "quantity": 1}],
        "customer_name": "أحمد"
      },
      "intent": "place_order",
      "suggested_state": "COLLECTING_DETAILS"
    }"""

    parsed = parse_ai_response(raw)
    assert parsed.response_text == "يا هلا فيك! عطر سوفاج متوفر"
    assert parsed.extracted_slots["customer_name"] == "أحمد"
    assert parsed.extracted_slots["products"][0]["name_match"] == "سوفاج"
    assert parsed.intent == "place_order"
    assert parsed.suggested_state == "COLLECTING_DETAILS"


def test_markdown_wrapped_json():
    raw = """تفضل الرد:
```json
{
  "response_text": "تمام، شو اسم المستلم؟",
  "extracted_slots": {
    "products": [{"name_match": "ديور", "quantity": 2}]
  },
  "intent": "place_order"
}
```
شكرا لك!"""

    parsed = parse_ai_response(raw)
    assert parsed.response_text == "تمام، شو اسم المستلم؟"
    assert len(parsed.extracted_slots["products"]) == 1
    assert parsed.extracted_slots["products"][0]["quantity"] == 2


def test_fallback_on_unstructured_text():
    raw = "يا هلا فيك أخي الكريم، للأسف هذا العطر غير متوفر حالياً ولكن بنقترح عليك عطر سوفاج المميز."
    parsed = parse_ai_response(raw)

    assert parsed.response_text == raw
    assert parsed.extracted_slots == {}
    assert parsed.intent == "general_inquiry"
