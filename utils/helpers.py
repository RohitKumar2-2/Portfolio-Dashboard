import os

def clean_env_value(key: str) -> str:
    """Fetch and sanitize environment variables (strip spaces, quotes, hidden chars)."""
    val = os.getenv(key, "")
    if not val:
        return ""
    return val.strip().replace('"', '').replace("'", "")

def rupees(x: float) -> str:
    try:
        return f"₹{x:,.2f}"
    except Exception:
        return f"₹{x}"
