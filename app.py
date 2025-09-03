"""
Streamlit Portfolio Comparison Dashboard
Reads any number of CSV portfolio files and produces:
- Common and unique stocks (back in!)
- Alerts (red/green) per rules described by the user
- Key highlights: max capital in one stock, top 3 losses
- Interactive, polished UI with rich visuals

Usage:
    streamlit run streamlit_portfolio_dashboard.py
"""

import streamlit as st
import pandas as pd
import numpy as np
import io
import plotly.express as px
import plotly.graph_objects as go
from typing import List, Dict, Tuple

st.set_page_config(page_title="Portfolio Comparator", layout="wide", page_icon="📊")

# ------------------ Helpers ------------------

def normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Normalize column names and coerce types; fill any missing core columns.
    Accepts common name variations.
    """
    col_map = {}
    lower = {c.lower().strip(): c for c in df.columns}
    mapping = {
        'instrument': ['instrument', 'symbol', 'name'],
        'qty': ['qty', 'quantity', 'no. of shares', 'quantity.'],
        'avg_cost': ['avg. cost', 'avg cost', 'avg_cost', 'avgprice', 'avg price'],
        'ltp': ['ltp', 'last', 'last price', 'last traded price'],
        'invested': ['invested', 'invested amount', 'invested.', 'investment', 'buy value'],
        'cur_val': ['cur. val', 'cur val', 'current value', 'market value', 'curvalue', 'current'],
        'pl': ['p&l', 'pnl', 'p/l', 'pl', 'profit/loss'],
        'net_chg': ['net chg.', 'net chg', 'net change', 'net_chg'],
        'day_chg': ['day chg.', 'day chg', 'day change', 'day_chg']
    }
    for target, candidates in mapping.items():
        for cand in candidates:
            if cand in lower:
                col_map[lower[cand]] = target
                break
    df = df.rename(columns=col_map)
    if 'instrument' not in df.columns:
        df = df.rename(columns={df.columns[0]: 'instrument'})
    # ensure columns exist
    for col in ['qty','avg_cost','ltp','invested','cur_val','pl','net_chg','day_chg']:
        if col not in df.columns:
            df[col] = 0
    # coerce numerics
    for num_col in ['qty','avg_cost','ltp','invested','cur_val','pl','net_chg','day_chg']:
        df[num_col] = (df[num_col]
                       .astype(str)
                       .str.replace(',', '')
                       .str.replace('\u2013', '-')
                       .str.replace('₹', '')
                       .str.replace('%', '')
                       )
        df[num_col] = pd.to_numeric(df[num_col], errors='coerce').fillna(0)
    df['instrument'] = df['instrument'].astype(str).str.strip()
    return df


def aggregate_portfolios(dfs: Dict[str,pd.DataFrame]) -> pd.DataFrame:
    """Aggregate across portfolios by instrument."""
    rows = []
    for name, df in dfs.items():
        tmp = df.copy()
        tmp['portfolio'] = name
        cols = ['instrument','qty','avg_cost','ltp','invested','cur_val','pl','portfolio']
        for c in cols:
            if c not in tmp.columns:
                tmp[c] = 0
        rows.append(tmp[cols])
    big = pd.concat(rows, ignore_index=True)
    agg = big.groupby('instrument', as_index=False).agg(
        total_qty=('qty','sum'),
        avg_cost=('avg_cost', lambda x: np.nan if x.dropna().empty else np.average(x.dropna())),
        ltp=('ltp', lambda x: x.dropna().iloc[0] if not x.dropna().empty else np.nan),
        total_invested=('invested','sum'),
        total_cur_val=('cur_val','sum'),
        total_pl=('pl','sum'),
        portfolios_present=('portfolio', lambda x: sorted(set(x)))
    )
    agg['pl_pct'] = (agg['total_pl'] / agg['total_invested'] * 100).replace([np.inf, -np.inf], np.nan).fillna(0)
    return agg


def compute_common_unique(dfs: Dict[str, pd.DataFrame]) -> Tuple[List[str], Dict[str, List[str]]]:
    """Return (common across ALL portfolios, unique per portfolio)."""
    names = list(dfs.keys())
    sets = {n: set(dfs[n]['instrument'].dropna().unique()) for n in names}
    if not sets:
        return [], {n: [] for n in names}
    if len(sets) == 1:
        common = next(iter(sets.values()))
    else:
        common = set.intersection(*sets.values())
    unique_per = {}
    for n in names:
        others = set().union(*(sets[m] for m in names if m != n))
        unique_per[n] = sorted(list(sets[n] - others))
    return sorted(list(common)), unique_per


def rupees(x: float) -> str:
    try:
        return f"₹{x:,.2f}"
    except Exception:
        return f"₹{x}"


def generate_alerts(
    dfs: Dict[str, pd.DataFrame],
    agg: pd.DataFrame,
    common_list: List[str],
    unique_per: Dict[str, List[str]],
    *,
    uniq_loss_thresh: float = 5.0,
    common_small_loss: float = 5.0,
    common_large_loss: float = 7.0,
    small_amt: float = 100000.0,
    large_amt: float = 150000.0,
    profit_small_pct: float = 10.0,
    profit_large_pct: float = 6.0,
    profit_large_amt: float = 100000.0,
) -> pd.DataFrame:
    """Build alerts per the rules; return as DataFrame."""
    alerts = []
    # Unique stock opportunity (down more than 5%)
    for port, uniques in unique_per.items():
        df = dfs[port]
        for ins in uniques:
            r = df[df['instrument'] == ins]
            if r.empty:
                continue
            invested = float(r['invested'].sum())
            pl = float(r['pl'].sum())
            pl_pct = (pl / invested * 100) if invested else 0
            if pl_pct < -uniq_loss_thresh:
                alerts.append({
                    'category': 'Red',
                    'type': 'Opportunity (Unique - down >5%)',
                    'instrument': ins,
                    'message': f"Opportunity: Add {ins} to other portfolios. It's down {round(-pl_pct,2)}% with {rupees(invested)} invested.",
                    'portfolio': port,
                    'invested': invested,
                    'pl_pct': pl_pct,
                    'rule': f"unique & loss>{uniq_loss_thresh}%"
                })
    # Common stocks average out rules
    common_set = set(common_list)
    for ins in common_set:
        row = agg[agg['instrument'] == ins]
        if row.empty:
            continue
        invested = float(row['total_invested'].iloc[0])
        pl = float(row['total_pl'].iloc[0])
        loss_pct = (pl / invested * 100) if invested else 0
        if loss_pct < -common_small_loss and invested < small_amt:
            alerts.append({
                'category': 'Red',
                'type': 'Average Out (Small Invest)',
                'instrument': ins,
                'message': f"Average Out (small): {ins} is down {round(-loss_pct,2)}% with total invested {rupees(invested)} (< {rupees(small_amt)}).",
                'portfolio': 'ALL',
                'invested': invested,
                'pl_pct': loss_pct,
                'rule': f"common & loss>{common_small_loss}% & invested<{rupees(small_amt)}"
            })
        if loss_pct < -common_large_loss and invested > large_amt:
            alerts.append({
                'category': 'Red',
                'type': 'Average Out (Large Invest)',
                'instrument': ins,
                'message': f"Average Out (large): {ins} is down {round(-loss_pct,2)}% with total invested {rupees(invested)} (> {rupees(large_amt)}).",
                'portfolio': 'ALL',
                'invested': invested,
                'pl_pct': loss_pct,
                'rule': f"common & loss>{common_large_loss}% & invested>{rupees(large_amt)}"
            })
    # Book profit rules
    for _, r in agg.iterrows():
        ins = r['instrument']
        invested = float(r['total_invested'])
        pl_pct = float(r['pl_pct']) if not pd.isna(r['pl_pct']) else 0
        if pl_pct > profit_small_pct and invested < profit_large_amt:
            alerts.append({
                'category': 'Green',
                'type': 'Book Profit (Small)',
                'instrument': ins,
                'message': f"Book Profit: {ins} is up {round(pl_pct,2)}% with invested {rupees(invested)} (< {rupees(profit_large_amt)}).",
                'portfolio': 'ALL',
                'invested': invested,
                'pl_pct': pl_pct,
                'rule': f"profit>{profit_small_pct}% & invested<{rupees(profit_large_amt)}"
            })
        if pl_pct > profit_large_pct and invested > profit_large_amt:
            alerts.append({
                'category': 'Green',
                'type': 'Book Profit (Large)',
                'instrument': ins,
                'message': f"Book Profit: {ins} is up {round(pl_pct,2)}% with invested {rupees(invested)} (> {rupees(profit_large_amt)}).",
                'portfolio': 'ALL',
                'invested': invested,
                'pl_pct': pl_pct,
                'rule': f"profit>{profit_large_pct}% & invested>{rupees(profit_large_amt)}"
            })
    if not alerts:
        return pd.DataFrame(columns=['category','type','instrument','message','portfolio','invested','pl_pct','rule'])
    return pd.DataFrame(alerts).sort_values(['category','type','instrument']).reset_index(drop=True)


# ------------------ UI ------------------

st.title("📊 Portfolio Dashboard")

st.markdown("""
<style>
    .stApp { background-color: #f8f9fa; }
    h1, h2, h3, h4 { color: #2c3e50; }
    .alert-card { padding: 12px 14px; border-radius: 10px; margin-bottom: 10px; font-size: 0.95rem; }
    .red-flag { background-color: #ffeaea; border-left: 6px solid #e74c3c; }
    .green-flag { background-color: #e9fff1; border-left: 6px solid #2ecc71; }
    .info-flag { background-color: #eaf2ff; border-left: 6px solid #3498db; }
    .chip { display:inline-block; padding:4px 10px; border-radius:999px; margin:2px; background:#eef2f7; }
</style>
""", unsafe_allow_html=True)



# Sidebar controls for interactivity
with st.sidebar:
    st.header("⚙️ Alert Rules")
    uniq_loss_thresh = st.number_input("Unique loss threshold (%)", value=5.0, min_value=0.0, step=0.5)
    small_amt = st.number_input("Small invest max (₹)", value=100000.0, step=5000.0)
    large_amt = st.number_input("Large invest min (₹)", value=150000.0, step=5000.0)
    common_small_loss = st.number_input("Common small loss (%)", value=5.0, min_value=0.0, step=0.5)
    common_large_loss = st.number_input("Common large loss (%)", value=7.0, min_value=0.0, step=0.5)
    profit_small_pct = st.number_input("Profit small (%)", value=10.0, min_value=0.0, step=0.5)
    profit_large_pct = st.number_input("Profit large (%)", value=6.0, min_value=0.0, step=0.5)

uploaded = st.file_uploader("Upload CSV files", type=['csv','txt'], accept_multiple_files=True)

if uploaded:
    dfs = {}
    for f in uploaded:
        try:
            content = f.read()
            df = pd.read_csv(io.BytesIO(content))
            df = normalize_columns(df)
            dfs[f.name] = df
        except Exception as e:
            st.error(f"❌ Failed to parse {f.name}: {str(e)}")

    if len(dfs)==0:
        st.error("No valid CSVs uploaded.")
    else:
        st.success(f"✅ {len(dfs)} portfolios loaded successfully!")

        # Comparisons: Common & Unique
        common_list, unique_per = compute_common_unique(dfs)
        with st.expander("🔀 Comparisons — Common & Unique Stocks", expanded=True):
            c1, c2 = st.columns([1,1])
            with c1:
                st.markdown(f"**Common Stocks across all portfolios ({len(common_list)})**")
                st.write(common_list if common_list else "—")
            with c2:
                st.markdown("**Unique Stocks per Portfolio**")
                for name, uniqs in unique_per.items():
                    st.write(f"**{name}** ({len(uniqs)})")
                    if uniqs:
                        st.markdown(' '.join([f"<span class='chip'>{u}</span>" for u in uniqs[:50]]), unsafe_allow_html=True)
                        if len(uniqs) > 50:
                            st.caption(f"(+{len(uniqs)-50} more)")
                    else:
                        st.caption("None")

        # Aggregate for further logic
        agg = aggregate_portfolios(dfs)

        # Alerts Section (with filters)
        st.subheader("🚨 Alerts & Opportunities")
        alerts_df = generate_alerts(
            dfs, agg, common_list, unique_per,
            uniq_loss_thresh=uniq_loss_thresh,
            common_small_loss=common_small_loss,
            common_large_loss=common_large_loss,
            small_amt=small_amt,
            large_amt=large_amt,
            profit_small_pct=profit_small_pct,
            profit_large_pct=profit_large_pct,
        )

        if not alerts_df.empty:
            search = st.text_input("Filter alerts by stock / text")
            cat = st.multiselect("Category", options=sorted(alerts_df['category'].unique()), default=list(sorted(alerts_df['category'].unique())))
            typ = st.multiselect("Type", options=sorted(alerts_df['type'].unique()), default=list(sorted(alerts_df['type'].unique())))
            view = alerts_df.copy()
            if search:
                s = search.lower()
                view = view[view.apply(lambda r: s in str(r.to_dict()).lower(), axis=1)]
            if cat:
                view = view[view['category'].isin(cat)]
            if typ:
                view = view[view['type'].isin(typ)]

            # Render nice cards
            for _, r in view.iterrows():
                css_class = 'green-flag' if r['category'] == 'Green' else 'red-flag'
                st.markdown(
                    f"""
                    <div class='alert-card {css_class}'>
                        <b>{r['instrument']}</b> — {r['message']}<br>
                        <small><i>Rule:</i> {r['rule']} | <i>Portfolio:</i> {r['portfolio']}</small>
                    </div>
                    """,
                    unsafe_allow_html=True
                )

            st.download_button(
                "Download alerts CSV",
                data=view.to_csv(index=False).encode('utf-8'),
                file_name='alerts.csv'
            )
        else:
            st.markdown('<div class="alert-card info-flag">No alerts triggered based on the rules.</div>', unsafe_allow_html=True)

        # Highlights
        with st.expander("⭐ Key Highlights", expanded=True):
            if not agg.empty:
                max_row = agg.loc[agg['total_invested'].idxmax()]
                st.markdown(f"**Max Capital in One Stock:** {max_row['instrument']} — {rupees(max_row['total_invested'])}")
                losses = agg.sort_values('pl_pct').head(3)
                st.markdown("**Top 3 Stocks with Biggest Losses (by %)**")
                for _, r in losses.iterrows():
                    st.write(f"{r['instrument']}: {r['pl_pct']:.2f}% (Invested {rupees(r['total_invested'])})")

        # Visualizations
        st.subheader("📊 Visualizations")
        tab1, tab2, tab3, tab4 = st.tabs(["Investment Distribution", "P&L % vs Invested", "Treemap", "Overlap Matrix"])

        with tab1:
            top20 = agg.sort_values('total_invested', ascending=False).head(20)
            fig = px.bar(top20, x='instrument', y='total_invested', color='total_pl',
                         title='Top 20 by Invested Amount', text_auto=True,
                         color_continuous_scale='RdYlGn')
            st.plotly_chart(fig, use_container_width=True)

        with tab2:
            bubble = px.scatter(
                agg, x='total_invested', y='pl_pct', size='total_qty', color='pl_pct',
                hover_data=['instrument','total_pl','total_cur_val'],
                labels={'total_invested':'Invested (₹)', 'pl_pct':'P&L %'},
                title='Risk/Reward — P&L% vs Invested (bubble=size of qty)',
                color_continuous_scale='RdYlGn'
            )
            st.plotly_chart(bubble, use_container_width=True)

        with tab3:
            treemap = px.treemap(
                agg.sort_values('total_invested', ascending=False).head(50),
                path=[px.Constant('All'), 'instrument'], values='total_invested',
                color='pl_pct', color_continuous_scale='RdYlGn',
                title='Treemap — Size by Invested, Color by P&L%'
            )
            st.plotly_chart(treemap, use_container_width=True)

        with tab4:
            # Presence matrix (instrument x portfolio)
            names = list(dfs.keys())
            presence_rows = []
            for ins in agg['instrument']:
                row = {'instrument': ins}
                for n in names:
                    row[n] = 1 if ins in set(dfs[n]['instrument']) else 0
                presence_rows.append(row)
            presence = pd.DataFrame(presence_rows)
            # limit to top 30 by invested for readability
            top30 = agg[['instrument','total_invested']].sort_values('total_invested', ascending=False).head(30)
            mat = presence.merge(top30, on='instrument', how='inner').drop(columns=['total_invested'])
            heat = go.Figure(data=go.Heatmap(
                z=mat[names].values,
                x=names,
                y=mat['instrument'],
                colorscale=[[0, '#f1f2f6'], [1, '#2e86de']],
                showscale=False
            ))
            heat.update_layout(title="Overlap Matrix — 1 means present in portfolio", xaxis_nticks=len(names))
            st.plotly_chart(heat, use_container_width=True)

        # Drilldown
        with st.expander("🔎 Per-Portfolio Drilldown"):
            sel = st.selectbox("Select portfolio", options=list(dfs.keys()))
            st.dataframe(dfs[sel])

else:
    st.info("Upload one or more CSV portfolio files to get started.")

st.markdown("---")

