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
        return pd.DataFrame(columns=["instrument","portfolio","rule","message"])
    # Precompute instrument sets
    inst_sets = {p: set(df["instrument"].dropna().unique()) for p, df in valid_dfs.items()}
    all_ports = list(valid_dfs.keys())

    records = []

    for rule in alert_rules:
        # ---- Skip incomplete (new) rules ----
        dir_ok = rule.get("profit_loss") in {"Profit","Loss","Unchanged"}
        inv_ok = rule.get("inv_comp") in {"Greater Than","Less Than","Range"}
        if not dir_ok or not inv_ok:
            continue
        if rule.get("profit_loss") != "Unchanged":
            comp_ok = rule.get("pl_comp") in {"Greater Than","Less Than","Range"}
            if not comp_ok:
                continue
        # -------------------------------------
        applied = rule.get("applied_to") or all_ports  # empty => all
        applied = [p for p in applied if p in valid_dfs]  # safety
        if not applied:
            continue

        scope = rule.get("uni_common","Unique")
        direction = rule.get("profit_loss")
        pl_comp = rule.get("pl_comp","Greater Than")
        pl_from = float(rule.get("pl_from",0) or 0)
        pl_to = float(rule.get("pl_to",pl_from) or pl_from)
        inv_comp = rule.get("inv_comp","Greater Than")
        inv_from = float(rule.get("inv_from",0) or 0)
        inv_to = float(rule.get("inv_to",inv_from) or inv_from)
        message = rule.get("message") or rule.get("name") or "Alert"
        rule_name = rule.get("name") or f"Rule {rule.get('id','')}"

        def pl_filter(df):
            if df.empty or "pnl_pct" not in df.columns: return df.iloc[0:0]
            if direction == "Unchanged":
                return df[df["pnl_pct"].abs() <= 0.0001]
            base = df[df["pnl_pct"] > 0] if direction=="Profit" else df[df["pnl_pct"] < 0]
            if base.empty: return base
            val = base["pnl_pct"] if direction=="Profit" else base["pnl_pct"].abs()
            if pl_comp == "Greater Than":
                return base[val >= pl_from]
            if pl_comp == "Less Than":
                return base[val <= pl_from]
            if pl_comp == "Range":
                lo,hi = sorted([pl_from,pl_to])
                return base[(val >= lo) & (val <= hi)]
            return base

        def inv_filter(df):
            if df.empty or "invested" not in df.columns: return df.iloc[0:0]
            val = df["invested"]
            if inv_comp == "Greater Than": return df[val >= inv_from]
            if inv_comp == "Less Than": return df[val <= inv_from]
            if inv_comp == "Range":
                lo,hi = sorted([inv_from,inv_to])
                return df[(val >= lo) & (val <= hi)]
            return df

        # Determine candidate symbols per portfolio based on Unique/Common
        if scope == "Common":
            subset = rule.get("common_in") or applied
            subset = [p for p in subset if p in applied]
            if not subset: subset = applied
            if not subset: continue
            common_syms = set.intersection(*[inst_sets[p] for p in subset]) if subset else set()
            # We'll alert once per portfolio in 'subset' for each symbol (so user sees portfolio context)
            for p in subset:
                dfp = valid_dfs[p]
                part = dfp[dfp["instrument"].isin(common_syms)]
                part = inv_filter(pl_filter(part))
                for _, r in part.iterrows():
                    records.append({"instrument": r["instrument"],"portfolio": p,
                                    "rule": rule_name,"message": message})
        else:  # Unique
            # Unique within 'applied'
            union_applied = {p: inst_sets[p] for p in applied}
            for p in applied:
                others = set().union(*[union_applied[o] for o in applied if o != p])
                unique_syms = inst_sets[p] - others
                if not unique_syms: continue
                dfp = valid_dfs[p]
                part = dfp[dfp["instrument"].isin(unique_syms)]
                part = inv_filter(pl_filter(part))
                for _, r in part.iterrows():
                    records.append({"instrument": r["instrument"],"portfolio": p,
                                    "rule": rule_name,"message": message})

    if not records:
        return pd.DataFrame(columns=["instrument","portfolio","rule","message"])
    return pd.DataFrame(records).drop_duplicates().sort_values(["portfolio","instrument"])
