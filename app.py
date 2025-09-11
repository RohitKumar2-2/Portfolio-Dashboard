import streamlit as st
import pandas as pd
from dotenv import load_dotenv
import json, os

from utils.helpers import clean_env_value
from utils.comparison import compute_common_unique
from utils.alerts import generate_alerts
from utils.highlights import portfolio_highlights
from services.smartapi_service import (
    fetch_portfolio as fetch_angelone_portfolio,
    fetch_zerodha_portfolio
)

load_dotenv()

# AngelOne creds (already existed)
api_key = clean_env_value("API_KEY")
client_id = clean_env_value("CLIENT_ID")
mpin = clean_env_value("MPIN")
totp_secret = clean_env_value("TOTP_SECRET")

# Zerodha creds (add these to .env)
zerodha_api_key = clean_env_value("ZERODHA_API_KEY")
zerodha_api_secret = clean_env_value("ZERODHA_API_SECRET")
zerodha_access_token = clean_env_value("ZERODHA_ACCESS_TOKEN")  # or logic to create one

TOKEN_CACHE = "zerodha_token.json"

def load_cached_zerodha_token(env_token: str):
    if env_token:
        return env_token.strip()
    if os.path.exists(TOKEN_CACHE):
        try:
            data = json.load(open(TOKEN_CACHE, "r", encoding="utf-8"))
            return data.get("access_token", "")
        except Exception:
            return ""
    return ""

zerodha_access_token = load_cached_zerodha_token(zerodha_access_token)

st.set_page_config(page_title="WHALESTREET DASHBOARD | Portfolio Dashboard", layout="wide", page_icon="📊")
st.title("📊 Portfolio Dashboard")

# Sidebar Alert Rules
with st.sidebar:
    st.header("⚙️ Alert Rules")
    uniq_loss_thresh = st.number_input("Unique loss threshold (%)", value=5.0, min_value=0.0, step=0.5)
    common_small_loss = st.number_input("Common small loss (%)", value=5.0, min_value=0.0, step=0.5)
    common_large_loss = st.number_input("Common large loss (%)", value=7.0, min_value=0.0, step=0.5)
    small_amt = st.number_input("Small invest max (₹)", value=100000.0, step=5000.0)
    large_amt = st.number_input("Large invest min (₹)", value=150000.0, step=5000.0)
    profit_small_pct = st.number_input("Profit small (%)", value=10.0, min_value=0.0, step=0.5)
    profit_large_pct = st.number_input("Profit large (%)", value=6.0, min_value=0.0, step=0.5)

# Refresh
if st.button("🔄 Refresh Portfolios"):
    for k in list(st.session_state.keys()):
        if k.startswith("portfolio_"):
            del st.session_state[k]
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

    # Standardize instrument column
    inst_candidates = ["instrument", "tradingsymbol", "trading_symbol", "symbol", "name"]
    for c in inst_candidates:
        if c in df.columns:
            df.rename(columns={c: "instrument"}, inplace=True)
            break

    # Quantity
    qty_candidates = ["quantity", "qty", "QTY", "Quantity"]
    qty_col = next((c for c in qty_candidates if c in df.columns), None)
    if qty_col and qty_col != "quantity":
        df.rename(columns={qty_col: "quantity"}, inplace=True)

    # Average price
    avg_candidates = ["avg_price", "average_price", "Average Price", "avgPrice", "Avg. cost", "avg_cost", "avg_cost_price"]
    avg_col = next((c for c in avg_candidates if c in df.columns), None)
    if avg_col and avg_col != "avg_price":
        df.rename(columns={avg_col: "avg_price"}, inplace=True)

    # Last traded price
    ltp_candidates = ["ltp", "LTP", "last_price", "last_traded_price", "close_price"]
    ltp_col = next((c for c in ltp_candidates if c in df.columns), None)
    if ltp_col and ltp_col != "ltp":
        df.rename(columns={ltp_col: "ltp"}, inplace=True)

    # Invested
    if "invested" not in df.columns:
        if {"avg_price", "quantity"}.issubset(df.columns):
            df["invested"] = (df["avg_price"].fillna(0) * df["quantity"].fillna(0)).round(2)
        else:
            df["invested"] = 0.0

    # Absolute P&L (try existing first)
    if "pnl_abs" not in df.columns:
        pl_candidates = ["pl", "P&L"]
        pl_col = next((c for c in pl_candidates if c in df.columns), None)
        if pl_col:
            df["pnl_abs"] = df[pl_col]
        elif {"avg_price", "ltp", "quantity"}.issubset(df.columns):
            df["pnl_abs"] = ((df["ltp"] - df["avg_price"]) * df["quantity"]).round(2)
        else:
            df["pnl_abs"] = 0.0

    # Percentage P&L
    if "pnl_pct" not in df.columns:
        with pd.option_context("mode.use_inf_as_na", True):
            df["pnl_pct"] = (
                df.apply(
                    lambda r: ((r["ltp"] - r["avg_price"]) / r["avg_price"] * 100)
                    if r.get("avg_price", 0) else 0,
                    axis=1
                )
                if {"avg_price", "ltp"}.issubset(df.columns) else 0
            )
    df["pnl_pct"] = df["pnl_pct"].fillna(0).round(2)

    return df

