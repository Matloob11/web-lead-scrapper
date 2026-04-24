import re
from urllib.parse import urlparse

FREE_EMAIL_DOMAINS = {
    "gmail.com",
    "yahoo.com",
    "hotmail.com",
    "outlook.com",
    "aol.com",
    "icloud.com",
    "live.com",
    "msn.com",
    "protonmail.com",
}

GENERIC_LOCAL_PARTS = {
    "info",
    "contact",
    "service",
    "sales",
    "office",
    "admin",
    "hello",
    "support",
    "team",
}


def normalize_domain(domain):
    domain = (domain or "").lower().strip()
    return domain[4:] if domain.startswith("www.") else domain


def get_email_domain(email):
    return normalize_domain(email.rsplit("@", 1)[-1] if "@" in email else "")


def get_url_domain(url):
    parsed = urlparse(url or "")
    return normalize_domain(parsed.hostname or parsed.netloc or "")


def tokenize_name(value):
    return [token for token in re.findall(r"[a-z0-9]+", (value or "").lower()) if len(token) >= 3]


def score_email_quality(email, business_name="", website="", sources=None):
    sources = set(sources or [])
    clean_email = (email or "").lower().strip()
    local_part = clean_email.split("@", 1)[0] if "@" in clean_email else ""
    email_domain = get_email_domain(clean_email)
    website_domain = get_url_domain(website)
    website_root = website_domain.rsplit(".", 2)[0] if website_domain else ""
    name_tokens = tokenize_name(business_name)

    if website_domain and (
        email_domain == website_domain or email_domain.endswith(f".{website_domain}")
    ):
        if local_part in GENERIC_LOCAL_PARTS:
            return "high", "business_domain_generic_inbox"
        return "high", "business_domain_personal_inbox"

    if website_root and website_root in email_domain:
        return "high", "email_domain_matches_website_brand"

    if email_domain not in FREE_EMAIL_DOMAINS and any(
        token in email_domain for token in name_tokens
    ):
        return "high", "email_domain_matches_business_name"

    if email_domain in FREE_EMAIL_DOMAINS:
        if any(token in local_part for token in name_tokens):
            return "medium", "free_email_matches_business_name"
        if local_part in GENERIC_LOCAL_PARTS:
            return "low", "generic_free_email"
        return "medium", "free_email"

    if "website" in sources:
        return "medium", "third_party_or_unmatched_domain_from_website"

    if "profile" in sources or "bbb_profile" in sources or "mailto" in sources:
        return "medium", "profile_visible_email"

    return "low", "unmatched_email_source"
