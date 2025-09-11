import argparse
import json
import os
import datetime
from kiteconnect import KiteConnect

CACHE_FILE = "zerodha_token.json"

def main():
    p = argparse.ArgumentParser(description="Exchange Zerodha request_token for access_token.")
    p.add_argument("--api-key", required=True)
    p.add_argument("--api-secret", required=True)
    p.add_argument("--request-token", required=True)
    p.add_argument("--write-env", action="store_true", help="Append/replace ZERODHA_ACCESS_TOKEN line in .env")
    args = p.parse_args()

    kite = KiteConnect(api_key=args.api_key)
    try:
        data = kite.generate_session(args.request_token, api_secret=args.api_secret)
    except Exception as e:
        print("ERROR: Failed to exchange request_token:", e)
        return

    access_token = data["access_token"]
    public_token = data.get("public_token")

    # Save to cache file
    payload = {
        "access_token": access_token,
        "public_token": public_token,
        "generated_at": datetime.datetime.now().isoformat()
    }
    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
    print(f"\nSaved access token to {CACHE_FILE}")

    if args.write_env:
        # Safely update .env
        lines = []
        if os.path.exists(".env"):
            with open(".env", "r", encoding="utf-8") as f:
                lines = f.readlines()
        # Remove existing line(s)
        lines = [ln for ln in lines if not ln.startswith("ZERODHA_ACCESS_TOKEN=")]
        lines.append(f"ZERODHA_ACCESS_TOKEN={access_token}\n")
        with open(".env", "w", encoding="utf-8") as f:
            f.writelines(lines)
        print("Updated .env with ZERODHA_ACCESS_TOKEN")

    print("\nSUCCESS")
    print("Access token (store for today only):", access_token)
    print("Public token:", public_token)
    print("NOTE: Do NOT reuse the request_token. Access token valid until end of day.")

if __name__ == "__main__":
    main()