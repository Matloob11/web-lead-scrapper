"""General text and URL utility helpers used by the scraper."""

import base64
import re
from binascii import Error as BinasciiError
from urllib.parse import unquote, urlparse

from scraper.config import (
    COUNTRY_HINTS,
    DEFAULT_SEARCH_COUNTRY,
    HOUZZ_DOMAIN_COUNTRIES,
)


def normalize_external_url(url):
    """Normalize external URLs into a browser-friendly absolute form when possible."""
    if not url:
        return ""

    cleaned = url.strip()
    if cleaned.startswith("//"):
        return f"https:{cleaned}"
    if re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*://", cleaned):
        return cleaned
    if cleaned.startswith("/"):
        return cleaned
    if "." in cleaned and " " not in cleaned:
        return f"https://{cleaned.lstrip('/')}"
    return cleaned


def compact_whitespace(value):
    """Collapse repeated whitespace into single spaces and trim the result."""
    return re.sub(r"\s+", " ", value or "").strip()


def infer_country_from_url(input_url):
    """Infer a country hint from a URL based on Houzz domains and slug text."""
    normalized_url = normalize_external_url(input_url)
    parsed = urlparse(normalized_url)
    hostname = (parsed.hostname or parsed.netloc or "").lower()

    domains = sorted(HOUZZ_DOMAIN_COUNTRIES.items(), key=lambda item: len(item[0]), reverse=True)
    for domain, country in domains:
        if hostname == domain or hostname.endswith(f".{domain}"):
            return country

    url_text = unquote(f"{parsed.path} {parsed.query}").lower().replace("_", " ")
    for hint, country in COUNTRY_HINTS.items():
        if hint in url_text:
            return country

    return DEFAULT_SEARCH_COUNTRY


def unique_preserve_order(values):
    """Return unique values while preserving their original order."""
    return list(dict.fromkeys(values))


def merge_email_sources(source_map, emails, source_name):
    """Attach a source label to each email in the provided source mapping."""
    for email in emails:
        clean_email = email.lower().strip()
        source_map.setdefault(clean_email, set()).add(source_name)


def decode_houzz_trk_link(url):
    """
    Houzz tracking links often contain a base64-encoded URL or handle after /trk/.
    Example URL: https://www.houzz.com/trk/aHR0cDovL2duYnVpbGRlcnMuaG91enouY29t/...
    Example Handle: https://www.houzz.com/trk/QHJqdGN1c3RvbWJ1aWxkZXJz/... (@rjtcustombuilders)
    """
    if not url or "/trk/" not in url:
        return ""

    try:
        # Extract the segment immediately following /trk/
        parts = url.split("/trk/")[1].split("/")
        if not parts:
            return ""

        encoded_segment = unquote(parts[0])
        # Quick check: if it's already a plain URL or handle, return it (unlikely but safe)
        if encoded_segment.startswith("http") or encoded_segment.startswith("@"):
            return encoded_segment

        # Pad base64 if needed
        missing_padding = len(encoded_segment) % 4
        if missing_padding:
            encoded_segment += "=" * (4 - missing_padding)

        try:
            decoded = (
                base64.urlsafe_b64decode(encoded_segment)
                .decode("utf-8", errors="ignore")
                .strip()
            )
        except (BinasciiError, UnicodeDecodeError, ValueError):
            return ""

        if not decoded:
            return ""

        # Case 1: Decoded is a full URL
        if decoded.startswith("http"):
            return decoded

        # Case 2: Decoded is a domain (e.g., gnbuilders.houzz.com)
        if "." in decoded and "/" not in decoded and " " not in decoded:
            return f"https://{decoded}"

        # Case 3: Decoded is a Facebook handle (e.g., @rjtcustombuilders)
        if decoded.startswith("@"):
            handle = decoded.lstrip("@")
            return f"https://www.facebook.com/{handle}"

        # Case 4: Decoded is a plain string that might be a Facebook handle (e.g., KBR Builders Inc)
        # We only return this if it looks like a single word handle or we are in a Facebook context.
        # But for now, let's stick to obvious ones to avoid false positives.

    except (BinasciiError, UnicodeDecodeError, ValueError):
        pass
    return ""
