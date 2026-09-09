"""Load *your* airfare data in place of the built-in demo dataset.

The shipped demo dataset (``app.dataset.build_dataset``) is synthetic: it is
generated on startup from a fixed seed so every run looks identical. This module
is the seam that lets real, user-supplied data take its place **without touching
a single screen, endpoint or line of aggregation logic**.

Design rules
------------
1. **Drop-in.** Put files in the data directory (default: ``<repo>/data``,
   override with ``APIX_CUSTOM_DATA_DIR``) and the dashboard serves them. No
   code change, no restart: the loader re-reads whenever a file's size or
   mtime changes.
2. **Additive.** Every supported file in the directory is loaded and merged, so
   "here is more data" means "drop another file in". Files are loaded in
   name order; ``routes.*``, ``airlines.*`` and ``sources.*`` are treated as
   reference tables, everything else as fare observations.
3. **Tolerant on input, strict on output.** Column names are matched through a
   generous alias table (``price``/``fare``/``total_fare``/``amount`` …), dates
   and amounts are parsed out of many common formats, and missing derived
   fields (route, lead time, fare components, fingerprint, quality) are
   computed. Output is always the canonical :class:`~app.dataset.Observation`.
4. **Honest.** Nothing is invented to make a screen look fuller: a row without
   a usable date, route or fare is reported as a rejected row with a reason,
   never silently turned into a plausible fare. Weights for routes the user did
   not supply are derived from observation share and labelled ``provisional``.
5. **Same pipeline.** The imported observations are aggregated by the exact
   function that backs the demo and live datasets
   (``dataset._finalize_aggregates``), so index, routes, airlines, lead time,
   quality and provenance screens all work unchanged.

Origin value for such a dataset is ``"custom"`` — the dashboard shows a
distinct badge for it, because it is neither synthetic demo data nor data the
collection engine scraped.

Quick check from a shell::

    cd backend && python -m app.custom_data            # report on ./../data
    cd backend && python -m app.custom_data path.csv   # validate one file
"""

from __future__ import annotations

import csv
import datetime as dt
import io
import json
import random
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Optional

from .config import settings
from .dataset import (
    ACTIVE_SOURCE_IDS,
    AIRLINES,
    LEAD_TIMES,
    ROUTES,
    ROUTE_AIRLINES,
    SOURCES,
    Dataset,
    Observation,
    _finalize_aggregates,
    _fingerprint,
    _median,
    _quality_score,
)

# --------------------------------------------------------------------------- #
# Where the data lives
# --------------------------------------------------------------------------- #

#: Files with these suffixes are considered data files.
SUPPORTED_SUFFIXES = {".csv", ".tsv", ".txt", ".json", ".jsonl", ".ndjson"}

#: Filenames (stem, lowercased) that are *reference tables* rather than fares.
REFERENCE_STEMS = {
    "routes": "routes",
    "route": "routes",
    "route_basket": "routes",
    "basket": "routes",
    "airlines": "airlines",
    "airline": "airlines",
    "carriers": "airlines",
    "carrier": "airlines",
    "sources": "sources",
    "source": "sources",
}

#: Reference files live at the data root only; observation files can be nested.
CONFIG_FILENAMES = ("config.json", "apix_data.json")

QUALITY_STATUSES = ("VALID", "SUSPICIOUS", "INVALID", "DUPLICATE", "SOLD_OUT", "STALE", "MISSING")

INDEX_ELIGIBLE = ("VALID", "SUSPICIOUS")


def data_root() -> Path:
    """Directory scanned for user data (``APIX_CUSTOM_DATA_DIR``)."""
    explicit = getattr(settings, "custom_data_dir", None)
    return Path(explicit) if explicit else Path(__file__).resolve().parents[2] / "data"


def is_enabled() -> bool:
    """Custom data is skipped when the source is explicitly locked to demo."""
    if not getattr(settings, "custom_data_enabled", True):
        return False
    return settings.forced_data_mode != "demo"


# --------------------------------------------------------------------------- #
# Column aliases — map whatever the user called it onto a canonical field
# --------------------------------------------------------------------------- #

FIELD_ALIASES: dict[str, tuple[str, ...]] = {
    "observation_id": (
        "observation_id", "obs_id", "id", "record_id", "row_id", "uuid", "uid",
    ),
    "source": (
        "source", "source_id", "source_name", "provider", "channel", "ota",
        "vendor", "site", "website", "collected_from", "feed", "partner",
    ),
    "collection_date": (
        "collection_date", "date", "observed_on", "observed_at", "observation_date",
        "snapshot_date", "collected_on", "collected_at", "collected_date",
        "scrape_date", "search_date", "recorded_at", "created_at", "captured_at",
        "query_date", "as_of", "as_on", "day", "datetime", "timestamp",
    ),
    "collection_timestamp": (
        "collection_timestamp", "collected_at_ts", "timestamp_ist", "event_time",
    ),
    "departure_date": (
        "departure_date", "travel_date", "flight_date", "dep_date", "departure",
        "outbound_date", "journey_date", "journeydate", "doj", "date_of_journey",
        "onward_date", "dept_date",
    ),
    "origin": (
        "origin", "from", "src", "source_airport", "origin_code", "from_airport",
        "dep_airport", "departure_airport", "origin_iata", "from_city_code",
        "board", "from_code", "orgn", "sector_from",
    ),
    "destination": (
        "destination", "to", "dst", "dest", "destination_code", "to_airport",
        "arr_airport", "arrival_airport", "destination_iata", "to_city_code",
        "deboard", "to_code", "destn", "sector_to",
    ),
    "route": (
        "route", "route_code", "route_name", "sector", "od", "o_d", "city_pair",
        "citypair", "leg", "pair",
    ),
    "airline": (
        "airline", "carrier", "airline_code", "carrier_code", "airline_name",
        "marketing_airline", "operating_airline", "airline_iata", "company",
    ),
    "flight_number": (
        "flight_number", "flight_no", "flightno", "flight", "flight_code",
        "flightnumber", "flight_id", "flt_no",
    ),
    "cabin": ("cabin", "cabin_class", "class_of_service", "travel_class", "cos"),
    "fare_class": (
        "fare_class", "booking_class", "rbd", "fare_basis", "fare_code",
        "booking_code", "class",
    ),
    "lead_time_days": (
        "lead_time_days", "lead_time", "days_to_departure", "advance_purchase_days",
        "dtd", "advance_days", "days_before_departure", "lead", "booking_window",
    ),
    "base_fare": (
        "base_fare", "base", "base_price", "basefare", "fare_base", "basic_fare",
        "net_fare", "fare_amount", "published_fare",
    ),
    "taxes": ("taxes", "tax", "tax_amount", "gst", "taxes_amount", "total_tax"),
    "fees": (
        "fees", "fee", "convenience_fee", "surcharge", "service_fee",
        "other_charges", "charges",
    ),
    "total_fare": (
        "total_fare", "total", "price", "fare", "amount", "total_price",
        "total_amount", "price_inr", "ticket_price", "payable", "grand_total",
        "net_payable", "final_price", "min_fare", "lowest_fare", "fare_total",
        "amount_paid", "value", "rate",
    ),
    "currency": ("currency", "curr", "currency_code", "ccy"),
    "availability": (
        "availability", "availability_status", "seat_availability", "status",
        "avail", "inventory_status",
    ),
    "seats_remaining": (
        "seats_remaining", "seats", "seats_left", "seats_available",
        "available_seats", "seat_count", "inventory",
    ),
    "quality_status": (
        "quality_status", "qc_status", "quality", "quality_flag", "flag",
        "validation_status", "qc", "status_flag",
    ),
    "origin_city": ("origin_city", "from_city", "origin_city_name", "source_city"),
    "destination_city": ("destination_city", "to_city", "destination_city_name", "dest_city"),
    "distance": ("distance", "distance_km", "distance_in_km", "km"),
    "weight": ("weight", "route_weight", "traffic_weight", "share"),
    "name": ("name", "airline_name", "source_name", "carrier_name", "label"),
    "alliance": ("alliance", "category", "type", "segment"),
    "hub": ("hub", "hub_airport", "base"),
    "type": ("type", "source_type", "kind"),
    "status": ("status", "state", "health"),
    "compliance": ("compliance", "permission", "authorization"),
    "adapter": ("adapter", "adapter_name"),
}

