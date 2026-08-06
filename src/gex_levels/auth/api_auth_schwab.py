import os
import json
import base64
import threading


from gex_levels.config import BASE_DIR

SCHWAB_TOKEN_PATH = BASE_DIR / ".secret" / ".schwab_token.json"

# One requests.Session per thread so concurrent callers (e.g. a thread pool
# fetching multiple expirations at once) get HTTP connection-pooling/keep-alive
# to api.schwabapi.com without sharing a Session object across threads.
_thread_local = threading.local()

# Guards token refresh so concurrent 401s from a thread pool don't each kick
# off a redundant refresh_token call / file write race.
_token_refresh_lock = threading.Lock()


def _get_session():
    if not hasattr(_thread_local, "session"):
        import requests

        _thread_local.session = requests.Session()
    return _thread_local.session


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


def schwab_get(url, params):
    """GET against a Schwab endpoint, refreshing the token on 401. Safe to call
    from multiple threads concurrently."""
    session = _get_session()

    with open(SCHWAB_TOKEN_PATH) as f:
        token_data = json.load(f)

    def _request(access_token):
        return session.get(
            url,
            params=params,
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=30,
        )

    resp = _request(token_data["token"]["access_token"])
    if resp.status_code == 401:
        with _token_refresh_lock:
            # Another thread may have already refreshed while we waited.
            with open(SCHWAB_TOKEN_PATH) as f:
                token_data = json.load(f)
            resp = _request(token_data["token"]["access_token"])
            if resp.status_code == 401:
                resp = _request(_schwab_refresh_token(token_data))
    resp.raise_for_status()
    return resp.json()