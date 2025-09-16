import streamlit as st
import pandas as pd
import json, os

from modules.auth import get_angelone_credentials, get_zerodha_credentials
from utils.comparison import compute_common_unique
from utils.helpers import clean_env_value  # still used elsewhere if needed
from services.smartapi_service import (
    fetch_portfolio as fetch_angelone_portfolio,
    fetch_zerodha_portfolio
)
from modules.compare_tab import render_compare_tab
from modules.alerts_tab import render_alerts_tab
from modules.overview_tab import render_overview_tab

st.set_page_config(page_title="WHALESTREET DASHBOARD | Portfolio Dashboard",
                   layout="wide", page_icon="📊")
st.title("📊 Portfolio Dashboard")

# -------- Auth & Credentials --------
angel_creds = get_angelone_credentials()
zerodha_creds = get_zerodha_credentials()

# -------- Utility --------
def refresh_portfolios():
    for k in list(st.session_state.keys()):
        if k.startswith("portfolio_"):
            del st.session_state[k]

if st.button("🔄 Refresh Portfolios"):
    refresh_portfolios()
    st.rerun()

def get_or_fetch(key, fetch_fn, *args, **kw):
    skey = f"portfolio_{key}"
    if skey not in st.session_state:
        st.session_state[skey] = fetch_fn(*args, **kw)
    return st.session_state[skey]

def normalize_and_enrich(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame()
    df = df.copy()

    # Standardize column names
    for c in ["instrument","tradingsymbol","trading_symbol","symbol","name"]:
        if c in df.columns:
            df.rename(columns={c: "instrument"}, inplace=True); break
    for c in ["quantity","qty","QTY","Quantity"]:
        if c in df.columns and c != "quantity":
            df.rename(columns={c:"quantity"}, inplace=True); break
    for c in ["avg_price","average_price","Average Price","avgPrice","Avg. cost","avg_cost","avg_cost_price"]:
        if c in df.columns and c != "avg_price":
            df.rename(columns={c:"avg_price"}, inplace=True); break
    for c in ["ltp","LTP","last_price","last_traded_price","close_price"]:
        if c in df.columns and c != "ltp":
            df.rename(columns={c:"ltp"}, inplace=True); break

    if "invested" not in df.columns and {"avg_price","quantity"}.issubset(df.columns):
        df["invested"] = (df["avg_price"].fillna(0)*df["quantity"].fillna(0)).round(2)
    else:
        df["invested"] = df.get("invested", 0).fillna(0)

    if "pnl_abs" not in df.columns and {"avg_price","ltp","quantity"}.issubset(df.columns):
        df["pnl_abs"] = ((df["ltp"]-df["avg_price"])*df["quantity"]).round(2)
    else:
        df["pnl_abs"] = df.get("pnl_abs", 0).fillna(0)

    if "pnl_pct" not in df.columns and {"avg_price","ltp"}.issubset(df.columns):
        df["pnl_pct"] = ((df["ltp"]-df["avg_price"])/df["avg_price"]).replace([pd.NA],0)*100
    df["pnl_pct"] = df.get("pnl_pct", 0).fillna(0).round(2)
    return df

# -------- Fetch Data --------
angel_df = normalize_and_enrich(
    get_or_fetch("AngelOne",
                 fetch_angelone_portfolio,
                 angel_creds.api_key,
                 angel_creds.client_id,
                 angel_creds.mpin,
                 angel_creds.totp_secret)
)
zerodha_df = normalize_and_enrich(
    get_or_fetch("Zerodha",
                 fetch_zerodha_portfolio,
                 zerodha_creds.api_key,
                 zerodha_creds.api_secret,
                 zerodha_creds.access_token)
)

dfs = {"AngelOne": angel_df, "Zerodha": zerodha_df}
valid_dfs = {k:v for k,v in dfs.items() if not v.empty and "instrument" in v.columns}
common_list, unique_per = compute_common_unique(valid_dfs)

# -------- Tabs --------
tab_compare, tab_alerts, tab_overview = st.tabs(["Compare","Alerts","Overview"])

with tab_compare:
    render_compare_tab(valid_dfs, common_list, unique_per)

with tab_alerts:
    render_alerts_tab(valid_dfs)

with tab_overview:
    render_overview_tab(dfs)