_ALIAS_LOOKUP: dict[str, str] = {}
for _canon, _aliases in FIELD_ALIASES.items():
    for _a in _aliases:
        # First writer wins: the earlier group is the more specific field, so
        # 'airline_name' stays an airline and 'status' stays an availability.
        _ALIAS_LOOKUP.setdefault(_a, _canon)
# A canonical name always maps to itself.
for _canon in FIELD_ALIASES:
    _ALIAS_LOOKUP.setdefault(_canon, _canon)

# Second chance for headers that carry an extra word ("Cheapest Fare (INR)",
# "Date Of Journey", "Observed On", "Flight No." …): match on a keyword token.
# Order is deliberate — the more specific field is tested first, so
# "date_of_journey" is a departure date and "base_fare" is not a total fare.
KEYWORD_PRIORITY: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("collection_timestamp", ("ts", "timestamp_ist", "event_time", "collected_at_ts")),
    ("departure_date", ("depart", "departure", "travel", "journey", "doj", "outbound",
                        "onward", "dept", "journeydate")),
    ("collection_date", ("date", "observed", "snapshot", "collected", "scrape", "search",
                         "recorded", "created", "captured", "query", "as_of", "as_on",
                         "day", "datetime", "timestamp", "seen")),
    ("base_fare", ("base", "basic", "basefare", "published", "net")),
    ("taxes", ("tax", "taxes", "gst")),
    ("fees", ("fee", "fees", "surcharge", "convenience", "service", "charges")),
    ("total_fare", ("fare", "fares", "price", "amount", "total", "rate", "value",
                    "payable", "cheapest", "lowest", "min", "ticket", "grand",
                    "tariff", "cost")),
    ("origin", ("origin", "from", "src", "board", "orgn", "dep_airport", "origin_iata")),
    ("destination", ("destination", "dest", "dst", "deboard", "destn", "arr_airport",
                     "destination_iata")),
    ("route", ("route", "sector", "city_pair", "citypair", "pair", "leg", "od")),
    ("airline", ("airline", "carrier", "company", "marketing", "operating")),
    ("flight_number", ("flight", "flt", "flightno")),
    ("lead_time_days", ("lead", "advance", "dtd", "booking_window", "days_before",
                        "days_to_departure", "advance_purchase")),
    ("seats_remaining", ("seats", "seat", "inventory")),
    ("availability", ("availability", "avail", "inventory_status", "seat_status")),
    ("quality_status", ("quality", "qc", "flag", "validation", "status_flag")),
    ("source", ("source", "provider", "channel", "ota", "vendor", "site", "website",
                "feed", "partner", "portal")),
    ("currency", ("currency", "curr", "ccy")),
    ("origin_city", ("origin_city", "from_city")),
    ("destination_city", ("destination_city", "to_city", "dest_city")),
    ("distance", ("distance", "km")),
    ("weight", ("weight", "traffic_weight", "share")),
    ("name", ("name", "label")),
    ("alliance", ("alliance", "category", "segment")),
    ("hub", ("hub",)),
    ("type", ("type", "kind")),
    ("status", ("state", "health")),
    ("compliance", ("compliance", "permission", "authorization")),
    ("adapter", ("adapter",)),
    ("observation_id", ("observation_id", "obs_id", "record_id", "row_id", "uuid", "uid")),
    ("fare_class", ("fare_class", "booking_class", "rbd", "fare_basis", "booking_code")),
    ("cabin", ("cabin", "cos", "travel_class", "class_of_service")),
)


def match_column(header: str) -> Optional[str]:
    """Best-effort canonical field for a header, exact alias first, keyword after."""
    norm = _normalise_header(header)
    if norm in _ALIAS_LOOKUP:
        return _ALIAS_LOOKUP[norm]
    tokens = set(norm.split("_"))
    if not tokens:
        return None
    for canon, keywords in KEYWORD_PRIORITY:
        if tokens & set(keywords):
            return canon
    return None


# --------------------------------------------------------------------------- #
# Value parsing helpers
# --------------------------------------------------------------------------- #

_NULLS = {"", "na", "n/a", "nan", "none", "null", "nil", "-", "--", "?", "unknown"}

_DATE_FORMATS = (
    "%Y-%m-%d", "%Y/%m/%d", "%d-%m-%Y", "%d/%m/%Y", "%d.%m.%Y",
    "%d-%b-%Y", "%d %b %Y", "%d-%b-%y", "%d %B %Y",
    "%b %d, %Y", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M",
    "%d-%m-%Y %H:%M", "%d/%m/%Y %H:%M", "%m/%d/%Y",
)

_AMOUNT_RE = re.compile(r"[^0-9.\-]")

# Airline name -> IATA code for the carriers that show up in Indian data.
AIRLINE_CODES: dict[str, str] = {
    "indigo": "6E", "air india": "AI", "air india express": "IX",
    "spicejet": "SG", "spice jet": "SG", "vistara": "UK",
    "go first": "G8", "goair": "G8", "go air": "G8", "go first airlines": "G8",
    "akasa air": "QP", "akasa": "QP",
    "airasia india": "I5", "airasia": "I5", "air asia india": "I5", "air asia": "I5",
    "alliance air": "9I", "star air": "S5", "fly91": "IC", "flybig": "S9",
    "indiaone air": "I7", "air india regional": "9I", "air india express ltd": "IX",
    "air india limited": "AI", "interglobe aviation": "6E",
}

# IATA code -> city, so imported routes get readable labels.
AIRPORT_CITIES: dict[str, str] = {
    "DEL": "Delhi", "BOM": "Mumbai", "BLR": "Bengaluru", "MAA": "Chennai",
    "CCU": "Kolkata", "HYD": "Hyderabad", "COK": "Kochi", "GOI": "Goa",
    "AMD": "Ahmedabad", "JAI": "Jaipur", "PNQ": "Pune", "LKO": "Lucknow",
    "VNS": "Varanasi", "PAT": "Patna", "BBI": "Bhubaneswar", "IXR": "Ranchi",
    "GAU": "Guwahati", "IMF": "Imphal", "IXB": "Bagdogra", "SXR": "Srinagar",
    "IXJ": "Jammu", "ATQ": "Amritsar", "IXC": "Chandigarh", "JDH": "Jodhpur",
    "UDR": "Udaipur", "JLR": "Jabalpur", "BHO": "Bhopal", "IDR": "Indore",
    "NAG": "Nagpur", "RAJ": "Rajkot", "BDQ": "Vadodara", "STV": "Surat",
    "GOX": "Goa", "TRV": "Thiruvananthapuram", "CJB": "Coimbatore",
    "IXM": "Madurai", "TRZ": "Tiruchirappalli", "VTZ": "Visakhapatnam",
    "VGA": "Vijayawada", "HBX": "Hubballi", "MYQ": "Mysuru", "IXG": "Belagavi",
    "IXE": "Mangaluru", "AGC": "Agra", "KUU": "Kullu", "DHM": "Dharamshala",
    "BKK": "Bangkok", "DXB": "Dubai", "DOH": "Doha", "SIN": "Singapore",
    "KUL": "Kuala Lumpur", "CMB": "Colombo", "KTM": "Kathmandu", "DAC": "Dhaka",
    "LHR": "London", "JFK": "New York", "AUH": "Abu Dhabi", "SHJ": "Sharjah",
    "MCT": "Muscat", "RUH": "Riyadh", "HKG": "Hong Kong", "NBO": "Nairobi",
}

#: Non-standard airport/city spellings seen in exports -> IATA code.
AIRPORT_ALIASES: dict[str, str] = {
    "GOA": "GOI", "GOX": "GOI", "BOMBAY": "BOM", "MUMBAI": "BOM",
    "DELHI": "DEL", "NEW DELHI": "DEL", "CALCUTTA": "CCU", "KOLKATA": "CCU",
    "MADRAS": "MAA", "CHENNAI": "MAA", "BANGALORE": "BLR", "BENGALURU": "BLR",
    "BENGALORE": "BLR", "TRIVANDRUM": "TRV", "THIRUVANANTHAPURAM": "TRV",
    "HYDERABAD": "HYD", "PUNE": "PNQ", "KOCHI": "COK", "COCHIN": "COK",
    "AHMEDABAD": "AMD", "JAIPUR": "JAI", "VARANASI": "VNS", "BENARES": "VNS",
    "PATNA": "PAT", "GUWAHATI": "GAU", "SRINAGAR": "SXR", "AMRITSAR": "ATQ",
}


