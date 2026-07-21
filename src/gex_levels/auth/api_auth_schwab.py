import os
import json
import base64


from gex_levels.config import BASE_DIR

SCHWAB_TOKEN_PATH = BASE_DIR / ".secret" / ".schwab_token.json"


def _schwab_refresh_token(token_data):
    """Refresh an expired Schwab access token using the stored refresh_token."""
    import requests

    # Pull the variables from the environment (the .env file) This works because load_dotenv() is executed prior to this file
    # since main.py is executed first on the CLI this file can access that variable
    client_id = os.getenv("SCHWAB_CLIENT_ID")
    client_secret = os.getenv("SCHWAB_CLIENT_SECRET")

    # Add a check to catch missing variables early
    if not client_id or not client_secret:
        raise ValueError(
            "Missing SCHWAB_CLIENT_ID or SCHWAB_CLIENT_SECRET in .env file"
        )

    auth_str = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()
    resp = requests.post(
        "https://api.schwabapi.com/v1/oauth/token",
        headers={
            "Authorization": f"Basic {auth_str}",
            "Content-Type": "application/x-www-form-urlencoded",
        },
        data={
            "grant_type": "refresh_token",
            "refresh_token": token_data["token"]["refresh_token"],
        },
        timeout=20,
    )
    resp.raise_for_status()
    new_token = resp.json()
    if "refresh_token" not in new_token:
        new_token["refresh_token"] = token_data["token"]["refresh_token"]
    token_data["token"] = new_token
    with open(SCHWAB_TOKEN_PATH, "w") as f:
        json.dump(token_data, f)
    return new_token["access_token"]


def _schwab_get(url, params):
    """GET against a Schwab endpoint, refreshing the token on 401."""
    import requests

    with open(SCHWAB_TOKEN_PATH) as f:
        token_data = json.load(f)

    def _request(access_token):
        return requests.get(
            url,
            params=params,
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=30,
        )

    resp = _request(token_data["token"]["access_token"])
    if resp.status_code == 401:
        resp = _request(_schwab_refresh_token(token_data))
    resp.raise_for_status()
    return resp.json()