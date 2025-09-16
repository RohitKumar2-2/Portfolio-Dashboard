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
from kiteconnect import KiteConnect  # only needed if you add optional debug (else you can remove)

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

# ---------- New Dynamic Alert Rules UI & Mapping Layer ----------

# ---------- Dynamic Alert Rules (replacing previous version) ----------
def _init_alert_rules():
    if "alert_rules" not in st.session_state:
        # Start with NO predefined rules
        st.session_state.alert_rules = []
    if "next_rule_id" not in st.session_state:
        st.session_state.next_rule_id = 1
    if "show_alert_rules_dialog" not in st.session_state:
        st.session_state.show_alert_rules_dialog = False
    if "editing_rule_id" not in st.session_state:
        st.session_state.editing_rule_id = None

_init_alert_rules()

PL_COMP_OPTS = ["Greater Than","Less Than","Range"]

def _alerts_css():
    if "alerts_css_done" in st.session_state:
        return
    st.markdown("""
    <style>
    div[data-testid="stDialog"] > div {
        width: 1050px !important;
        max-width: 1050px !important;
    }
    div[data-testid="stDialog"] section {
        max-height: 68vh !important;
        overflow-y: auto !important;
    }
    .rule-row {padding:4px 6px;border-radius:4px;margin-bottom:4px;background:#fafafa;}
    .rule-row:hover {background:#f0f2f6;}
    .icon-btn button {padding:2px 6px !important; font-size:0.7rem !important; line-height:1 !important;}
    </style>
    """, unsafe_allow_html=True)
    st.session_state.alerts_css_done = True

_alerts_css()

def open_alert_rules_dialog():
    st.session_state.show_alert_rules_dialog = True
    st.session_state.editing_rule_id = None

def _close_alert_rules_dialog():
    st.session_state.show_alert_rules_dialog = False
    st.session_state.editing_rule_id = None

def _start_edit_rule(rid:int):
    st.session_state.editing_rule_id = rid

def _add_rule():
    rid = st.session_state.next_rule_id
    st.session_state.alert_rules.append({
        "id": rid, "name": f"Alert {rid}",
        "applied_to": [], "uni_common":"Unique","common_in":[],
        "profit_loss":"Loss","pl_comp":"Greater Than","pl_from":5.0,"pl_to":0.0,
        "inv_comp":"Greater Than","inv_from":0.0,"inv_to":0.0,
        "message":"New rule"
    })
    st.session_state.next_rule_id += 1
    st.session_state.editing_rule_id = rid

def _reset_rules():
    """Delete all alert rules and reset counters."""
    st.session_state.alert_rules = []
    st.session_state.next_rule_id = 1
    st.session_state.editing_rule_id = None

def _delete_rule(rid:int):
    st.session_state.alert_rules = [r for r in st.session_state.alert_rules if r["id"]!=rid]
    if st.session_state.editing_rule_id == rid:
        st.session_state.editing_rule_id = None

def _save_rule(rid:int):
    for r in st.session_state.alert_rules:
        if r["id"] == rid:
            r["name"] = st.session_state.get(f"rule_name_{rid}", r["name"])
            r["applied_to"] = st.session_state.get(f"rule_applied_{rid}", [])
            r["uni_common"] = st.session_state.get(f"rule_uni_common_{rid}", r["uni_common"])
            r["common_in"] = st.session_state.get(f"rule_common_in_{rid}", [])
            r["profit_loss"] = st.session_state.get(f"rule_profit_loss_{rid}", r["profit_loss"])
            r["pl_comp"] = st.session_state.get(f"rule_pl_comp_{rid}", r["pl_comp"])
            r["pl_from"] = st.session_state.get(f"rule_pl_from_{rid}", r["pl_from"])
            r["pl_to"] = st.session_state.get(f"rule_pl_to_{rid}", r["pl_to"])
            r["inv_comp"] = st.session_state.get(f"rule_inv_comp_{rid}", r["inv_comp"])
            r["inv_from"] = st.session_state.get(f"rule_inv_from_{rid}", r["inv_from"])
            r["inv_to"] = st.session_state.get(f"rule_inv_to_{rid}", r["inv_to"])
            r["message"] = st.session_state.get(f"rule_message_{rid}", r["message"])
            break
    st.session_state.editing_rule_id = None
    # Flag for toast outside callback
    st.session_state.show_saved_toast = True