def _airport_code(value: str) -> str:
    """Canonical 3-letter airport code, tolerating city names and aliases."""
    code = _clean(value).upper()
    return AIRPORT_ALIASES.get(code, code)


_ROUTE_SPLIT_RE = re.compile(r"\s*(?:-+>|-|>|\||/|\\|\bto\b|\b2\b|,|;)\s*", re.IGNORECASE)


def _clean(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _is_null(value: Any) -> bool:
    return _clean(value).lower() in _NULLS


def _normalise_header(name: str) -> str:
    """``'Total Fare (INR)'`` -> ``'total_fare'``."""
    s = _clean(name).lower()
    s = re.sub(r"\(.*?\)", "", s)               # drop units: (INR), (days)
    s = s.replace("₹", "").replace("rs", "")
    s = re.sub(r"[^a-z0-9]+", "_", s)
    s = re.sub(r"_+", "_", s).strip("_")
    for suffix in ("_inr", "_rs", "_rupees", "_days", "_day"):
        if s.endswith(suffix):
            s = s[: -len(suffix)]
    return s


def _to_float(value: Any) -> Optional[float]:
    """Parse ``'₹ 4,650.00'`` -> ``4650.0``; ``None`` when unparseable."""
    if value is None:
        return None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    text = _clean(value)
    if _is_null(text):
        return None
    text = _AMOUNT_RE.sub("", text)
    if text in ("", "-", "."):
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _to_int(value: Any) -> Optional[int]:
    f = _to_float(value)
    return None if f is None else int(round(f))


def _to_date(value: Any, date_format: Optional[str] = None) -> Optional[dt.date]:
    if value is None:
        return None
    if isinstance(value, dt.datetime):
        return value.date()
    if isinstance(value, dt.date):
        return value
    text = _clean(value)
    if _is_null(text):
        return None
    candidates: list[str] = []
    if date_format:
        candidates.append(date_format)
    candidates.extend(_DATE_FORMATS)
    # ISO datetime with timezone / 'T' separator.
    head = text.replace("T", " ").split("+")[0].split(".")[0].strip()
    candidates.insert(0, "%Y-%m-%d %H:%M:%S")
    for fmt in candidates:
        for candidate in (text, head):
            if not candidate:
                continue
            try:
                return dt.datetime.strptime(candidate, fmt).date()
            except ValueError:
                continue
    return None


def _to_iso_time(value: Any) -> Optional[str]:
    text = _clean(value)
    if not text or _is_null(text):
        return None
    if "T" in text:
        return text
    return None


def _split_route(value: Any) -> Optional[tuple[str, str]]:
    """``'DEL-BOM'`` / ``'DEL / BOM'`` / ``'DEL to BOM'`` -> ``('DEL','BOM')``."""
    text = _clean(value).upper()
    if not text or _is_null(text):
        return None
    text = text.replace("–", "-")
    parts = [p.strip() for p in _ROUTE_SPLIT_RE.split(text) if p.strip()]
    if len(parts) >= 2:
        o, d = parts[0], parts[-1]
    elif len(text) == 6 and text.isalpha():      # DELBOM
        o, d = text[:3], text[3:]
    else:
        return None
    o, d = _airport_code(o), _airport_code(d)
    if len(o) != 3 or len(d) != 3 or not (o.isalpha() and d.isalpha()):
        return None
    return o, d


def _airline_code(value: Any) -> tuple[str, Optional[str]]:
    """Return ``(code, name)`` for whatever the user supplied."""
    text = _clean(value)
    if not text or _is_null(text):
        return "NA", None
    upper = text.upper()
    is_code = (
        1 < len(upper) <= 3
        and " " not in upper
        and upper.isalnum()          # IATA codes mix letters and digits: 6E, I5, G8
        and any(c.isalpha() for c in upper)
    )
    if is_code:
        known = AIRLINES.get(upper)
        return upper, (known["name"] if known else None)
    name_key = text.lower().strip()
    code = AIRLINE_CODES.get(name_key)
    if code:
        known = AIRLINES.get(code)
        return code, (known["name"] if known else text.title())
    # Unknown airline name: derive a stable 2-letter code from the name.
    words = [w for w in re.split(r"[^A-Za-z]+", text) if w]
    derived = ("".join(w[0] for w in words)[:2] or "NA").upper()
    return derived, text.title()


def _normalise_availability(value: Any) -> Optional[str]:
    text = _clean(value).upper()
    if not text or _is_null(text):
        return None
    if text in ("AVAILABLE", "AVAIL", "A", "YES", "Y", "TRUE", "1", "OPEN", "ON SALE"):
        return "AVAILABLE"
    if text in ("LIMITED", "LTD", "FEW", "LOW", "SELLING FAST"):
        return "LIMITED"
    if text in ("SOLD_OUT", "SOLDOUT", "SOLD OUT", "NO", "N", "0", "UNAVAILABLE",
                "CLOSED", "NOT AVAILABLE", "FALSE"):
        return "SOLD_OUT"
    return None


_QUALITY_WORDS = {
    "VALID": "VALID", "OK": "VALID", "PASS": "VALID", "GOOD": "VALID", "CLEAN": "VALID",
    "SUSPICIOUS": "SUSPICIOUS", "OUTLIER": "SUSPICIOUS", "ANOMALY": "SUSPICIOUS",
    "INVALID": "INVALID", "REJECTED": "INVALID", "BAD": "INVALID", "ERROR": "INVALID",
    "FAILED": "INVALID", "FAIL": "INVALID",
    "DUPLICATE": "DUPLICATE", "DUP": "DUPLICATE",
    "SOLD_OUT": "SOLD_OUT", "SOLD OUT": "SOLD_OUT", "SOLDOUT": "SOLD_OUT",
    "STALE": "STALE", "CACHED": "STALE",
    "MISSING": "MISSING", "NULL": "MISSING",
}


def _normalise_quality(value: Any) -> Optional[str]:
    text = _clean(value).upper()
    if not text or _is_null(text):
        return None
    if text in QUALITY_STATUSES:
        return text
    return _QUALITY_WORDS.get(text)


def _slug(value: str) -> str:
    """Stable id from a free-text name: 'Mock OTA A' -> 'mock_ota_a'."""
    s = re.sub(r"[^A-Za-z0-9]+", "_", _clean(value).lower()).strip("_")
    return s or "import"


# --------------------------------------------------------------------------- #
# File reading
# --------------------------------------------------------------------------- #

@dataclass
class DataFile:
    """One discovered file plus what we managed to make of it."""

    path: Path
    kind: str = "observations"          # observations | routes | airlines | sources
    rows: int = 0
    observations: int = 0
    rejected: int = 0
    columns: list[str] = field(default_factory=list)
    mapped: dict[str, str] = field(default_factory=dict)   # canonical -> source column
    unmapped: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "path": _display_path(self.path),
            "name": self.path.name,
            "kind": self.kind,
            "rows": self.rows,
            "observations": self.observations,
            "rejected": self.rejected,
            "columns": self.columns,
            "mapped": self.mapped,
            "unmapped": self.unmapped,
            "warnings": self.warnings,
            "errors": self.errors,
            "size_bytes": _safe_size(self.path),
            "modified_at": _safe_mtime(self.path),
        }


def _safe_size(path: Path) -> int:
    try:
        return path.stat().st_size
    except OSError:
        return 0


def _safe_mtime(path: Path) -> Optional[str]:
    try:
        return dt.datetime.fromtimestamp(path.stat().st_mtime).isoformat(timespec="seconds")
    except OSError:
        return None


def _display_path(path: Path) -> str:
    try:
        return str(path.relative_to(Path(__file__).resolve().parents[2]))
    except (ValueError, OSError):
        return str(path)


