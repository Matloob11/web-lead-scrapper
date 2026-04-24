from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIR = PROJECT_ROOT / "output"
CSV_OUTPUT_DIR = OUTPUT_DIR / "csv"
LOG_OUTPUT_DIR = OUTPUT_DIR / "logs"
FINAL_OUTPUT_DIR = PROJECT_ROOT / "final"
RUNTIME_DIR = PROJECT_ROOT / "runtime"
BROWSER_EXECUTABLE_CANDIDATES = (
    Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe"),
    Path(r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"),
    Path.home() / r"AppData\Local\Google\Chrome\Application\chrome.exe",
    Path(r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"),
    Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"),
    Path.home() / r"AppData\Local\Microsoft\Edge\Application\msedge.exe",
)

HOUZZ_OUTPUT_FILE = str(PROJECT_ROOT / "houzz_emails.csv")
BBB_OUTPUT_FILE = str(PROJECT_ROOT / "bbb_emails.csv")
OUTPUT_FILE = HOUZZ_OUTPUT_FILE

HOUZZ_FINAL_OUTPUT_FILE = str(FINAL_OUTPUT_DIR / "houzz_high_quality_emails.csv")
BBB_FINAL_OUTPUT_FILE = str(FINAL_OUTPUT_DIR / "bbb_high_quality_emails.csv")
HOUZZ_FINAL_DETAIL_FILE = str(FINAL_OUTPUT_DIR / "houzz_high_quality_email_details.csv")
BBB_FINAL_DETAIL_FILE = str(FINAL_OUTPUT_DIR / "bbb_high_quality_email_details.csv")

HOUZZ_DETAIL_OUTPUT_FILE = str(CSV_OUTPUT_DIR / "houzz_results_detailed.csv")
BBB_DETAIL_OUTPUT_FILE = str(CSV_OUTPUT_DIR / "bbb_results_detailed.csv")
DETAIL_OUTPUT_FILE = HOUZZ_DETAIL_OUTPUT_FILE

HOUZZ_STATUS_FILE = str(CSV_OUTPUT_DIR / "houzz_scrape_status.csv")
BBB_STATUS_FILE = str(CSV_OUTPUT_DIR / "bbb_scrape_status.csv")
STATUS_FILE = HOUZZ_STATUS_FILE

LEGACY_PROGRESS_FILE = str(CSV_OUTPUT_DIR / "scraped_links.txt")
HOUZZ_FAIL_LOG_FILE = str(LOG_OUTPUT_DIR / "houzz_scrape_failures.csv")
BBB_FAIL_LOG_FILE = str(LOG_OUTPUT_DIR / "bbb_scrape_failures.csv")
FAIL_LOG_FILE = HOUZZ_FAIL_LOG_FILE
USER_DATA_DIR = str(RUNTIME_DIR / "user_data")

EMAIL_REGEX = r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}"
PLACEHOLDER_EMAIL_FRAGMENTS = ("user@domain.com", "email@address.com", "example@")
PLACEHOLDER_EMAIL_DOMAINS = {
    "example.com",
    "example.org",
    "example.net",
    "test.com",
}
INVALID_EMAIL_TLDS = {
    "png",
    "jpg",
    "jpeg",
    "gif",
    "webp",
    "svg",
    "ico",
    "bmp",
    "tif",
    "tiff",
    "avif",
    "js",
    "css",
    "json",
    "xml",
    "pdf",
    "zip",
    "rar",
    "7z",
    "gz",
    "mp3",
    "wav",
    "mp4",
    "mov",
    "webm",
    "woff",
    "woff2",
    "ttf",
    "otf",
    "eot",
}

RETRY_ATTEMPTS = 2
PROFILE_TIMEOUT_MS = 15000
BBB_SEARCH_TIMEOUT_MS = 18000
BBB_PROFILE_TIMEOUT_MS = 15000
REDIRECT_TIMEOUT_MS = 7000
SITE_TIMEOUT_MS = 10000
CONTACT_TIMEOUT_MS = 8000
FACEBOOK_TIMEOUT_MS = 9000
GOOGLE_TIMEOUT_MS = 10000
GOOGLE_RESULT_LIMIT = 3
DEFAULT_SEARCH_COUNTRY = "USA"
CONCURRENT_PROFILES = 4

USER_AGENTS = [
    (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"
    ),
    (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"
    ),
    (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"
    ),
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:124.0) Gecko/20100101 Firefox/124.0",
    (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Safari/605.1.15"
    ),
]