def _rule_edit_form(rule:dict, portfolios:list):
    rid = rule["id"]
    st.text_input("Alert Name", value=rule["name"], key=f"rule_name_{rid}")
    st.markdown("**1. Applied To**")
    all_ports = st.checkbox("All Portfolios", key=f"rule_all_{rid}", value=(not rule["applied_to"]))
    if all_ports:
        st.session_state[f"rule_applied_{rid}"] = []
        applied_display = portfolios
    else:
        st.multiselect("Select Portfolios", portfolios,
                       default=rule["applied_to"], key=f"rule_applied_{rid}")
        applied_display = st.session_state.get(f"rule_applied_{rid}", [])
    st.markdown("**2. Unique / Common**")
    st.radio("Scope", ["Unique","Common"], key=f"rule_uni_common_{rid}",
             index=0 if rule["uni_common"]=="Unique" else 1, horizontal=True)
    if st.session_state.get(f"rule_uni_common_{rid}") == "Common":
        subset = applied_display if applied_display else portfolios
        st.multiselect("Common Across (subset)", subset,
                       default=rule["common_in"] if rule["common_in"] else subset,
                       key=f"rule_common_in_{rid}")
    st.markdown("**3. Profit / Loss Percentage**")
    st.radio("Direction", ["Profit","Loss","Unchanged"], horizontal=True,
             key=f"rule_profit_loss_{rid}",
             index=["Profit","Loss","Unchanged"].index(rule["profit_loss"]))
    direction = st.session_state.get(f"rule_profit_loss_{rid}")
    if direction != "Unchanged":
        st.selectbox("Comparator", PL_COMP_OPTS,
                     index=PL_COMP_OPTS.index(rule["pl_comp"]), key=f"rule_pl_comp_{rid}")
        comp = st.session_state.get(f"rule_pl_comp_{rid}")
        if comp == "Range":
            c1,c2 = st.columns(2)
            with c1:
                st.number_input("From (%)", value=rule["pl_from"], step=0.5, key=f"rule_pl_from_{rid}")
            with c2:
                st.number_input("To (%)", value=rule["pl_to"], step=0.5, key=f"rule_pl_to_{rid}")
        else:
            st.number_input("Value (%)", value=rule["pl_from"], step=0.5, key=f"rule_pl_from_{rid}")
    st.markdown("**4. Investment**")
    st.selectbox("Investment Comparator", PL_COMP_OPTS,
                 index=PL_COMP_OPTS.index(rule["inv_comp"]), key=f"rule_inv_comp_{rid}")
    inv_comp = st.session_state.get(f"rule_inv_comp_{rid}")
    if inv_comp == "Range":
        c3,c4 = st.columns(2)
        with c3:
            st.number_input("Investment From (₹)", value=float(rule["inv_from"]), step=5000.0,
                            key=f"rule_inv_from_{rid}")
        with c4:
            st.number_input("Investment To (₹)", value=float(rule["inv_to"]), step=5000.0,
                            key=f"rule_inv_to_{rid}")
    else:
        st.number_input("Investment Value (₹)", value=float(rule["inv_from"]), step=5000.0,
                        key=f"rule_inv_from_{rid}")
    st.markdown("**5. Alert Message**")
    st.text_area("Message", value=rule["message"], key=f"rule_message_{rid}", height=70)
    cbtn = st.columns([0.5,0.25,0.25])
    with cbtn[1]:
        st.button("Save", key=f"save_rule_{rid}", on_click=_save_rule, args=(rid,))
    with cbtn[2]:
        st.button("Cancel", key=f"cancel_rule_{rid}",
                  on_click=lambda: st.session_state.update(editing_rule_id=None))