def discover_files(root: Optional[Path] = None, include: Optional[list[str]] = None,
                   exclude: Optional[list[str]] = None) -> list[DataFile]:
    """Find every data file under ``root`` (recursively, ``_``-prefixed skipped).

    Files/directories whose name starts with ``_`` are ignored, which is how the
    bundled templates in ``data/_templates`` stay out of the way until copied.
    """
    import fnmatch

    root = Path(root) if root else data_root()
    if not root.exists():
        return []
    found: list[Path] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(root)
        if any(part.startswith("_") or part.startswith(".") for part in rel.parts):
            continue
        if path.suffix.lower() not in SUPPORTED_SUFFIXES:
            continue
        rel_str = str(rel).replace("\\", "/")
        if include and not any(fnmatch.fnmatch(rel_str, pat) or fnmatch.fnmatch(path.name, pat) for pat in include):
            continue
        if exclude and any(fnmatch.fnmatch(rel_str, pat) or fnmatch.fnmatch(path.name, pat) for pat in exclude):
            continue
        found.append(path)

    files: list[DataFile] = []
    for path in found:
        stem = re.sub(r"[-_\s\d]+$", "", path.stem.lower())
        kind = REFERENCE_STEMS.get(stem)
        if kind is None and path.parent != root:
            # Nested reference tables (data/reference/routes.csv) still count.
            kind = REFERENCE_STEMS.get(path.stem.lower())
        files.append(DataFile(path=path, kind=kind or "observations"))
    return files


def load_config(root: Optional[Path] = None) -> dict:
    """Optional ``data/config.json``: column map, date format, weights, filters."""
    root = Path(root) if root else data_root()
    for name in CONFIG_FILENAMES:
        cfg_path = root / name
        if cfg_path.is_file():
            try:
                data = json.loads(cfg_path.read_text(encoding="utf-8-sig"))
            except (OSError, ValueError) as exc:
                print(f"[apix] {cfg_path.name} could not be read ({exc}); ignoring it")
                continue
            if isinstance(data, dict):
                return data
    return {}


def read_rows(path: Path, warning_sink: Optional[list[str]] = None) -> tuple[list[dict], list[str]]:
    """Read a CSV/TSV/JSON/JSONL file into ``(rows, headers)``."""
    suffix = path.suffix.lower()
    try:
        text = path.read_text(encoding="utf-8-sig", errors="replace")
    except OSError as exc:
        if warning_sink is not None:
            warning_sink.append(f"could not read file: {exc}")
        return [], []

    if suffix in (".json", ".jsonl", ".ndjson"):
        return _read_json(text, warning_sink)

    sample = text[:8192]
    delimiter = ","
    try:
        delimiter = csv.Sniffer().sniff(sample, delimiters=",;\t|").delimiter
    except csv.Error:
        if "\t" in sample:
            delimiter = "\t"
        elif ";" in sample:
            delimiter = ";"
    reader = csv.reader(io.StringIO(sample), delimiter=delimiter)
    try:
        header = next(reader)
    except StopIteration:
        return [], []
    # A single-column CSV usually means the delimiter guess was wrong.
    if len(header) == 1 and delimiter != "\t" and "\t" in sample:
        delimiter = "\t"
    reader = csv.DictReader(io.StringIO(text), delimiter=delimiter)
    try:
        rows = [dict(r) for r in reader]
    except csv.Error as exc:
        if warning_sink is not None:
            warning_sink.append(f"CSV parse error: {exc}")
        return [], []
    headers = [h for h in (reader.fieldnames or []) if h is not None]
    return rows, headers


def _read_json(text: str, warning_sink: Optional[list[str]] = None) -> tuple[list[dict], list[str]]:
    stripped = text.strip()
    if not stripped:
        return [], []
    if stripped[0] in "[{":
        try:
            data = json.loads(stripped)
        except ValueError:
            data = None          # not one document — maybe JSON Lines
        else:
            rows, headers = _flatten_json(data)
            if rows:
                return rows, headers
    # JSON Lines (one object per line)
    rows: list[dict] = []
    for line in stripped.splitlines():
        line = line.strip().rstrip(",")
        if not line or line in ("[", "]"):
            continue
        try:
            obj = json.loads(line)
        except ValueError:
            # Not line-delimited after all: try the whole document.
            try:
                data = json.loads(stripped)
            except ValueError as exc:
                if warning_sink is not None:
                    warning_sink.append(f"JSON parse error: {exc}")
                return [], []
            return _flatten_json(data)
        if isinstance(obj, dict):
            rows.append(obj)
    headers: list[str] = []
    for row in rows:
        for key in row:
            if key not in headers:
                headers.append(key)
    return rows, headers


def _flatten_json(data: Any) -> tuple[list[dict], list[str]]:
    if isinstance(data, dict):
        for key in ("observations", "data", "rows", "fares", "records", "results", "items"):
            value = data.get(key)
            if isinstance(value, list):
                rows = [r for r in value if isinstance(r, dict)]
                headers: list[str] = []
                for row in rows:
                    for k in row:
                        if k not in headers:
                            headers.append(k)
                return rows, headers
        return [data], list(data.keys())
    if isinstance(data, list):
        rows = [r for r in data if isinstance(r, dict)]
        headers = []
        for row in rows:
            for k in row:
                if k not in headers:
                    headers.append(k)
        return rows, headers
    return [], []


# --------------------------------------------------------------------------- #
# Row -> canonical observation
# --------------------------------------------------------------------------- #

def _map_columns(headers: Iterable[str], extra_map: Optional[dict] = None) -> tuple[dict, dict, list[str]]:
    """Return ``(canonical_by_source_column, source_by_canonical, unmapped)``."""
    canonical: dict[str, str] = {}
    source_by_canonical: dict[str, str] = {}
    unmapped: list[str] = []
    for header in headers:
        norm = _normalise_header(header)
        override = (extra_map or {}).get(norm) or (extra_map or {}).get(_clean(header).lower())
        canon = override or match_column(header)
        # 'status' is ambiguous: availability wins, quality is detected by value.
        if canon is None:
            unmapped.append(_clean(header))
            continue
        if canon in source_by_canonical:
            # Duplicate mapping: keep the first, remember the spare column name.
            unmapped.append(_clean(header))
            continue
        canonical[header] = canon
        source_by_canonical[canon] = header
    return canonical, source_by_canonical, unmapped


def _get(row: dict, canonical: dict[str, str], key: str) -> Any:
    header = canonical.get(key)
    return row.get(header) if header else None


def _resolve_route(row: dict, canonical: dict[str, str]) -> Optional[tuple[str, str, str]]:
    """``(route_key, origin, destination)`` from whichever columns exist."""
    raw_route = _get(row, canonical, "route")
    pair = _split_route(raw_route)
    if pair is None:
        origin = _airport_code(_get(row, canonical, "origin"))
        destination = _airport_code(_get(row, canonical, "destination"))
        if len(origin) == 3 and len(destination) == 3 and origin.isalpha() and destination.isalpha():
            pair = (origin, destination)
    if pair is None:
        return None
    return f"{pair[0]}-{pair[1]}", pair[0], pair[1]