# Fetch both API portfolios
angel_df = normalize_and_enrich(
    get_or_fetch("AngelOne", fetch_angelone_portfolio, api_key, client_id, mpin, totp_secret)
)
zerodha_df = normalize_and_enrich(
    get_or_fetch("Zerodha", fetch_zerodha_portfolio,
                 zerodha_api_key, zerodha_api_secret, zerodha_access_token)
)

dfs = {
    "AngelOne": angel_df,
    "Zerodha": zerodha_df
}

valid_dfs = {k: v for k, v in dfs.items() if not v.empty and "instrument" in v.columns}
common_list, unique_per = compute_common_unique(valid_dfs)

# ---- Unified Stocks Table (replaces previous status + table block) ----
import pandas as pd

# Build base table (all symbols, all portfolio % columns)
if valid_dfs:
    # Build master table once
    all_symbols = sorted(set().union(*[df["instrument"] for df in valid_dfs.values()]))
    rows = []
    for sym in all_symbols:
        present = []
        pct_map = {}
        for pname, dfp in valid_dfs.items():
            match = dfp[dfp["instrument"] == sym]
            if not match.empty:
                present.append(pname)
                pct_map[pname] = float(match.iloc[0].get("pnl_pct", 0))
        avg_pct_all = round(sum(pct_map.values()) / len(pct_map), 2) if pct_map else 0
        rows.append({
            "Stock": sym,
            "Portfolios": present,
            "Avg % Up/Down": avg_pct_all,
            **{f"{p} % Up/Down": pct_map.get(p, 0) for p in valid_dfs.keys()}
        })
    table_df = pd.DataFrame(rows)

    # Force 2‑decimals now
    pct_cols_all = [c for c in table_df.columns if c.endswith("% Up/Down")]
    for c in pct_cols_all:
        table_df[c] = pd.to_numeric(table_df[c], errors="coerce").round(2)

    st.subheader("📌 Stocks Across Portfolios")

    # Session state init
    if "portfolio_filter" not in st.session_state:
        st.session_state["portfolio_filter"] = []

    # Clear callback BEFORE widget instantiation
    def clear_filters():
        st.session_state["portfolio_filter"] = []

    top_cols = st.columns([0.8, 0.2])
    with top_cols[1]:
        st.button("Clear All Filters", on_click=clear_filters)

    with top_cols[0]:
        portfolio_options = list(valid_dfs.keys())
        st.multiselect(
            "Filter with Portfolios",
            options=portfolio_options,
            key="portfolio_filter"
        )

    selected_ports = st.session_state["portfolio_filter"]

    disp = table_df.copy()

    if selected_ports:
        # Intersection: stock must be in ALL selected portfolios
        disp = disp[disp["Portfolios"].apply(lambda lst: all(p in lst for p in selected_ports))].copy()
        sel_pct_cols = [f"{p} % Up/Down" for p in selected_ports]
        # Recompute average for selected only
        if sel_pct_cols:
            disp["Avg % Up/Down"] = disp[sel_pct_cols].mean(axis=1).round(2)
        # Keep only relevant % columns
        keep_cols = ["Stock", "Portfolios", "Avg % Up/Down"] + sel_pct_cols
        disp = disp[keep_cols]
    else:
        # No selection: show all; replace 0 with NA in % columns (including Avg)
        pct_cols_all = [c for c in disp.columns if c.endswith("% Up/Down")]
        disp[pct_cols_all] = disp[pct_cols_all].replace(0, pd.NA)

    # Portfolios list -> string
    disp["Portfolios"] = disp["Portfolios"].apply(lambda x: ", ".join(x))

    # Style function
    def color_pct(val):
        if pd.isna(val):
            return "color:#888;"
        try:
            v = float(val)
        except Exception:
            return ""
        if v > 0:
            return "color:green;font-weight:600;"
        if v < 0:
            return "color:red;font-weight:600;"
        return "color:#555;"

    pct_cols_for_style = [c for c in disp.columns if c.endswith("% Up/Down")]

    styled = (
        disp.style
            .applymap(color_pct, subset=pct_cols_for_style)
            .format(
                subset=pct_cols_for_style,
                formatter=lambda v: "NA" if pd.isna(v) else f"{float(v):.2f}"
            )
    )

    st.dataframe(styled, use_container_width=True)