def _alert_rules_dialog_body(portfolios):
    portfolios = portfolios or []
    if st.session_state.editing_rule_id:
        rule = next((x for x in st.session_state.alert_rules
                     if x["id"] == st.session_state.editing_rule_id), None)
        st.markdown(f"### Edit Rule (ID {st.session_state.editing_rule_id})")
        st.button("← Back to List", on_click=lambda: st.session_state.update(editing_rule_id=None),
                  type="secondary")
        st.divider()
        if rule:
            _rule_edit_form(rule, portfolios)
        else:
            st.warning("Rule not found.")
    else:
        st.markdown("### Alerts List")
        # Only Reset + Close here (Add moved to main Alerts tab)
        col_reset, col_close = st.columns([0.5,0.5])
        with col_reset:
            st.button("Reset (Delete All)", on_click=_reset_rules, use_container_width=True, type="secondary")
        with col_close:
            st.button("Close", on_click=_close_alert_rules_dialog, use_container_width=True)
        st.divider()
        for r in sorted(st.session_state.alert_rules, key=lambda x: x["id"]):
            cols = st.columns([0.7,0.15,0.15])
            with cols[0]:
                st.write(r["name"])
            with cols[1]:
                st.button("✏️", key=f"edit_{r['id']}",
                          on_click=_start_edit_rule, args=(r["id"],))
            with cols[2]:
                st.button("🗑️", key=f"del_{r['id']}",
                          on_click=_delete_rule, args=(r["id"],))

def refresh_portfolios():
    for k in list(st.session_state.keys()):
        if k.startswith("portfolio_"):
            del st.session_state[k]

# Refresh
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

# ------------------------------------------------------------------
# TABS
# ------------------------------------------------------------------
tab_compare, tab_alerts, tab_overview = st.tabs(["Compare", "Alerts", "Overview"])

# ===================== COMPARE TAB =====================
with tab_compare:
    # ---- Unified Stocks Table (Comparison) ----
    if valid_dfs:
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

        # Force 2 decimals
        pct_cols_all = [c for c in table_df.columns if c.endswith("% Up/Down")]
        for c in pct_cols_all:
            table_df[c] = pd.to_numeric(table_df[c], errors="coerce").round(2)

        st.subheader("📌 Stocks Across Portfolios")

        # Session state key specific to compare tab
        if "compare_portfolio_filter" not in st.session_state:
            st.session_state["compare_portfolio_filter"] = []

        def clear_compare_filters():
            st.session_state["compare_portfolio_filter"] = []

        col_select, col_clear = st.columns([0.9, 0.1])
        with col_select:
            st.multiselect(
                "Filter with Portfolios",
                options=list(valid_dfs.keys()),
                key="compare_portfolio_filter"
            )
        with col_clear:
            st.write("")
            st.button("Clear All", on_click=clear_compare_filters, use_container_width=True)

        selected_ports = st.session_state["compare_portfolio_filter"]
        disp = table_df.copy()

        if selected_ports:
            disp = disp[disp["Portfolios"].apply(lambda lst: all(p in lst for p in selected_ports))].copy()
            sel_pct_cols = [f"{p} % Up/Down" for p in selected_ports]
            if sel_pct_cols:
                disp["Avg % Up/Down"] = disp[sel_pct_cols].mean(axis=1).round(2)
            keep_cols = ["Stock", "Portfolios", "Avg % Up/Down"] + sel_pct_cols
            disp = disp[keep_cols]
        else:
            pct_cols_all = [c for c in disp.columns if c.endswith("% Up/Down")]
            disp[pct_cols_all] = disp[pct_cols_all].replace(0, pd.NA)

        disp["Portfolios"] = disp["Portfolios"].apply(lambda x: ", ".join(x))

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

        # (Optional) show unique/common chips if you want inside Compare tab
        with st.expander("Common & Unique Summary", expanded=False):
            st.markdown(f"**Common Symbols ({len(common_list)})**: {', '.join(common_list) if common_list else 'None'}")
            for pname in valid_dfs.keys():
                st.markdown(f"**Unique to {pname}**:")
                st.markdown(" ".join(unique_per.get(pname, [])) or "_None_")
    else:
        st.warning("No valid portfolio data to compare.")

