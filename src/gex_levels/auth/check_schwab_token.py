import os
import json
import time

from dotenv import load_dotenv

from gex_levels.auth.api_auth_schwab import SCHWAB_TOKEN_PATH

REFRESH_TOKEN_LIFETIME_DAYS = 7
REAUTH_BUFFER_DAYS = 0.5  # trigger reauth this much early, rather than waiting to hit the exact cutoff


def token_age_days() -> float:
    with open(SCHWAB_TOKEN_PATH) as f:
        token_data = json.load(f)
    return (time.time() - token_data["creation_timestamp"]) / 86400


def main():
    age = token_age_days()
    remaining = REFRESH_TOKEN_LIFETIME_DAYS - age
    print(f"Schwab refresh token age: {age:.2f} days ({remaining:.2f} days remaining)")

    if remaining > REAUTH_BUFFER_DAYS:
        print("Token still valid, nothing to do.")
        return

    print("Refresh token expired or about to expire — starting manual re-auth flow.")
    print("A login URL will be printed below. Log in, then paste the full redirect URL back here.")

    load_dotenv()
    from schwab.auth import client_from_manual_flow

    client_id = os.getenv("SCHWAB_CLIENT_ID")
    client_secret = os.getenv("SCHWAB_CLIENT_SECRET")
    callback_url = os.getenv("SCHWAB_CALLBACK_URL")
    if not client_id or not client_secret or not callback_url:
        raise ValueError("Missing SCHWAB_CLIENT_ID / SCHWAB_CLIENT_SECRET / SCHWAB_CALLBACK_URL in .env")

    client_from_manual_flow(
        api_key=client_id,
        app_secret=client_secret,
        callback_url=callback_url,
        token_path=str(SCHWAB_TOKEN_PATH),
    )
    print(f"New token written to {SCHWAB_TOKEN_PATH}")


if __name__ == "__main__":
    main()
