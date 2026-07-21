def _load_api_key_tradier():
    """Load Tradier API key from env or .env file. Returns None if not set."""
    key = os.environ.get("TRADIER_API_KEY")
    if key:
        return key
    env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    if os.path.exists(env_path):
        with open(env_path, "r") as f:
            for line in f:
                line = line.strip()
                if line.startswith("TRADIER_API_KEY="):
                    val = line.split("=", 1)[1].strip().strip("'\"")
                    if val and val != "your_sandbox_token_here":
                        return val
    return None

