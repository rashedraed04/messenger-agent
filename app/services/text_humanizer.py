"""
Outgoing reply humanizer.

Last-line cleanup applied to every customer-facing message so replies read like
a person typing on Messenger: no markdown, no shouty exclamation marks, no
divider lines or emoji form labels, and no stiff Fusha/AI phrasing.
"""

import re

# Stiff phrases -> natural Jordanian equivalents (longest first so phrases win over words)
PHRASE_REPLACEMENTS: tuple[tuple[str, str], ...] = (
    ("بناءً على رغبتك", "متل ما بدك"),
    ("بناء على رغبتك", "متل ما بدك"),
    ("يسعدني مساعدتك", "تكرم عينك"),
    ("إحنا بالخدمة دائماً", "احنا موجودين"),
    ("إحنا بالخدمة دائما", "احنا موجودين"),
    ("تفضل القائمة", "هاي الخيارات"),
    ("تم بنجاح", "تمام"),
    ("هل ترغب", "بتحب"),
    ("بالتأكيد", "أكيد"),
    ("حسناً", "تمام"),
    ("حسنا", "تمام"),
    ("عذراً", "معلش"),
    ("عذرا", "معلش"),
    ("رائع", "حلو"),
)

# Whole-word swaps only, so "بكرة" or "نعمان" are left alone
WORD_REPLACEMENTS: dict[str, str] = {
    "نعم": "اه",
    "بك": "فيك",
}

# A line made only of divider characters (━━━━, ----, ====, ____ ...)
_DIVIDER_LINE = re.compile(r"^\s*[━─═—–\-=_~•·*]{3,}\s*$")
# Emoji-prefixed form labels at line start: "📱 الاسم:" -> "الاسم:"
_EMOJI_LABEL = re.compile(
    r"^\s*[\U0001F300-\U0001FAFF☀-➿️]+\s*(?=[^\s:]{1,20}\s*:)", re.MULTILINE
)


def _replace_word(text: str, word: str, replacement: str) -> str:
    return re.sub(rf"(?<!\w){re.escape(word)}(?!\w)", replacement, text)


def humanize_reply(text: str) -> str:
    """Clean an outgoing customer message so it reads like a human typed it."""
    if not text:
        return text

    # Markdown: bold/italic markers, headings, inline code
    text = text.replace("**", "").replace("__", "").replace("`", "")
    text = text.replace("*", "").replace("#", "")

    # Divider lines and emoji form labels
    lines = [line for line in text.split("\n") if not _DIVIDER_LINE.match(line)]
    text = _EMOJI_LABEL.sub("", "\n".join(lines))

    for phrase, replacement in PHRASE_REPLACEMENTS:
        text = text.replace(phrase, replacement)
    for word, replacement in WORD_REPLACEMENTS.items():
        text = _replace_word(text, word, replacement)

    # Exclamation marks: dropped at the end of a line, a space mid-sentence
    text = re.sub(r"\s*[!！]+\s*$", "", text, flags=re.MULTILINE)
    text = re.sub(r"\s*[!！]+\s*", " ", text)

    # Tidy whitespace left behind
    text = re.sub(r"[ \t]{2,}", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return "\n".join(line.strip() for line in text.split("\n")).strip()
