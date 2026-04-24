import re
from urllib.parse import unquote

from scraper.config import (
    EMAIL_REGEX,
    INVALID_EMAIL_TLDS,
    PLACEHOLDER_EMAIL_DOMAINS,
    PLACEHOLDER_EMAIL_FRAGMENTS,
    REJECT_EMAIL_DOMAINS,
    STRICT_REJECT_LOCAL_FRAGMENTS,
)


def find_emails(text):
    """Extract unique valid emails from any text blob."""
    if not text:
        return set()

    emails = set()
    for match in re.findall(EMAIL_REGEX, text):
        clean_email = match.lower().strip(" \t\r\n<>\"'()[]{}.,;:")
        if is_valid_email_candidate(clean_email):
            emails.add(clean_email)
    return emails


def extract_mailto_emails(href):
    if not href or not href.lower().startswith("mailto:"):
        return set()
    return find_emails(unquote(href))


def is_placeholder_email(email):
    return any(fragment in email for fragment in PLACEHOLDER_EMAIL_FRAGMENTS)


def is_valid_email_candidate(email):
    if not email:
        return False

    clean_email = email.lower().strip()
    if not re.fullmatch(EMAIL_REGEX, clean_email):
        return False
    if is_placeholder_email(clean_email):
        return False

    local_part, domain = clean_email.rsplit("@", 1)
    if not local_part or not domain or "." not in domain:
        return False
    if domain in PLACEHOLDER_EMAIL_DOMAINS:
        return False
    if local_part.startswith(".") or local_part.endswith(".") or ".." in local_part:
        return False
    if domain.startswith(".") or domain.endswith(".") or ".." in domain:
        return False
    if any(char in domain for char in "/\\?#"):
        return False
    if domain in REJECT_EMAIL_DOMAINS or any(
        domain.endswith(f".{reject_domain}") for reject_domain in REJECT_EMAIL_DOMAINS
    ):
        return False

    tld = domain.rsplit(".", 1)[-1]
    if tld in INVALID_EMAIL_TLDS:
        return False
    if re.search(r"@\d+x\.", clean_email):
        return False

    # Strict local part filtering (e.g., houzz@..., bbb@...)
    if any(fragment in local_part for fragment in STRICT_REJECT_LOCAL_FRAGMENTS):
        return False

    domain_labels = domain.split(".")
    return not any(
        not label or label.startswith("-") or label.endswith("-") for label in domain_labels
    )
