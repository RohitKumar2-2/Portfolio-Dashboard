import pandas as pd
from typing import Dict, List

# New rule-driven alert engine.
# valid_dfs: { portfolio_name: DataFrame(instrument, pnl_pct, invested, ...) }
# alert_rules: list of dicts (stored in st.session_state.alert_rules)
#
# Rule fields used:
#  name, applied_to(list), uni_common("Unique"/"Common"), common_in(list),
#  profit_loss("Profit"/"Loss"/"Unchanged"), pl_comp("Greater Than"/"Less Than"/"Range"),
#  pl_from(float), pl_to(float), inv_comp(...), inv_from(float), inv_to(float), message(str)

def generate_alerts(valid_dfs: Dict[str, pd.DataFrame], alert_rules: List[dict]) -> pd.DataFrame:
    if not valid_dfs or not alert_rules:
        return pd.DataFrame(columns=["instrument","portfolio","rule","message","category"])
    # Precompute instrument sets
    inst_sets = {p: set(df["instrument"].dropna().unique()) for p, df in valid_dfs.items()}
    all_ports = list(valid_dfs.keys())

    records = []

    for rule in alert_rules:
        applied = rule.get("applied_to") or all_ports  # empty => all
        applied = [p for p in applied if p in valid_dfs]  # safety
        if not applied:
            continue

        scope = rule.get("uni_common","Unique")
        profit_loss = rule.get("profit_loss","Loss")
        pl_comp = rule.get("pl_comp","Greater Than")
        pl_from = float(rule.get("pl_from",0) or 0)
        pl_to = float(rule.get("pl_to",pl_from))
        inv_comp = rule.get("inv_comp","Greater Than")
        inv_from = float(rule.get("inv_from",0) or 0)
        inv_to = float(rule.get("inv_to",inv_from))
        message = rule.get("message", rule.get("name","Alert"))
        rule_name = rule.get("name","Alert")

        # Determine candidate symbols per portfolio based on Unique/Common
        if scope == "Common":
            subset = rule.get("common_in") or applied
            subset = [p for p in subset if p in applied]
            if not subset:
                subset = applied
            common_syms = set.intersection(*[inst_sets[p] for p in subset]) if subset else set()
            # We'll alert once per portfolio in 'subset' for each symbol (so user sees portfolio context)
            for p in subset:
                dfp = valid_dfs[p]
                part = dfp[dfp["instrument"].isin(common_syms)].copy()
                part = _apply_pl_filters(part, profit_loss, pl_comp, pl_from, pl_to)
                part = _apply_inv_filters(part, inv_comp, inv_from, inv_to)
                if part.empty:
                    continue
                cat = _derive_category(profit_loss)
                for _, r in part.iterrows():
                    records.append({
                        "instrument": r["instrument"],
                        "portfolio": p,
                        "rule": rule_name,
                        "message": message,
                        "category": cat
                    })
        else:  # Unique
            # Unique within 'applied'
            union_applied = {p: inst_sets[p] for p in applied}
            for p in applied:
                others = set().union(*[union_applied[o] for o in applied if o != p])
                unique_syms = inst_sets[p] - others
                if not unique_syms:
                    continue
                dfp = valid_dfs[p]
                part = dfp[dfp["instrument"].isin(unique_syms)].copy()
                part = _apply_pl_filters(part, profit_loss, pl_comp, pl_from, pl_to)
                part = _apply_inv_filters(part, inv_comp, inv_from, inv_to)
                if part.empty:
                    continue
                cat = _derive_category(profit_loss)
                for _, r in part.iterrows():
                    records.append({
                        "instrument": r["instrument"],
                        "portfolio": p,
                        "rule": rule_name,
                        "message": message,
                        "category": cat
                    })

    if not records:
        return pd.DataFrame(columns=["instrument","portfolio","rule","message","category"])
    out = pd.DataFrame(records).drop_duplicates()
    # Optional ordering
    cat_order = {"Red":0,"Yellow":1,"Green":2}
    out["__order"] = out["category"].map(cat_order).fillna(99)
    out = out.sort_values(["__order","portfolio","instrument"]).drop(columns="__order")
    return out


def _apply_pl_filters(df: pd.DataFrame, direction: str, comp: str, v_from: float, v_to: float) -> pd.DataFrame:
    if df.empty:
        return df
    if "pnl_pct" not in df.columns:
        return df.iloc[0:0]
    # Unchanged: near zero (abs <= 0.0001)
    if direction == "Unchanged":
        return df[ df["pnl_pct"].abs() <= 0.0001 ]

    sign_mask = df["pnl_pct"] > 0 if direction == "Profit" else df["pnl_pct"] < 0
    work = df[sign_mask].copy()
    if work.empty:
        return work

    # Comparator applied on value (profit) or abs(value) (loss) for intuitive thresholds
    if direction == "Loss":
        val = work["pnl_pct"].abs()
    else:
        val = work["pnl_pct"]

    if comp == "Greater Than":
        work = work[val >= v_from]
    elif comp == "Less Than":
        work = work[val <= v_from]
    elif comp == "Range":
        lo = min(v_from, v_to)
        hi = max(v_from, v_to)
        work = work[(val >= lo) & (val <= hi)]
    return work


def _apply_inv_filters(df: pd.DataFrame, comp: str, v_from: float, v_to: float) -> pd.DataFrame:
    if df.empty:
        return df
    if "invested" not in df.columns:
        return df.iloc[0:0]
    val = df["invested"]
    if comp == "Greater Than":
        return df[val >= v_from]
    elif comp == "Less Than":
        return df[val <= v_from]
    elif comp == "Range":
        lo = min(v_from, v_to)
        hi = max(v_from, v_to)
        return df[(val >= lo) & (val <= hi)]
    return df


def _derive_category(direction: str) -> str:
    if direction == "Profit":
        return "Green"
    if direction == "Loss":
        return "Red"
    return "Yellow"
