
import streamlit as st
import pandas as pd

def render_compare_tab(valid_dfs, common_list, unique_per):
    if not valid_dfs:
        st.warning("No valid portfolio data to compare.")
        return

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

    pct_cols_all = [c for c in table_df.columns if c.endswith("% Up/Down")]
    for c in pct_cols_all:
        table_df[c] = pd.to_numeric(table_df[c], errors="coerce").round(2)

    st.subheader("📌 Stocks Across Portfolios")

    if "compare_portfolio_filter" not in st.session_state:
        st.session_state.compare_portfolio_filter = []

    def clear_compare_filters():
        st.session_state.compare_portfolio_filter = []

    col_select, col_clear = st.columns([0.9,0.1])
    with col_select:
        st.multiselect("Filter with Portfolios",
                       options=list(valid_dfs.keys()),
                       key="compare_portfolio_filter")
    with col_clear:
        st.write("")
        st.button("Clear All", on_click=clear_compare_filters, use_container_width=True)

    selected_ports = st.session_state.compare_portfolio_filter
    disp = table_df.copy()

    if selected_ports:
        disp = disp[disp["Portfolios"].apply(lambda lst: all(p in lst for p in selected_ports))].copy()
        sel_pct_cols = [f"{p} % Up/Down" for p in selected_ports]
        if sel_pct_cols:
            disp["Avg % Up/Down"] = disp[sel_pct_cols].mean(axis=1).round(2)
        keep_cols = ["Stock", "Portfolios", "Avg % Up/Down"] + sel_pct_cols
        disp = disp[keep_cols]
    else:
        disp[pct_cols_all] = disp[pct_cols_all].replace(0, pd.NA)

    disp["Portfolios"] = disp["Portfolios"].apply(lambda x: ", ".join(x))

    def color_pct(val):
        if pd.isna(val):
            return "color:#888;"
        try:
            v = float(val)
        except Exception:
            return ""
        if v > 0: return "color:green;font-weight:600;"
        if v < 0: return "color:red;font-weight:600;"
        return "color:#555;"

    pct_cols_for_style = [c for c in disp.columns if c.endswith("% Up/Down")]
    styled = (disp.style
              .applymap(color_pct, subset=pct_cols_for_style)
              .format(subset=pct_cols_for_style,
                      formatter=lambda v: "NA" if pd.isna(v) else f"{float(v):.2f}"))
    st.dataframe(styled, use_container_width=True)

    with st.expander("Common & Unique Summary", expanded=False):
        st.markdown(f"**Common Symbols ({len(common_list)})**: "
                    f"{', '.join(common_list) if common_list else 'None'}")
        for pname in valid_dfs.keys():
            st.markdown(f"**Unique to {pname}**:")
            uniques = unique_per.get(pname, [])
            st.markdown(" ".join(uniques) or "_None_")