def build_observations(
    rows: list[dict],
    headers: list[str],
    *,
    data_file: DataFile,
    config: Optional[dict] = None,
    default_source: Optional[str] = None,
) -> list[Observation]:
    """Turn raw rows from one file into canonical observations."""
    config = config or {}
    extra_map = {_normalise_header(k): v for k, v in (config.get("column_map") or {}).items()}
    date_format = config.get("date_format") or None
    currency = str(config.get("currency") or "INR").upper()
    fallback_source = default_source or config.get("default_source") or _slug(data_file.path.stem)

    headers = [_clean(h) for h in headers]
    # ``canonical`` is {canonical field -> your column name}; ``by_header`` is
    # the inverse and is only used to detect duplicate mappings.
    by_header, canonical, unmapped = _map_columns(headers, extra_map)
    data_file.columns = list(headers)
    data_file.mapped = dict(canonical)
    data_file.unmapped = unmapped

    if "collection_date" not in canonical:
        data_file.errors.append(
            "no collection-date column found (expected one of: collection_date, date, "
            "observed_on, snapshot_date, timestamp …) — add one or map it in data/config.json"
        )
        return []
    if "total_fare" not in canonical and "base_fare" not in canonical:
        data_file.errors.append(
            "no fare column found (expected one of: total_fare, price, fare, amount, "
            "base_fare …) — add one or map it in data/config.json"
        )
        return []
    if "route" not in canonical and not ("origin" in canonical and "destination" in canonical):
        data_file.errors.append(
            "no route column found (expected 'route' like DEL-BOM, or both 'origin' and "
            "'destination') — add one or map it in data/config.json"
        )
        return []

    observations: list[Observation] = []
    missing_date = 0
    missing_route = 0
    missing_fare = 0
    warned: set[str] = set()

    def warn_once(message: str) -> None:
        if message not in warned:
            warned.add(message)
            data_file.warnings.append(message)

    for index, raw_row in enumerate(rows):
        row = {(_clean(k) if k is not None else ""): v for k, v in raw_row.items() if k is not None}
        if not any(_clean(v) for v in row.values()):
            continue  # blank line

        collection = _to_date(_get(row, canonical, "collection_date"), date_format)
        if collection is None:
            ts_col = _get(row, canonical, "collection_timestamp")
            collection = _to_date(ts_col, date_format)
        if collection is None:
            missing_date += 1
            continue
        collection_str = collection.isoformat()

        resolved = _resolve_route(row, canonical)
        if resolved is None:
            missing_route += 1
            continue
        route, origin, destination = resolved

        departure = _to_date(_get(row, canonical, "departure_date"), date_format)
        lead = _to_int(_get(row, canonical, "lead_time_days"))
        if lead is None and departure is not None:
            lead = (departure - collection).days
        if lead is None or lead < 0:
            lead = 0
            warn_once("some rows have no lead time (no departure_date and no lead_time column) — defaulted to 0")
        departure_str = (departure or (collection + dt.timedelta(days=lead))).isoformat()

        total = _to_float(_get(row, canonical, "total_fare"))
        base = _to_float(_get(row, canonical, "base_fare"))
        taxes = _to_float(_get(row, canonical, "taxes"))
        fees = _to_float(_get(row, canonical, "fees"))
        if total is None and (base is not None or taxes is not None or fees is not None):
            total = (base or 0.0) + (taxes or 0.0) + (fees or 0.0)
        if total is None:
            missing_fare += 1
            continue
        if base is None and taxes is None and fees is None:
            # Only a headline fare: split it the way the canonical model does.
            base, taxes, fees = total * 0.78, total * 0.16, total * 0.06
        else:
            base = base if base is not None else max(0.0, total - (taxes or 0.0) - (fees or 0.0))
            taxes = taxes if taxes is not None else 0.0
            fees = fees if fees is not None else max(0.0, total - base - taxes)

        if total <= 0:
            # Keep the row: a non-positive fare is an audit finding, not a gap.
            status, exclusion = "INVALID", "flag:non_positive_fare"
        else:
            status, exclusion = "VALID", None

        raw_airline = _get(row, canonical, "airline")
        airline_code, airline_name = _airline_code(raw_airline) if not _is_null(raw_airline) else ("NA", None)
        if airline_name and airline_code not in AIRLINES:
            _remember("airlines", airline_code, AIRLINES.get(airline_code))
            AIRLINES.setdefault(airline_code, {
                "name": airline_name, "factor": 1.0, "alliance": "Unknown", "hub": "",
            })

        source_raw = _get(row, canonical, "source")
        source_id = _slug(_clean(source_raw)) if not _is_null(source_raw) else fallback_source

        flight_number = _clean(_get(row, canonical, "flight_number")) or None
        fare_class = _clean(_get(row, canonical, "fare_class")) or None
        cabin = _clean(_get(row, canonical, "cabin")).upper() or "ECONOMY"

        availability = _normalise_availability(_get(row, canonical, "availability"))
        seats = _to_int(_get(row, canonical, "seats_remaining"))
        if availability is None and seats == 0:
            availability = "SOLD_OUT"
        if availability is None:
            availability = "AVAILABLE"

        quality_status = _normalise_quality(_get(row, canonical, "quality_status"))
        if quality_status is None:
            # A column literally called 'status' can hold either meaning.
            status_col_value = _normalise_quality(_get(row, canonical, "status"))
            if status_col_value is not None:
                quality_status = status_col_value

        observation_id = _clean(_get(row, canonical, "observation_id")) or \
            f"{_slug(data_file.path.stem)}-{index + 1:06d}"

        timestamp = _to_iso_time(_get(row, canonical, "collection_timestamp"))
        if timestamp is None:
            timestamp = f"{collection_str}T09:00:00+05:30"

        row_currency = _clean(_get(row, canonical, "currency")).upper()
        origin_city = _clean(_get(row, canonical, "origin_city"))
        destination_city = _clean(_get(row, canonical, "destination_city"))
        distance = _to_int(_get(row, canonical, "distance"))

        observations.append(
            Observation(
                observation_id=observation_id,
                source=source_id,
                origin=origin,
                destination=destination,
                route=route,
                departure_date=departure_str,
                collection_date=collection_str,
                collection_timestamp=timestamp,
                airline=airline_code,
                flight_number=flight_number,
                cabin=cabin,
                fare_class=fare_class,
                lead_time_days=int(lead),
                base_fare=round(base, 2),
                taxes=round(taxes, 2),
                fees=round(fees, 2),
                total_fare=round(total, 2),
                currency=row_currency or currency,
                availability=availability,
                seats_remaining=seats,
                raw_payload_reference=f"file:{_display_path(data_file.path)}:{index + 1}",
                fingerprint=_fingerprint(source_id, route, departure_str, airline_code,
                                         flight_number or "", fare_class or "", total),
                quality_status=status if status == "INVALID" else (quality_status or "VALID"),
                quality_score=0.0,
                exclusion_reason=exclusion,
            )
        )
        # Remember city/distance hints if the file carried them.
        obs = observations[-1]
        if origin_city or destination_city or distance:
            obs._geo_hint = {  # type: ignore[attr-defined]
                "origin_city": origin_city or None,
                "destination_city": destination_city or None,
                "distance": distance,
            }

    data_file.rows = len(rows)
    data_file.observations = len(observations)
    data_file.rejected = missing_date + missing_route + missing_fare
    for label, count in (("missing/unparseable date", missing_date),
                         ("missing origin-destination", missing_route),
                         ("missing/unparseable fare", missing_fare)):
        if count:
            data_file.warnings.append(f"{count} row(s) skipped: {label}")
    return observations


# --------------------------------------------------------------------------- #
# Quality assessment for imported rows
# --------------------------------------------------------------------------- #

def _assess_quality(observations: list[Observation]) -> dict[str, int]:
    """Flag outliers / duplicates / sold-out rows that arrived without a status.

    Rows that already carried an explicit quality status are respected as-is;
    this only fills in what the file did not say, using the same vocabulary the
    rest of the pipeline uses (see docs/DATA_DICTIONARY.md).
    """
    counts: dict[str, int] = {}
    by_group: dict[tuple[str, str], list[Observation]] = {}
    for obs in observations:
        if obs.total_fare > 0:
            by_group.setdefault((obs.route, obs.collection_date), []).append(obs)
    medians = {key: _median([o.total_fare for o in group]) for key, group in by_group.items()}

    seen: set[tuple] = set()
    for obs in observations:
        rng = random.Random(int(obs.fingerprint[:12], 16) if obs.fingerprint else 0)
        if obs.quality_status == "INVALID":
            pass  # decided at parse time (non-positive fare)
        elif obs.availability == "SOLD_OUT" or obs.seats_remaining == 0:
            obs.quality_status, obs.exclusion_reason = "SOLD_OUT", "flag:sold_out"
        else:
            key = (obs.source, obs.route, obs.collection_date, obs.departure_date,
                   obs.airline, obs.flight_number, obs.fare_class, round(obs.total_fare, 0))
            if key in seen:
                obs.quality_status, obs.exclusion_reason = "DUPLICATE", "flag:duplicate_fingerprint"
            else:
                seen.add(key)
                median = medians.get((obs.route, obs.collection_date))
                if median and median > 0:
                    ratio = obs.total_fare / median
                    if ratio >= 2.2 or ratio <= 0.40:
                        obs.quality_status = "SUSPICIOUS"
                        obs.exclusion_reason = "flag:statistical_outlier"
        obs.quality_score = round(_quality_score(obs.quality_status, rng), 4)
        counts[obs.quality_status] = counts.get(obs.quality_status, 0) + 1
    return counts


