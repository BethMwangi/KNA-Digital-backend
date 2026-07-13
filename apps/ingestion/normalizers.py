"""
Normalisers — every legacy value passes through here before touching our
database. The source data is decades of manual data entry: ALL CAPS,
typos, double-encoded UTF-8 (Â£, â€™), ref-numbers mixed into keywords.
We clean deterministically so the checksum is stable across runs.
"""

import hashlib
import json
import re
from datetime import date, datetime

# Windows-1252-as-UTF-8 double-encoding artefacts seen in the source
MOJIBAKE = {
    "Â£": "£",
    "â€™": "'",
    "â€˜": "'",
    "â€œ": '"',
    "â€\x9d": '"',
    "â€“": "–",
    "â€”": "—",
    "â€¦": "…",
    "Â ": " ",
    "Â": "",
}

REFNO_RE = re.compile(r"^\d{1,5}/\d{1,5}$")  # "1398/254"
WS_RE = re.compile(r"\s+")

# Words that stay capitalised when we sentence-case shouting text
KEEP_UPPER = {"KNA", "KDF", "NGO", "NGOs", "TV", "UK", "USA", "UN", "GSU", "OCS", "MP", "PC", "DC"}


def fix_mojibake(text: str) -> str:
    for bad, good in MOJIBAKE.items():
        text = text.replace(bad, good)
    return text


def clean_text(value: str | None) -> str:
    if not value:
        return ""
    return WS_RE.sub(" ", fix_mojibake(str(value))).strip()


def sentence_case(value: str | None) -> str:
    """The archive was typed in ALL CAPS; render it readable.
    Only applied when the text is (almost) entirely upper-case, so
    already-clean mixed-case records pass through untouched."""
    text = clean_text(value)
    if not text:
        return ""
    letters = [c for c in text if c.isalpha()]
    if letters and sum(c.isupper() for c in letters) / len(letters) < 0.8:
        return text  # already mixed-case
    lowered = text.lower()
    out = []
    capitalize_next = True
    for word in lowered.split(" "):
        original = word.upper().strip(".,()")
        if original in KEEP_UPPER:
            out.append(word.replace(word.strip(".,()"), original))
            capitalize_next = False
            continue
        if capitalize_next and word:
            word = word[0].upper() + word[1:]
        out.append(word)
        capitalize_next = word.endswith((".", "!", "?"))
    result = " ".join(out)
    # Restore proper-noun capitalisation for very common archive names
    for name in (
        "kenyatta",
        "moi",
        "kenya",
        "nairobi",
        "mombasa",
        "kisumu",
        "nakuru",
        "mzee",
        "jomo",
        "daniel",
        "mboya",
        "ngala",
        "uhuru",
    ):
        result = re.sub(rf"\b{name}\b", name.capitalize(), result)
    return result


def title_case_location(value: str | None) -> str:
    text = clean_text(value)
    return text.title() if text else ""


def parse_tags(keywords: str | None) -> list[str]:
    """'1398/254, PRIME MINISTER KENYATTA, EGERTON COLLEGE' →
    ['prime minister kenyatta', 'egerton college'] — ref numbers dropped,
    lowercased, deduped, length-capped for the Tag.name column."""
    if not keywords:
        return []
    seen, tags = set(), []
    for raw in re.split(r"[,;]", fix_mojibake(keywords)):
        tag = WS_RE.sub(" ", raw).strip(" .").lower()
        if not tag or REFNO_RE.match(tag) or len(tag) < 2:
            continue
        tag = tag[:50]
        if tag not in seen:
            seen.add(tag)
            tags.append(tag)
    return tags


def parse_date(value: str | None) -> date | None:
    if not value:
        return None
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%Y/%m/%d", "%d-%m-%Y"):
        try:
            parsed = datetime.strptime(value.strip(), fmt).date()
            # 1970-01-01 is the source system's "unknown" sentinel
            return None if parsed == date(1970, 1, 1) else parsed
        except ValueError:
            continue
    return None


COUNTRY_MAP = {"KEN": "Kenya", "UGA": "Uganda", "TZA": "Tanzania"}


def normalize_country(iso: str | None) -> str:
    return COUNTRY_MAP.get(clean_text(iso).upper(), "Kenya")


# Fields that participate in change detection. If the source edits any of
# these, the checksum changes and we re-map. Volatile/internal fields
# (date_image_injested etc.) are excluded so they don't cause noise.
CHECKSUM_FIELDS = [
    "image_refno",
    "image_description",
    "image_headline",
    "image_caption",
    "image_keywords",
    "image_scene_location",
    "image_Iso_country_created",
    "image_county_created",
    "intellectual_genre",
    "iptc_scene",
    "image_source",
    "main_category",
    "sub_category",
    "image_creator",
    "image_date_created",
    "image_creator_jobtitle",
    "image_thumbnails",
]


def record_checksum(record: dict) -> str:
    subset = {k: record.get(k) for k in CHECKSUM_FIELDS}
    canonical = json.dumps(subset, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(canonical.encode()).hexdigest()
