"""Manual Supabase connectivity check for the access-control database setup.

Run from the project root:

    python -m tools.test_supabase_connection
"""

if __package__ in {None, ""}:
    raise SystemExit(
        "Run this helper as `python -m tools.test_supabase_connection` from the project root."
    )

from scraper.access_control import AccessControlClient, format_access_decision


def main() -> None:
    """Call the Supabase access RPC and print the access decision."""
    decision = AccessControlClient.from_environment().check_access()
    print(format_access_decision(decision))
    if decision.technical_error:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