# --------------------------------------------------------------------------- #
# Reference tables (routes / airlines / sources) + route registration
# --------------------------------------------------------------------------- #

def _read_reference(files: list[DataFile], kind: str, config: dict) -> list[dict]:
    rows: list[dict] = []
    for data_file in files:
        if data_file.kind != kind:
            continue
        raw_rows, headers = read_rows(data_file.path, data_file.warnings)
        headers = [_clean(h) for h in headers]
        canonical, source_by_canonical, _ = _map_columns(
            headers, {_normalise_header(k): v for k, v in (config.get("column_map") or {}).items()}
        )
        data_file.rows = len(raw_rows)
        data_file.columns = list(headers)
        data_file.mapped = {c: h for h, c in canonical.items()}
        for raw_row in raw_rows:
            row = {(_clean(k) if k is not None else ""): v for k, v in raw_row.items() if k is not None}
            entry: dict[str, Any] = {}
            for canon, header in source_by_canonical.items():
                if canon in ("route", "origin", "destination", "origin_city",
                             "destination_city", "name", "alliance", "hub", "type",
                             "status", "compliance", "adapter", "airline", "source", "currency"):
                    entry[canon] = _clean(row.get(header))
                elif canon in ("weight", "distance", "base_fare"):
                    entry[canon] = _to_float(row.get(header))
            data_file.observations += 1
            rows.append(entry)
    return rows


def _canonicalise_route_keys(observations: list[Observation]) -> None:
    """Merge routes that differ only by an airport alias (BOM-GOI -> BOM-GOA).

    The published basket spells Goa ``GOA`` while IATA uses ``GOI``; without
    this, an import carrying the IATA code would silently register a second,
    duplicate route instead of joining the one already in the basket.
    """
    by_pair: dict[tuple[str, str], str] = {}
    for key in ROUTES:
        origin, _, destination = key.partition("-")
        by_pair.setdefault((_airport_code(origin), _airport_code(destination)), key)
    for obs in observations:
        origin, _, destination = obs.route.partition("-")
        canonical = by_pair.get((_airport_code(origin), _airport_code(destination)))
        if canonical and canonical != obs.route:
            obs.route = canonical
            obs.origin, _, obs.destination = canonical.partition("-")


def register_routes(observations: list[Observation], route_rows: list[dict],
                    config: dict) -> dict[str, Any]:
    """Make every imported route a first-class member of the basket.

    Routes already in the published basket keep their metadata (and their
    DGCA-provisional weights). New routes get an entry synthesised from the
    data, with a weight supplied by ``routes.csv``, ``config.json`` or — failing
    that — proportional to how many observations the file contains. That last
    fallback is explicitly reported as *provisional*.
    """
    _canonicalise_route_keys(observations)

    counts: dict[str, int] = {}
    cities: dict[str, dict[str, Any]] = {}
    airlines_by_route: dict[str, set[str]] = {}
    for obs in observations:
        counts[obs.route] = counts.get(obs.route, 0) + 1
        airlines_by_route.setdefault(obs.route, set()).add(obs.airline)
        hint = getattr(obs, "_geo_hint", None)
        if hint:
            cities.setdefault(obs.route, hint)

    provided: dict[str, dict] = {}
    for row in route_rows:
        key = row.get("route") or ""
        pair = _split_route(key)
        if pair is None:
            origin, destination = _clean(row.get("origin")).upper(), _clean(row.get("destination")).upper()
            if len(origin) == 3 and len(destination) == 3:
                pair = (origin, destination)
        if pair is None:
            continue
        provided[f"{pair[0]}-{pair[1]}"] = row
    for key, value in (config.get("route_weights") or {}).items():
        pair = _split_route(key)
        if pair:
            provided.setdefault(f"{pair[0]}-{pair[1]}", {}).setdefault("weight", _to_float(value))

    eligible_total = sum(
        counts.get(r, 0) for r in counts
    ) or 1
    provided_weight_sum = sum(
        float(v.get("weight") or 0.0) for k, v in provided.items() if k in counts and (v.get("weight") or 0)
    )

    weight_basis = "provided" if provided_weight_sum > 0 else "observation_share"
    registered: dict[str, dict] = {}

    for route in sorted(counts):
        origin, _, destination = route.partition("-")
        row = provided.get(route, {})
        meta = dict(ROUTES.get(route, {}))
        meta.setdefault("origin", origin)
        meta.setdefault("destination", destination)
        meta.setdefault("origin_city", _clean(row.get("origin_city")) or AIRPORT_CITIES.get(origin, origin))
        meta.setdefault("destination_city", _clean(row.get("destination_city")) or AIRPORT_CITIES.get(destination, destination))
        meta.setdefault("distance", int(row.get("distance") or 0))
        meta.setdefault("base_fare", float(row.get("base_fare") or 0.0) or None)
        if meta.get("base_fare") is None:
            fares = sorted(o.total_fare for o in observations
                           if o.route == route and o.quality_status in INDEX_ELIGIBLE)
            meta["base_fare"] = round(_median(fares), 2) if fares else 0.0

        weight = _to_float(row.get("weight"))
        if weight and weight > 0:
            meta["weight"] = float(weight)
            meta["weight_basis"] = "provided"
        else:
            share = counts[route] / eligible_total
            if provided_weight_sum > 0:
                share = share * max(0.0, 1.0 - min(provided_weight_sum, 0.999))
            meta["weight"] = max(share, 1e-6)
            meta["weight_basis"] = "observation_share"

        _remember("routes", route, ROUTES.get(route))
        ROUTES[route] = meta
        _remember("route_airlines", route, ROUTE_AIRLINES.get(route))
        ROUTE_AIRLINES[route] = sorted(airlines_by_route.get(route, set())) or list(AIRLINES)[:1]
        registered[route] = {
            "route": route,
            "origin": meta["origin"],
            "destination": meta["destination"],
            "origin_city": meta["origin_city"],
            "destination_city": meta["destination_city"],
            "distance": meta["distance"],
            "weight": round(meta["weight"], 6),
            "weight_basis": meta["weight_basis"],
            "observations": counts[route],
            "is_basket_route": route in _BUILTIN_ROUTES,
        }

    # Lead times actually present in the data widen the published ladder.
    observed_leads = sorted({o.lead_time_days for o in observations if o.lead_time_days > 0})
    for lead in observed_leads:
        if lead not in LEAD_TIMES:
            LEAD_TIMES.append(lead)
            if lead not in _registry["lead_times"]:
                _registry["lead_times"].append(lead)
    LEAD_TIMES.sort()

    return {
        "routes": registered,
        "weight_basis": weight_basis,
        "provided_weights": sum(1 for r in registered.values() if r["weight_basis"] == "provided"),
    }


def register_airlines(observations: list[Observation], airline_rows: list[dict]) -> list[dict]:
    for row in airline_rows:
        code = _clean(row.get("airline")).upper()
        if not code:
            code = _airline_code(row.get("name"))[0]
        if not code or code == "NA":
            continue
        _remember("airlines", code, AIRLINES.get(code))
        entry = AIRLINES.setdefault(code, {
            "name": _clean(row.get("name")) or code,
            "factor": 1.0, "alliance": "Unknown", "hub": "",
        })
        if row.get("name"):
            entry["name"] = _clean(row.get("name"))
        if row.get("alliance"):
            entry["alliance"] = _clean(row.get("alliance"))
        if row.get("hub"):
            entry["hub"] = _clean(row.get("hub")).upper()

    counts: dict[str, int] = {}
    for obs in observations:
        counts[obs.airline] = counts.get(obs.airline, 0) + 1
    out = []
    for code, count in sorted(counts.items(), key=lambda kv: -kv[1]):
        _remember("airlines", code, AIRLINES.get(code))
        meta = AIRLINES.setdefault(code, {
            "name": code, "factor": 1.0, "alliance": "Unknown", "hub": "",
        })
        out.append({
            "code": code, "name": meta["name"], "alliance": meta.get("alliance", "Unknown"),
            "hub": meta.get("hub", ""), "observations": count,
            "is_known_airline": code in _BUILTIN_AIRLINES,
        })
    return out


