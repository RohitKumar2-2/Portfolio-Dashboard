import streamlit as st

def compute_common_unique(dfs):
    """
    Returns (common_list, unique_per_portfolio_html)
    Expects each df to contain: instrument, pnl_pct(optional)
    """
    names = list(dfs.keys())
    sets = {n: set(dfs[n]["instrument"].dropna().unique()) for n in names}

    if not sets:
        return [], {n: [] for n in names}

    common = set.intersection(*sets.values()) if len(sets) > 1 else next(iter(sets.values()))

    unique_per = {}
    for n in names:
        others = set().union(*(sets[o] for o in names if o != n))
        uniques = sorted(list(sets[n] - others))
        df = dfs[n]
        chips = []
        for sym in uniques:
            row = df[df["instrument"] == sym]
            if not row.empty:
                pct = row.iloc[0].get("pnl_pct", 0)
                color = "green" if pct > 0 else "red"
                chips.append(
                    f"<span style='margin:3px;padding:4px 8px;border-radius:6px;"
                    f"background:#f1f3f6;color:{color};font-weight:600;font-size:12px'>"
                    f"{sym} ({pct:.2f}%)</span>"
                )
            else:
                chips.append(f"<span>{sym}</span>")
        unique_per[n] = chips
    return sorted(list(common)), unique_per