else:
    st.warning("No valid portfolio data.")

# Alerts (optional – uses existing logic)
if valid_dfs:
    alerts_df = generate_alerts(
        valid_dfs, common_list, unique_per,
        uniq_loss_thresh=uniq_loss_thresh,
        common_small_loss=common_small_loss,
        common_large_loss=common_large_loss,
        small_amt=small_amt,
        large_amt=large_amt,
        profit_small_pct=profit_small_pct,
        profit_large_pct=profit_large_pct
    )
    st.subheader("🚨 Alerts & Opportunities")

    if alerts_df.empty:
        st.info("No alerts triggered.")
    else:
        mode = st.radio("View Mode", ["Portfolio wise", "Alerts wise"], horizontal=True)

        # Helper to render category cards
        def render_category_cards(df_subset):
            category_styles = {
                "Yellow": ("🟨 Opportunity", "background:#fff7e6"),
                "Red": ("🟥 Average Out", "background:#ffeaea"),
                "Green": ("🟩 Book Profit", "background:#e9fff1"),
            }
            for cat, (title, css) in category_styles.items():
                cat_df = df_subset[df_subset["category"] == cat]
                if cat_df.empty:
                    continue
                st.markdown(f"### {title}")
                for _, r in cat_df.iterrows():
                    st.markdown(
                        f"<div style='{css};padding:8px;border-radius:6px;margin-bottom:6px'>"
                        f"<b>{r['instrument']}</b><br>"
                        f"<small>{r['message']}<br>"
                        f"Rule: {r['rule']} | Portfolio: {r['portfolio']}</small>"
                        f"</div>",
                        unsafe_allow_html=True
                    )

        if mode == "Portfolio wise":
            port_choice = st.selectbox("Select Portfolio", list(valid_dfs.keys()))
            p_df = alerts_df[alerts_df["portfolio"] == port_choice]
            if p_df.empty:
                st.warning("No alerts for this portfolio.")
            else:
                render_category_cards(p_df)

        else:  # Alerts wise
            c1, c2, c3 = st.columns([0.25, 0.25, 0.25])
            with c1:
                show_yellow = st.checkbox("Opportunity (Yellow)", value=True)
            with c2:
                show_red = st.checkbox("Average Out (Red)", value=True)
            with c3:
                show_green = st.checkbox("Book Profit (Green)", value=True)
            

            chosen = []
            if show_yellow: chosen.append("Yellow")
            if show_red: chosen.append("Red")
            if show_green: chosen.append("Green")

            if not chosen:
                st.info("Select at least one alert category.")
            else:
                filtered = alerts_df[alerts_df["category"].isin(chosen)]
                render_category_cards(filtered)

# Highlights
st.subheader("⭐ Highlights & 📂 Holdings")
c1, c2 = st.columns(2)

with c1:
    sel_h = st.selectbox("Highlights portfolio", list(dfs.keys()))
    dfh = dfs[sel_h]
    if not dfh.empty:
        highlights = portfolio_highlights(dfh)
        st.write("Top 3 Max Capital:")
        for t in highlights["max_capital"]:
            st.write("🔹", t)
        st.write("Top 3 Profit:")
        for t in highlights["max_profit"]:
            st.write("🟩", t)
        st.write("Top 3 Loss:")
        for t in highlights["max_loss"]:
            st.write("🟥", t)
    else:
        st.warning("No data.")

with c2:
    sel_hold = st.selectbox("Holdings portfolio", list(dfs.keys()))
    dff = dfs[sel_hold]
    if not dff.empty:
        st.dataframe(dff, use_container_width=True)
        st.download_button(
            f"Download {sel_hold} CSV",
            data=dff.to_csv(index=False).encode("utf-8"),
            file_name=f"{sel_hold}_holdings.csv",
            mime="text/csv"
        )
    else:
        st.warning("No data.")