def register_sources(observations: list[Observation], source_rows: list[dict],
                     files: list[DataFile]) -> list[dict]:
    """Register each source found in the data so the Collection Monitor is honest."""
    counts: dict[str, int] = {}
    valid_counts: dict[str, int] = {}
    last_day: dict[str, str] = {}
    source_files: dict[str, set[str]] = {}
    for obs in observations:
        counts[obs.source] = counts.get(obs.source, 0) + 1
        if obs.quality_status in INDEX_ELIGIBLE:
            valid_counts[obs.source] = valid_counts.get(obs.source, 0) + 1
        if obs.collection_date > last_day.get(obs.source, ""):
            last_day[obs.source] = obs.collection_date
        ref = obs.raw_payload_reference or ""
        if ref.startswith("file:"):
            source_files.setdefault(obs.source, set()).add(ref.split(":")[1].split("/")[-1])

    meta_by_id: dict[str, dict] = {}
    for row in source_rows:
        sid = _slug(row.get("source") or row.get("name") or "")
        if not sid or sid == "import":
            continue
        meta_by_id[sid] = {
            "name": _clean(row.get("name")) or sid,
            "type": _clean(row.get("type")) or "import",
            "status": _clean(row.get("status")).lower() or "healthy",
            "compliance": _clean(row.get("compliance")) or "provided",
            "adapter": _clean(row.get("adapter")) or "FileImportAdapter",
        }

    out: list[dict] = []
    for sid, count in sorted(counts.items(), key=lambda kv: -kv[1]):
        meta = meta_by_id.get(sid, {})
        entry = {
            "id": sid,
            "name": meta.get("name") or f"Imported · {sid}",
            "type": meta.get("type") or meta.get("alliance") or "import",
            "status": meta.get("status") or "healthy",
            "adapter": meta.get("adapter") or "FileImportAdapter",
            "compliance": meta.get("compliance") or "provided",
            "base_capacity": count,
        }
        _remember("sources", sid, SOURCES.get(sid))
        SOURCES[sid] = entry
        if sid not in ACTIVE_SOURCE_IDS:
            ACTIVE_SOURCE_IDS.append(sid)
            if sid not in _registry["active_sources"]:
                _registry["active_sources"].append(sid)
        out.append({
            **entry,
            "observations": count,
            "valid_observations": valid_counts.get(sid, 0),
            "last_day": last_day.get(sid),
            "files": sorted(source_files.get(sid, set())) or sorted(f.path.name for f in files),
        })
    return out


# --------------------------------------------------------------------------- #
# Dataset assembly
# --------------------------------------------------------------------------- #

# Snapshot of the shipped catalogues so we can tell "yours" from "ours".
_BUILTIN_ROUTES: set[str] = set(ROUTES)
_BUILTIN_AIRLINES: set[str] = set(AIRLINES)
_BUILTIN_SOURCES: set[str] = set(SOURCES)
_BUILTIN_ACTIVE_SOURCES: list[str] = list(ACTIVE_SOURCE_IDS)
_BUILTIN_LEAD_TIMES: list[int] = list(LEAD_TIMES)
_BUILTIN_ROUTE_AIRLINES: dict[str, list[str]] = dict(ROUTE_AIRLINES)

# --------------------------------------------------------------------------- #
# Registration bookkeeping
# --------------------------------------------------------------------------- #
# The engine reads routes/airlines/sources from module-level catalogues, so an
# import has to *register* into them. Everything it touches is recorded here and
# rolled back before the next build: remove a file and its routes disappear too,
# instead of lingering in the basket until the process restarts.

_registry: dict[str, Any] = {
    "routes": {},        # route -> original dict or None (None = route is new)
    "airlines": {},      # code  -> original dict or None
    "sources": {},       # id    -> original dict or None
    "route_airlines": {},  # route -> original list or None
    "active_sources": [],  # ids appended to ACTIVE_SOURCE_IDS
    "lead_times": [],      # lead times appended to LEAD_TIMES
}


def _remember(bucket: str, key: str, original: Any) -> None:
    _registry[bucket].setdefault(key, original)


def reset_registrations() -> None:
    """Undo everything a previous import added to the shared catalogues."""
    for route, original in list(_registry["routes"].items()):
        if original is None:
            ROUTES.pop(route, None)
        else:
            ROUTES[route] = original
    for code, original in list(_registry["airlines"].items()):
        if original is None:
            AIRLINES.pop(code, None)
        else:
            AIRLINES[code] = original
    for sid, original in list(_registry["sources"].items()):
        if original is None:
            SOURCES.pop(sid, None)
        else:
            SOURCES[sid] = original
    for route, original in list(_registry["route_airlines"].items()):
        if original is None:
            ROUTE_AIRLINES.pop(route, None)
        else:
            ROUTE_AIRLINES[route] = original
    for sid in list(_registry["active_sources"]):
        if sid in ACTIVE_SOURCE_IDS:
            ACTIVE_SOURCE_IDS.remove(sid)
    for lead in list(_registry["lead_times"]):
        if lead not in _BUILTIN_LEAD_TIMES and lead in LEAD_TIMES:
            LEAD_TIMES.remove(lead)
    for bucket in _registry:
        _registry[bucket] = {} if isinstance(_registry[bucket], dict) else []
    LEAD_TIMES[:] = sorted(set(LEAD_TIMES))


@dataclass
class CustomData:
    """Everything the loader produced for one scan of the data directory."""

    dataset: Optional[Dataset]
    files: list[DataFile]
    routes: dict[str, dict]
    airlines: list[dict]
    sources: list[dict]
    quality: dict[str, int]
    weight_basis: str
    notes: list[str]
    config: dict

    def as_dict(self) -> dict:
        ds = self.dataset
        dates = ds.dates if ds else []
        return {
            "enabled": is_enabled(),
            "data_dir": str(data_root()),
            "active": ds is not None and bool(ds.observations),
            "origin": ds.origin if ds else "demo",
            "files": [f.as_dict() for f in self.files],
            "totals": {
                "files": len(self.files),
                "rows_in": sum(f.rows for f in self.files if f.kind == "observations"),
                "rows_skipped": sum(f.rejected for f in self.files if f.kind == "observations"),
                "observations": len(ds.observations) if ds else 0,
                "routes": len(self.routes),
                "airlines": len(self.airlines),
                "sources": len(self.sources),
                "quality": self.quality,
            },
            "date_range": {
                "start": dates[0] if dates else None,
                "end": dates[-1] if dates else None,
                "days": len(dates),
                "base_period": {
                    "start": ds.base_period_start.isoformat() if ds else None,
                    "end": ds.base_period_end.isoformat() if ds else None,
                },
            },
            "routes": sorted(self.routes.values(), key=lambda r: -r["weight"]),
            "airlines": self.airlines,
            "sources": self.sources,
            "weight_basis": self.weight_basis,
            "notes": self.notes,
        }


