import pandas as pd
from typing import Dict, List


def _value_matches(comp: str, val: float, from_v: float, to_v: float) -> bool:
    if not comp:
        return True
    if comp == "Greater Than":
        return val >= from_v
    if comp == "Less Than":
        return val <= from_v
    if comp == "Range":
        lo, hi = sorted([from_v, to_v])
        return lo <= val <= hi
    return True


def generate_alerts(valid_dfs: Dict[str, pd.DataFrame], alert_rules: List[dict]) -> pd.DataFrame:
    if not valid_dfs or not alert_rules:
        return pd.DataFrame(columns=["instrument", "portfolio", "rule", "message"])

    # Ensure invested column
    prepared: Dict[str, pd.DataFrame] = {}
    for p, df in valid_dfs.items():
        if df is None or df.empty:
            prepared[p] = df
            continue
        if "invested" not in df.columns and {"quantity", "avg_price"}.issubset(df.columns):
            tmp = df.copy()
            tmp["invested"] = tmp["quantity"] * tmp["avg_price"]
            prepared[p] = tmp
        else:
            prepared[p] = df

    all_ports = list(prepared.keys())
    records = []

    for rule in alert_rules:
        # Extract rule fields with defaults
        applied = rule.get("applied_to") or all_ports
        applied = [p for p in applied if p in prepared and prepared[p] is not None and not prepared[p].empty]
        if not applied:
            continue

        direction = rule.get("profit_loss", "")
        pl_comp = rule.get("pl_comp", "")
        pl_from = float(rule.get("pl_from", 0) or 0)
        pl_to = float(rule.get("pl_to", pl_from) or pl_from)
        pl_basis = rule.get("pl_basis", "Per Portfolio")  # Per Portfolio | Total Avg

        inv_comp = rule.get("inv_comp", "")
        inv_from = float(rule.get("inv_from", 0) or 0)
        inv_to = float(rule.get("inv_to", inv_from) or inv_from)
        inv_level = rule.get("inv_level", "Per Stock")  # Per Portfolio | Per Stock

        presence = rule.get("stock_presence", "All")  # Unique | Not Unique | All
        rule_name = rule.get("name") or f"Rule {rule.get('id', '')}"
        message = rule.get("message") or ""

        # Basic direction validity
        if direction not in {"Profit", "Loss", "Unchanged", ""}:
            continue
        # If direction requires comparator ensure provided
        if direction and direction != "Unchanged" and pl_comp not in {"Greater Than", "Less Than", "Range"}:
            # allow empty comparator => treat as pass (skip threshold)
            pass

        # ---------- Investment gating (Per Portfolio) ----------
        if inv_level == "Per Portfolio" and inv_comp in {"Greater Than", "Less Than", "Range"}:
            passing_ports = []
            for p in applied:
                dfp = prepared[p]
                total_inv = float(dfp["invested"].sum()) if "invested" in dfp.columns else 0.0
                if _value_matches(inv_comp, total_inv, inv_from, inv_to):
                    passing_ports.append(p)
            if not passing_ports:
                continue
            target_ports = passing_ports
        else:
            target_ports = applied

        if not target_ports:
            continue

        # ---------- Build instrument -> portfolios map for presence filtering ----------
        inst_port_map = {}
        for p in target_ports:
            dfp = prepared[p]
            if dfp is None or dfp.empty or "instrument" not in dfp.columns:
                continue
            for sym in dfp["instrument"].dropna().unique():
                inst_port_map.setdefault(sym, set()).add(p)

        if not inst_port_map:
            continue

        if presence == "Unique":
            selected_syms = {s for s, ps in inst_port_map.items() if len(ps) == 1}
        elif presence == "Not Unique":
            selected_syms = {s for s, ps in inst_port_map.items() if len(ps) > 1}
        else:  # All
            selected_syms = set(inst_port_map.keys())

        if not selected_syms:
            continue

        # ---------- Helper: direction + comparator logic ----------
        def direction_mask(df: pd.DataFrame) -> pd.Series:
            if "pnl_pct" not in df.columns:
                return pd.Series(False, index=df.index)
            if direction == "Profit":
                return df["pnl_pct"] > 0
            if direction == "Loss":
                return df["pnl_pct"] < 0
            if direction == "Unchanged":
                return df["pnl_pct"].abs() <= 0.0001
            # No direction specified => accept all
            return pd.Series(True, index=df.index)

        def row_comp_series(df: pd.DataFrame) -> pd.Series:
            # Value to compare according to direction
            if "pnl_pct" not in df.columns:
                return pd.Series([], dtype=float)
            if direction == "Loss":
                return df["pnl_pct"].abs()
            if direction == "Unchanged":
                return df["pnl_pct"].abs()
            return df["pnl_pct"]

        # ---------- Iterate symbols ----------
        for sym in selected_syms:
            holding_ports = inst_port_map[sym]
            # Gather rows across holding portfolios
            rows_list = []
            for p in holding_ports:
                if p not in target_ports:
                    continue
                dfp = prepared[p]
                part = dfp[dfp["instrument"] == sym].copy()
                if part.empty:
                    continue

                # Per Stock investment filter
                if inv_level == "Per Stock" and inv_comp in {"Greater Than", "Less Than", "Range"}:
                    if "invested" in part.columns:
                        inv_vals = part["invested"]
                        if inv_comp == "Greater Than":
                            part = part[inv_vals >= inv_from]
                        elif inv_comp == "Less Than":
                            part = part[inv_vals <= inv_from]
                        elif inv_comp == "Range":
                            lo, hi = sorted([inv_from, inv_to])
                            part = part[(inv_vals >= lo) & (inv_vals <= hi)]
                        if part.empty:
                            continue

                # Direction filter
                m = direction_mask(part)
                part = part[m]
                if part.empty:
                    continue

                part["__portfolio"] = p
                rows_list.append(part)

            if not rows_list:
                continue

            sym_df = pd.concat(rows_list, ignore_index=True)

            # If direction is Unchanged we optionally still can check comparator if provided
            comp_series = row_comp_series(sym_df)

            emit_df = sym_df

            if direction == "Unchanged":
                # Comparator optional; if provided apply
                if pl_comp in {"Greater Than", "Less Than", "Range"}:
                    mask_comp = comp_series.apply(lambda v: _value_matches(pl_comp, v, pl_from, pl_to))
                    emit_df = sym_df[mask_comp]
                    if emit_df.empty:
                        continue
            else:
                # Only apply comparator if provided
                if pl_comp in {"Greater Than", "Less Than", "Range"}:
                    if pl_basis == "Per Portfolio":
                        mask_comp = comp_series.apply(lambda v: _value_matches(pl_comp, v, pl_from, pl_to))
                        emit_df = sym_df[mask_comp]
                        if emit_df.empty:
                            continue
                    else:  # Total Avg
                        avg_val = float(comp_series.mean()) if not comp_series.empty else 0.0
                        if not _value_matches(pl_comp, avg_val, pl_from, pl_to):
                            continue
                        # Average passes -> keep all rows already direction-filtered

            if emit_df.empty:
                continue

            # Emit alert rows (one per portfolio holding)
            for p in emit_df["__portfolio"].unique():
                records.append({
                    "instrument": sym,
                    "portfolio": p,
                    "rule": rule_name,
                    "message": message
                })

    if not records:
        return pd.DataFrame(columns=["instrument", "portfolio", "rule", "message"])
    return (
        pd.DataFrame(records)
        .drop_duplicates()
        .sort_values(["portfolio", "instrument"])
        .reset_index(drop=True)
    )
