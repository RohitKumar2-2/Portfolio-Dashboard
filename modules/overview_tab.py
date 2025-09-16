
import streamlit as st
from utils.highlights import portfolio_highlights

def render_overview_tab(dfs):
    st.subheader("⭐ Overview: Highlights & Holdings")
    if not dfs:
        st.warning("No data.")
        return
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