def build_custom_dataset(root: Optional[Path] = None) -> CustomData:
    """Scan the data directory and build a :class:`Dataset` from what is there."""
    root = Path(root) if root else data_root()
    reset_registrations()
    config = load_config(root)
    files = discover_files(
        root,
        include=config.get("include") or None,
        exclude=config.get("exclude") or None,
    )
    notes: list[str] = []

    if not files:
        notes.append(
            f"No data files found in {root}. Drop CSV/JSON fare exports there "
            "(see data/README.md) — the synthetic demo dataset is being served until you do."
        )
        return CustomData(None, [], {}, [], [], {}, "none", notes, config)

    observations: list[Observation] = []
    default_source = config.get("default_source")
    for data_file in files:
        if data_file.kind != "observations":
            continue
        rows, headers = read_rows(data_file.path, data_file.warnings)
        if not rows:
            if not data_file.errors:
                data_file.warnings.append("file is empty or has no header row")
            continue
        observations.extend(
            build_observations(rows, headers, data_file=data_file, config=config,
                               default_source=default_source)
        )

    if not observations:
        for data_file in files:
            notes.extend(data_file.errors)
        notes.append("No usable fare rows could be parsed — see the per-file errors above.")
        return CustomData(None, files, {}, [], [], {}, "none", notes, config)

    quality = _assess_quality(observations)
    route_rows = _read_reference(files, "routes", config)
    airline_rows = _read_reference(files, "airlines", config)
    source_rows = _read_reference(files, "sources", config)

    route_info = register_routes(observations, route_rows, config)
    airlines = register_airlines(observations, airline_rows)
    sources = register_sources(observations, source_rows, files)

    dates = sorted({o.collection_date for o in observations})
    start = dt.date.fromisoformat(dates[0])
    end = dt.date.fromisoformat(dates[-1])
    base_end = min(end, start + dt.timedelta(days=6))

    eligible = {
        o.route for o in observations
        if o.quality_status in INDEX_ELIGIBLE and o.route in ROUTES
    }
    index_routes = [r for r in ROUTES if r in eligible]

    ds = Dataset(
        end_date=end,
        base_period_start=start,
        base_period_end=base_end,
        origin="custom",
    )
    ds.observations = observations
    if index_routes:
        _finalize_aggregates(ds, start, end, start, base_end, index_routes=index_routes)
    if not ds.dates:
        # Nothing index-eligible (every row was rejected by the quality rules).
        # Keep the collected dates so the screens render an empty state instead
        # of dividing by a dataset with no timeline at all.
        ds.dates = sorted({o.collection_date for o in observations})
        notes.append(
            "None of the imported rows are index-eligible (every observation was flagged "
            "INVALID / SOLD_OUT / DUPLICATE / STALE / MISSING). Check the quality breakdown "
            "in /api/data/files — the dashboard has nothing to index."
        )

    ds.source_files = [f.as_dict() for f in files]
    ds.import_notes = {
        "data_dir": str(root),
        "weight_basis": route_info["weight_basis"],
        "notes": notes,
        "quality": quality,
        "sources": sources,
    }

    if route_info["weight_basis"] == "observation_share":
        notes.append(
            "Route weights are provisional: no weights were supplied, so each route is "
            "weighted by its share of observations (routes.csv or data/config.json can set them)."
        )
    skipped = sum(f.rejected for f in files if f.kind == "observations")
    if skipped:
        notes.append(f"{skipped} row(s) were skipped as unusable (no date, route or fare) — see /api/data/files for details.")
    unknown_routes = [r for r, meta in route_info["routes"].items() if not meta["is_basket_route"]]
    if unknown_routes:
        notes.append(
            f"{len(unknown_routes)} route(s) are new to the basket and were registered from your data: "
            + ", ".join(sorted(unknown_routes)[:8]) + ("…" if len(unknown_routes) > 8 else "")
        )

    return CustomData(
        dataset=ds,
        files=files,
        routes=route_info["routes"],
        airlines=airlines,
        sources=sources,
        quality=quality,
        weight_basis=route_info["weight_basis"],
        notes=notes,
        config=config,
    )


# --------------------------------------------------------------------------- #
# Cache + report (the API layer talks to these)
# --------------------------------------------------------------------------- #

_custom: Optional[CustomData] = None
_signature: Optional[tuple] = None


def signature(root: Optional[Path] = None) -> Optional[tuple]:
    """Cheap fingerprint of the data directory (paths + mtime + size + config)."""
    root = Path(root) if root else data_root()
    if not root.exists():
        return None
    parts: list[Any] = [str(root), json.dumps(load_config(root), sort_keys=True, default=str)]
    for data_file in discover_files(root):
        try:
            st = data_file.path.stat()
        except OSError:
            continue
        parts.append((str(data_file.path), st.st_mtime_ns, st.st_size))
    return tuple(parts)


def get_custom_dataset() -> Optional[Dataset]:
    """Dataset built from the user's files, rebuilt only when they change."""
    global _custom, _signature
    if not is_enabled():
        return None
    sig = signature()
    if sig is None and _custom is None:
        return None
    if _custom is None or _signature != sig:
        _custom = build_custom_dataset()
        _signature = sig
    return _custom.dataset


def import_report() -> dict:
    """Everything the UI needs to explain *which* data the dashboard is serving."""
    global _custom, _signature
    if not is_enabled():
        return {
            "enabled": False,
            "data_dir": str(data_root()),
            "active": False,
            "origin": "demo",
            "notes": ["Custom data loading is disabled (APIX_CUSTOM_DATA=0 or APIX_DATA_MODE=demo)."],
        }
    sig = signature()
    if _custom is None or _signature != sig:
        _custom = build_custom_dataset()
        _signature = sig
    return _custom.as_dict()


def invalidate_cache() -> None:
    """Force a rescan on the next call (new files land without a restart)."""
    global _custom, _signature
    _custom = None
    _signature = None


def has_custom_data() -> bool:
    ds = get_custom_dataset()
    return ds is not None and bool(ds.observations)


# --------------------------------------------------------------------------- #
# CLI:  python -m app.custom_data [paths...]
# --------------------------------------------------------------------------- #

def _main(argv: Optional[list[str]] = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(
        prog="python -m app.custom_data",
        description="Validate and preview your airfare data files.",
    )
    parser.add_argument("paths", nargs="*", help="files or directories to check (default: the data dir)")
    parser.add_argument("--dir", dest="directory", default=None, help="data directory to scan")
    args = parser.parse_args(argv)

    if args.paths:
        files: list[DataFile] = []
        for raw in args.paths:
            path = Path(raw)
            if path.is_dir():
                files.extend(discover_files(path))
            elif path.is_file():
                files.append(DataFile(path=path, kind=REFERENCE_STEMS.get(path.stem.lower(), "observations")))
            else:
                print(f"  ! not found: {raw}")
        config = load_config(Path(args.paths[0]).parent if Path(args.paths[0]).is_file() else Path(args.paths[0]))
        observations: list[Observation] = []
        for data_file in files:
            if data_file.kind != "observations":
                continue
            rows, headers = read_rows(data_file.path, data_file.warnings)
            observations.extend(build_observations(rows, headers, data_file=data_file, config=config))
        quality = _assess_quality(observations)
        print(f"\n{len(observations):,} observations parsed from {len(files)} file(s)")
        for status, count in sorted(quality.items(), key=lambda kv: -kv[1]):
            print(f"  {status:<12} {count:>8,}")
        for data_file in files:
            print(f"\n{data_file.path.name}  [{data_file.kind}]")
            print(f"  rows={data_file.rows}  observations={data_file.observations}  skipped={data_file.rejected}")
            if data_file.mapped:
                print("  mapped: " + ", ".join(f"{h} -> {c}" for c, h in sorted(data_file.mapped.items(), key=lambda kv: kv[0])))
            for message in data_file.errors + data_file.warnings:
                print(f"  ! {message}")
        return 0 if observations else 1

    report = import_report()
    print(f"data dir : {report['data_dir']}")
    print(f"active   : {report['active']}  (origin={report.get('origin')})")
    if not report["active"]:
        for note in report.get("notes", []):
            print(f"  ! {note}")
        return 1
    totals = report["totals"]
    print(f"files    : {totals['files']}   rows in: {totals['rows_in']:,}   skipped: {totals['rows_skipped']:,}")
    print(f"observations: {totals['observations']:,}")
    print(f"routes   : {totals['routes']}   airlines: {totals['airlines']}   sources: {totals['sources']}")
    print(f"dates    : {report['date_range']['start']} -> {report['date_range']['end']} ({report['date_range']['days']} days)")
    print("quality  : " + ", ".join(f"{k}={v:,}" for k, v in sorted(totals["quality"].items(), key=lambda kv: -kv[1])))
    print("weights  : " + report["weight_basis"])
    for data_file in report["files"]:
        print(f"  - {data_file['name']}: {data_file['observations']:,} obs "
              f"({data_file['rows']:,} rows, {data_file['rejected']:,} skipped)")
        for message in data_file["errors"] + data_file["warnings"]:
            print(f"      ! {message}")
    for note in report["notes"]:
        print(f"  note: {note}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(_main())
