from SmartApi import SmartConnect
import pyotp
import pandas as pd
import streamlit as st
from kiteconnect import KiteConnect, exceptions
import logging, traceback, re

def fetch_portfolio(api_key, client_id, mpin, totp_secret):
    """Fetch live portfolio and CMP from Angel One SmartAPI safely using MPIN."""
    try:
        obj = SmartConnect(api_key=api_key)

        # Generate session with MPIN + TOTP
        totp = pyotp.TOTP(totp_secret).now()
        session = obj.generateSession(client_id, mpin, totp)

        if "data" not in session or "jwtToken" not in session["data"]:
            st.error(f"❌ Login failed: {session}")
            return pd.DataFrame()

        st.sidebar.success("✅ SmartAPI login successful")

        # Fetch holdings
        holdings_resp = obj.holding()
        if not holdings_resp or "data" not in holdings_resp or not holdings_resp["data"]:
            st.warning("⚠️ No holdings returned from API")
            return pd.DataFrame()

        df = pd.DataFrame(holdings_resp["data"])

        # Standardize + keep token and exchange
        df.rename(columns={
            "tradingsymbol": "instrument",
            "averageprice": "avg_price",
            "quantity": "qty",
            "symboltoken": "symboltoken",
            "exchange": "exchange"
        }, inplace=True)

        # Fetch CMP for each stock
        ltps = []
        for _, row in df.iterrows():
            try:
                exch = row.get("exchange", "NSE")
                token = row.get("symboltoken")
                if not token:
                    raise ValueError("Missing symboltoken")
                ltp_data = obj.ltpData(exch, row["instrument"], token)
                ltps.append(ltp_data["data"]["ltp"])
            except Exception as e:
                st.warning(f"⚠️ Failed LTP for {row['instrument']}: {e}")
                ltps.append(0)

        df["ltp"] = ltps
        df["invested"] = df["qty"] * df["avg_price"]
        df["cur_val"] = df["qty"] * df["ltp"]
        df["pl"] = df["cur_val"] - df["invested"]

        return df[["instrument", "qty", "avg_price", "ltp", "invested", "cur_val", "pl"]]

    except Exception as e:
        st.error(f"❌ Portfolio fetch failed: {e}")
        return pd.DataFrame()

def fetch_zerodha_portfolio(api_key: str, api_secret: str, access_token: str):
    """
    Use already-generated access_token (valid for the trading day).
    """
    if not api_key or not access_token:
        logging.error("Zerodha: Missing api_key or access_token.")
        return pd.DataFrame()

    api_key = api_key.strip()
    access_token = access_token.strip()

    try:
        kite = KiteConnect(api_key=api_key)
        kite.set_access_token(access_token)

        # Validate
        try:
            kite.profile()
        except exceptions.TokenException as e:
            logging.error("Zerodha auth failed: %s", e)
            return pd.DataFrame()

        holdings = kite.holdings() or []
        rows = []
        for h in holdings:
            qty = float(h.get("quantity") or 0)
            avg = float(h.get("average_price") or 0)
            ltp = float(h.get("last_price") or 0)
            invested = avg * qty
            pnl_abs = (ltp - avg) * qty
            pnl_pct = ((ltp - avg) / avg * 100) if avg else 0
            rows.append({
                "instrument": h.get("tradingsymbol"),
                "quantity": qty,
                "avg_price": round(avg, 2),
                "ltp": round(ltp, 2),
                "invested": round(invested, 2),
                "pnl_abs": round(pnl_abs, 2),
                "pnl_pct": round(pnl_pct, 2),
            })
        return pd.DataFrame(rows).sort_values("instrument").reset_index(drop=True)
    except Exception as e:
        logging.error("Zerodha unexpected error: %s", e)
        traceback.print_exc()
        return pd.DataFrame()