# ===================== ALERTS TAB =====================
with tab_alerts:
    st.subheader("🚨 Alerts & Opportunities")

    # Top action buttons row
    btn_cols = st.columns([0.15, 0.15, 0.70])
    with btn_cols[0]:
        add_clicked = st.button("➕ Add Rule", key="add_rule_main")
        if add_clicked:
            # Create new rule THEN just set the dialog flag (do NOT clear editing_rule_id)
            _add_rule()  # sets editing_rule_id to new rule
            st.session_state.show_alert_rules_dialog = True

    with btn_cols[1]:
        if st.session_state.alert_rules:
            if st.button("⚙️ Settings", key="open_alert_rules"):
                open_alert_rules_dialog()

    # If no rules, show only Add Rule and exit
    if not st.session_state.alert_rules:
        st.info("No alert rules configured. Use 'Add Rule' to create one.")
    else:
        if valid_dfs:
            alerts_df = generate_alerts(valid_dfs, st.session_state.alert_rules)
            if alerts_df.empty:
                st.info("No alerts triggered for current rules.")
            else:
                view_mode = st.radio("View Mode", ["By Portfolio", "By Rule"], horizontal=True)
                if view_mode == "By Portfolio":
                    port = st.selectbox("Select Portfolio", sorted(alerts_df["portfolio"].unique()))
                    to_show = alerts_df[alerts_df["portfolio"] == port]
                else:
                    rule = st.selectbox("Select Rule", sorted(alerts_df["rule"].unique()))
                    to_show = alerts_df[alerts_df["rule"] == rule]

                if to_show.empty:
                    st.warning("No matches for this selection.")
                else:
                    for _, r in to_show.iterrows():
                        st.markdown(
                            f"<div style='background:#f5f5f5;padding:8px;border-radius:6px;margin-bottom:6px'>"
                            f"<b>{r['instrument']}</b> "
                            f"<span style='font-size:0.8rem;color:#555'>(Portfolio: {r['portfolio']} | Rule: {r['rule']})</span><br>"
                            f"<small>{r['message']}</small>"
                            f"</div>",
                            unsafe_allow_html=True
                        )
        else:
            st.warning("No portfolios loaded to generate alerts.")

# ===================== OVERVIEW TAB =====================
with tab_overview:
    st.subheader("⭐ Overview: Highlights & Holdings")
    if not dfs:
        st.warning("No data.")
    else:
        c1, c2 = st.columns(2)

        with c1:
            sel_h = st.selectbox("Highlights portfolio", list(dfs.keys()), key="highlights_select")
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
            sel_hold = st.selectbox("Holdings portfolio", list(dfs.keys()), key="holdings_select")
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

if st.session_state.get("show_alert_rules_dialog"):
    _ports = list(valid_dfs.keys())
    if hasattr(st, "dialog"):
        @st.dialog("Set Alert Rules")
        def _alerts_dialog():
            _alert_rules_dialog_body(_ports)
        _alerts_dialog()
    else:
        with st.expander("Set Alert Rules", expanded=True):
            _alert_rules_dialog_body(_ports)

# PATCH: Remove UI rendering (st.toast) from callbacks to eliminate fragment rerun warning.
# 1. Modify _save_rule to NOT call st.toast directly.
def _save_rule(rid:int):
    for r in st.session_state.alert_rules:
        if r["id"] == rid:
            r["name"] = st.session_state.get(f"rule_name_{rid}", r["name"])
            r["applied_to"] = st.session_state.get(f"rule_applied_{rid}", [])
            r["uni_common"] = st.session_state.get(f"rule_uni_common_{rid}", r["uni_common"])
            r["common_in"] = st.session_state.get(f"rule_common_in_{rid}", [])
            r["profit_loss"] = st.session_state.get(f"rule_profit_loss_{rid}", r["profit_loss"])
            r["pl_comp"] = st.session_state.get(f"rule_pl_comp_{rid}", r["pl_comp"])
            r["pl_from"] = st.session_state.get(f"rule_pl_from_{rid}", r["pl_from"])
            r["pl_to"] = st.session_state.get(f"rule_pl_to_{rid}", r["pl_to"])
            r["inv_comp"] = st.session_state.get(f"rule_inv_comp_{rid}", r["inv_comp"])
            r["inv_from"] = st.session_state.get(f"rule_inv_from_{rid}", r["inv_from"])
            r["inv_to"] = st.session_state.get(f"rule_inv_to_{rid}", r["inv_to"])
            r["message"] = st.session_state.get(f"rule_message_{rid}", r["message"])
            break
    st.session_state.editing_rule_id = None
    # Flag for toast outside callback
    st.session_state.show_saved_toast = True

# 2. After your main layout begins (anywhere AFTER st.set_page_config and BEFORE tabs render),
#    add this small block ONCE (make sure it isn’t duplicated):
if st.session_state.get("show_saved_toast"):
    st.toast("Rule saved")
    st.session_state.show_saved_toast = False