MASTER_HEADERS = ["Email"]
FINAL_DETAIL_HEADERS = ["Email"]
STATUS_HEADERS = ["profile_url", "status", "detail", "updated_at"]
GOOGLE_FALLBACK_STATUS_FILE = str(PROJECT_ROOT / "google_fallback_search_status.csv")
GOOGLE_FALLBACK_STATUS_HEADERS = [
    "profile_url",
    "name",
    "location",
    "country",
    "query",
    "status",
    "candidate_count",
    "first_candidate",
    "detail",
    "updated_at",
]
DETAIL_HEADERS = [
    "email",
    "name",
    "houzz_profile",
    "website",
    "facebook",
    "sources",
    "email_quality",
    "email_quality_reason",
    "saved_to_master_output",
]

FOLLOWUP_PATHS = (
    "/contact",
    "/contact-us",
    "/contactus",
    "/about",
    "/about-us",
    "/aboutus",
    "/get-in-touch",
    "/support",
)
FOLLOWUP_PAGE_LIMIT = 3

HOUZZ_DOMAIN_COUNTRIES = {
    "houzz.com": "USA",
    "houzz.ca": "Canada",
    "houzz.co.uk": "UK",
    "houzz.com.au": "Australia",
    "houzz.de": "Germany",
    "houzz.fr": "France",
    "houzz.it": "Italy",
    "houzz.es": "Spain",
    "houzz.in": "India",
    "houzz.ie": "Ireland",
}

COUNTRY_HINTS = {
    "united states": "USA",
    "united-states": "USA",
    "usa": "USA",
    "us": "USA",
    "canada": "Canada",
    "uk": "UK",
    "united kingdom": "UK",
    "australia": "Australia",
    "germany": "Germany",
    "france": "France",
    "italy": "Italy",
    "spain": "Spain",
    "india": "India",
    "ireland": "Ireland",
}

FACEBOOK_REJECT_FIRST_SEGMENTS = {
    "houzz",
    "sharer",
    "share",
    "plugins",
    "login",
    "recover",
    "help",
    "privacy",
    "policies",
    "terms",
    "settings",
    "search",
    "events",
    "marketplace",
    "watch",
    "gaming",
    "groups",
}

BUSINESS_NAME_STOPWORDS = {
    "and",
    "the",
    "a",
    "an",
    "llc",
    "inc",
    "corp",
    "corporation",
    "company",
    "co",
    "ltd",
    "limited",
}

TARGET_BUSINESS_KEYWORDS = (
    "contractor",
    "contractors",
    "construction",
    "remodel",
    "remodeling",
    "renovation",
    "renovations",
    "builder",
    "builders",
    "building",
    "home improvement",
    "home improvements",
    "design build",
    "design-build",
    "kitchen",
    "bath",
    "bathroom",
    "electric",
    "electrical",
    "electrician",
    "plumbing",
    "roofing",
    "concrete",
    "masonry",
    "flooring",
    "painting",
    "drywall",
    "hvac",
    "air conditioning",
    "landscape",
    "landscaping",
    "architect",
    "architecture",
    "carpentry",
    "real estate",
    "real-estate",
    "realtor",
    "realty",
    "property",
    "properties",
    "broker",
    "brokerage",
    "developer",
    "development",
)

TARGET_BUSINESS_REJECT_KEYWORDS = (
    "restaurant",
    "dentist",
    "medical",
    "doctor",
    "attorney",
    "lawyer",
    "accountant",
    "insurance",
    "auto repair",
    "car dealer",
    "hotel",
    "salon",
    "spa",
    "pet",
    "school",
    "church",
)

REJECT_WEBSITE_HOST_KEYWORDS = (
    "bbb.org",
    "bbbmarketplacetrust.org",
    "give.org",
    "bbbprograms.org",
    "cslb.ca.gov",
    "ca.gov",
    "gov",
    "facebook.com",
    "instagram.com",
    "linkedin.com",
    "x.com",
    "twitter.com",
    "youtube.com",
)

REJECT_EMAIL_DOMAINS = (
    "cslb.ca.gov",
    "ca.gov",
    "bbb.org",
    "thinkservice-email.com",
)

STRICT_REJECT_LOCAL_FRAGMENTS = (
    "houzz",
    "bbb",
    "noreply",
    "no-reply",
)
