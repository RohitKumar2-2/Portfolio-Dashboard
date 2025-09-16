
import os, json
from dataclasses import dataclass
from dotenv import load_dotenv
from utils.helpers import clean_env_value

load_dotenv()

@dataclass
class AngelOneCreds:
    api_key: str
    client_id: str
    mpin: str
    totp_secret: str

@dataclass
class ZerodhaCreds:
    api_key: str
    api_secret: str
    access_token: str  # may be cached / refreshed later

CACHE_FILE = "zerodha_token.json"

def _load_cached_zerodha_token(env_token: str) -> str:
    if env_token:
        return env_token.strip()
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data.get("access_token", "")
        except Exception:
            return ""
    return ""

def get_angelone_credentials() -> AngelOneCreds:
    return AngelOneCreds(
        api_key=clean_env_value("API_KEY"),
        client_id=clean_env_value("CLIENT_ID"),
        mpin=clean_env_value("MPIN"),
        totp_secret=clean_env_value("TOTP_SECRET"),
    )

def get_zerodha_credentials() -> ZerodhaCreds:
    raw_token = clean_env_value("ZERODHA_ACCESS_TOKEN")
    return ZerodhaCreds(
        api_key=clean_env_value("ZERODHA_API_KEY"),
        api_secret=clean_env_value("ZERODHA_API_SECRET"),
        access_token=_load_cached_zerodha_token(raw_token),
    )

# (Optional) future: add refresh_zerodha_token() if you implement re-auth flows.
