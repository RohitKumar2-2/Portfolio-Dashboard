import pandas as pd
from typing import Dict, List

def _value_matches(comp: str, val: float, from_v: float, to_v: float) -> bool:
    if comp == "Greater Than":
        return val >= from_v
    if comp == "Less Than":
        return val <= from_v
    if comp == "Range":
        lo, hi = sorted([from_v, to_v])
        return lo <= val <= hi
    return False

def generate_alerts(valid_dfs: Dict[str, pd.DataFrame], alert_rules: List[dict]) -> pd.DataFrame:
    if not valid_dfs or not alert_rules:
        return pd.DataFrame(columns=["instrument","portfolio","rule","message"])

    # Ensure invested column exists (quantity * avg_price fallback)
    prepared = {}
    for p, df in valid_dfs.items():
        if df is None or df.empty:
            prepared[p] = df
            continue
        if "invested" not in df.columns:
            tmp = df.copy()
            if "quantity" in tmp.columns and "avg_price" in tmp.columns:
                tmp["invested"] = tmp["quantity"] * tmp["avg_price"]
            else:
                tmp["invested"] = 0.0
            prepared[p] = tmp
        else:
            prepared[p] = df

    inst_sets = {p: set(df["instrument"].dropna().unique()) for p, df in prepared.items() if df is not None and not df.empty}
    all_ports = list(prepared.keys())
    records = []

    for rule in alert_rules:
        # Basic rule validity checks
        dir_ok = rule.get("profit_loss") in {"Profit","Loss","Unchanged"}
        inv_ok = rule.get("inv_comp") in {"Greater Than","Less Than","Range"}
        if not dir_ok or not inv_ok:
            continue
        if rule.get("profit_loss") != "Unchanged":
            if rule.get("pl_comp") not in {"Greater Than","Less Than","Range"}:
                continue

        applied = rule.get("applied_to") or all_ports
        applied = [p for p in applied if p in prepared]
        if not applied:
            continue

        scope        = rule.get("uni_common","Unique")
        direction    = rule.get("profit_loss")
        pl_comp      = rule.get("pl_comp","Greater Than")
        pl_from      = float(rule.get("pl_from",0) or 0)
        pl_to        = float(rule.get("pl_to",pl_from) or pl_from)
        inv_comp     = rule.get("inv_comp","Greater Than")
        inv_from     = float(rule.get("inv_from",0) or 0)
        inv_to       = float(rule.get("inv_to",inv_from) or inv_from)
        inv_level    = rule.get("inv_level","Per Stock")  # NEW
        message      = rule.get("message") or rule.get("name") or "Alert"
        rule_name    = rule.get("name") or f"Rule {rule.get('id','')}"

        # ---- P/L filter function (row-level) ----
        def pl_filter(df: pd.DataFrame) -> pd.DataFrame:
            if df.empty or "pnl_pct" not in df.columns:
                return df.iloc[0:0]
            if direction == "Unchanged":
                return df[df["pnl_pct"].abs() <= 0.0001]
            base = df[df["pnl_pct"] > 0] if direction == "Profit" else df[df["pnl_pct"] < 0]
            if base.empty:
                return base
            # For Loss compare on absolute magnitude
            val = base["pnl_pct"] if direction == "Profit" else base["pnl_pct"].abs()
            if pl_comp == "Greater Than":
                return base[val >= pl_from]
            if pl_comp == "Less Than":
                return base[val <= pl_from]
            if pl_comp == "Range":
                lo, hi = sorted([pl_from, pl_to])
                return base[(val >= lo) & (val <= hi)]
            return base

        # ---- Investment filtering logic ----
        # Per Portfolio gate: decide which portfolios pass BEFORE symbol selection
        if inv_level == "Per Portfolio":
            passing_ports = []
            for p in applied:
                dfp = prepared[p]
                if dfp is None or dfp.empty:
                    continue
                total_inv = float(dfp["invested"].sum())
                if _value_matches(inv_comp, total_inv, inv_from, inv_to):
                    passing_ports.append(p)
            if not passing_ports:
                continue  # no portfolio satisfies investment gate
            target_ports_for_scope = passing_ports
        else:
            # Per Stock: we will apply comparator later per row; keep original applied list now
            target_ports_for_scope = applied

        # ---- Scope (Unique / Common) symbol selection ----
        if scope == "Common":
            subset = rule.get("common_in") or target_ports_for_scope
            subset = [p for p in subset if p in target_ports_for_scope]
            if not subset:
                continue
            # Intersection of instruments across subset portfolios
            if not subset:
                continue
            common_syms = set.intersection(*[inst_sets.get(p,set()) for p in subset]) if all(p in inst_sets for p in subset) else set()
            if not common_syms:
                continue
            for p in subset:
                dfp = prepared[p]
                if dfp is None or dfp.empty:
                    continue
                part = dfp[dfp["instrument"].isin(common_syms)].copy()
                if part.empty:
                    continue
                # Apply row-level investment filter only if Per Stock
                if inv_level == "Per Stock":
                    val = part["invested"]
                    if inv_comp == "Greater Than":
                        part = part[val >= inv_from]
                    elif inv_comp == "Less Than":
                        part = part[val <= inv_from]
                    elif inv_comp == "Range":
                        lo, hi = sorted([inv_from, inv_to])
                        part = part[(val >= lo) & (val <= hi)]
                # P/L filter
                part = pl_filter(part)
                if part.empty:
                    continue
                for _, r in part.iterrows():
                    records.append({
                        "instrument": r["instrument"],
                        "portfolio": p,
                        "rule": rule_name,
                        "message": message
                    })
        else:  # Unique
            for p in target_ports_for_scope:
                dfp = prepared[p]
                if dfp is None or dfp.empty:
                    continue
                # Unique symbols relative to other (target) portfolios
                others = set().union(*[inst_sets.get(o,set()) for o in target_ports_for_scope if o != p])
                unique_syms = inst_sets.get(p,set()) - others
                if not unique_syms:
                    continue
                part = dfp[dfp["instrument"].isin(unique_syms)].copy()
                if part.empty:
                    continue
                if inv_level == "Per Stock":
                    val = part["invested"]
                    if inv_comp == "Greater Than":
                        part = part[val >= inv_from]
                    elif inv_comp == "Less Than":
                        part = part[val <= inv_from]
                    elif inv_comp == "Range":
                        lo, hi = sorted([inv_from, inv_to])
                        part = part[(val >= lo) & (val <= hi)]
                # (If Per Portfolio we already gated; no per-row invested filter.)
                part = pl_filter(part)
                if part.empty:
                    continue
                for _, r in part.iterrows():
                    records.append({
                        "instrument": r["instrument"],
                        "portfolio": p,
                        "rule": rule_name,
                        "message": message
                    })

    if not records:
        return pd.DataFrame(columns=["instrument","portfolio","rule","message"])
    return pd.DataFrame(records).drop_duplicates().sort_values(["portfolio","instrument"])
