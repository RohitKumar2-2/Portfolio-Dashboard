import pandas as pd
from utils.helpers import rupees

# ---------- Normalizer ----------
def normalize_symbol(s: str) -> str:
    """Standardize stock symbols for matching across portfolios."""
    if not isinstance(s, str):
        return s
    return s.strip().upper().replace(".NS", "")

def _extract_pl_context(row):
    """
    Returns dict with:
      invested, pl_abs, pl_pct
    Accepts multiple possible schemas.
    """
    # Invested
    invested = (
        row.get("invested")
        or row.get("Invested")
        or ( (row.get("avg_price") or row.get("average_price") or 0) * (row.get("quantity") or row.get("qty") or 0) )
        or 0
    )
    # Absolute P&L
    pl_abs = (
        row.get("pl")
        or row.get("P&L")
        or row.get("pnl_abs")
    )
    if pl_abs is None:
        avg = row.get("avg_price") or row.get("average_price")
        ltp = row.get("ltp") or row.get("LTP") or row.get("last_price")
        qty = row.get("quantity") or row.get("qty") or 0
        if avg is not None and ltp is not None:
            try:
                pl_abs = (ltp - avg) * qty
            except Exception:
                pl_abs = 0
        else:
            pl_abs = 0

    # Percentage P&L
    pl_pct = row.get("pnl_pct")
    if pl_pct is None:
        if invested:
            pl_pct = (pl_abs / invested) * 100 if invested else 0
        else:
            pl_pct = 0

    return {
        "invested": float(invested) if invested else 0.0,
        "pl_abs": float(pl_abs) if pl_abs else 0.0,
        "pl_pct": float(pl_pct) if pl_pct else 0.0
    }

# ---------- Alerts ----------
def generate_alerts(
    dfs: dict,
    common_list: list,
    unique_per: dict,
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
    """
    Generate portfolio-wise alerts based on rules.

    Returns:
        pd.DataFrame with columns:
        ['category','type','instrument','message','portfolio','invested','pl_pct','rule']
    """
    alerts = []

    # ---------- Normalize instruments in all dfs ----------
    dfs = {
        port: df.rename(columns=str.lower).assign(
            instrument=df['instrument'].apply(normalize_symbol)
        )
        for port, df in dfs.items()
    }

    # Normalize unique & common lists
    common_list = [normalize_symbol(x) for x in common_list]
    unique_per = {p: [normalize_symbol(x) for x in lst] for p, lst in unique_per.items()}

    # ------------------ Unique Stock Opportunities ------------------
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
                    'category': 'Yellow',
                    'type': 'Opportunity (Unique - down > threshold)',
                    'instrument': ins,
                    'message': f"Opportunity: Add {ins} to other portfolios. It's down {round(pl_pct,2)}% with {rupees(invested)} invested.",
                    'portfolio': port,
                    'invested': invested,
                    'pl_pct': pl_pct,
                    'rule': f"unique & loss>{uniq_loss_thresh}%"
                })

    # ------------------ Average Out (Common Stocks) ------------------
    common_set = set(common_list)
    for port, df in dfs.items():
        for ins in set(df['instrument']).intersection(common_set):
            r = df[df['instrument'] == ins]
            invested = float(r['invested'].sum())
            pl = float(r['pl'].sum())
            loss_pct = (pl / invested * 100) if invested else 0
            if loss_pct < -common_small_loss and invested < small_amt:
                alerts.append({
                    'category': 'Red',
                    'type': 'Average Out (Small Invest)',
                    'instrument': ins,
                    'message': f"Average Out (small): {ins} is down {round(loss_pct,2)}% with invested {rupees(invested)} in {port}.",
                    'portfolio': port,
                    'invested': invested,
                    'pl_pct': loss_pct,
                    'rule': f"loss>{common_small_loss}% & invested<{rupees(small_amt)}"
                })
            if loss_pct < -common_large_loss and invested > large_amt:
                alerts.append({
                    'category': 'Red',
                    'type': 'Average Out (Large Invest)',
                    'instrument': ins,
                    'message': f"Average Out (large): {ins} is down {round(loss_pct,2)}% with invested {rupees(invested)} in {port}.",
                    'portfolio': port,
                    'invested': invested,
                    'pl_pct': loss_pct,
                    'rule': f"loss>{common_large_loss}% & invested>{rupees(large_amt)}"
                })

    # ------------------ Book Profit ------------------
    for port, df in dfs.items():
        for _, r in df.iterrows():
            ins = r['instrument']
            invested = float(r['invested'])
            pl = float(r['pl'])
            pl_pct = (pl / invested * 100) if invested else 0
            if pl_pct > profit_small_pct and invested < profit_large_amt:
                alerts.append({
                    'category': 'Green',
                    'type': 'Book Profit (Small)',
                    'instrument': ins,
                    'message': f"Book Profit: {ins} is up {round(pl_pct,2)}% with invested {rupees(invested)} in {port}.",
                    'portfolio': port,
                    'invested': invested,
                    'pl_pct': pl_pct,
                    'rule': f"profit>{profit_small_pct}% & invested<{rupees(profit_large_amt)}"
                })
            if pl_pct > profit_large_pct and invested > profit_large_amt:
                alerts.append({
                    'category': 'Green',
                    'type': 'Book Profit (Large)',
                    'instrument': ins,
                    'message': f"Book Profit: {ins} is up {round(pl_pct,2)}% with invested {rupees(invested)} in {port}.",
                    'portfolio': port,
                    'invested': invested,
                    'pl_pct': pl_pct,
                    'rule': f"profit>{profit_large_pct}% & invested>{rupees(profit_large_amt)}"
                })

    # ------------------ Return as DataFrame ------------------
    if not alerts:
        return pd.DataFrame(columns=['category','type','instrument','message','portfolio','invested','pl_pct','rule'])

    return pd.DataFrame(alerts).sort_values(
        ['category','type','instrument']
    ).reset_index(drop=True)

    # ---------- Alerts ----------
def generate_alerts(
    dfs: dict,
    common_list: list,
    unique_per: dict,
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
    """
    Robust alert generator that no longer assumes 'pl' column.
    """
    alerts = []

    for pname, df in dfs.items():
        if df.empty:
            continue

        for _, r in df.iterrows():
            symbol = r.get("instrument") or r.get("symbol") or r.get("tradingsymbol")
            if not symbol:
                continue

            ctx = _extract_pl_context(r)
            invested = ctx["invested"]
            pl_abs = ctx["pl_abs"]
            pl_pct = ctx["pl_pct"]

            # Determine common / unique
            is_common = symbol in common_list

            # Loss scenarios
            if pl_pct < 0:
                loss_pct = abs(pl_pct)

                # Unique stock loss alert
                if (not is_common) and loss_pct >= uniq_loss_thresh:
                    alerts.append({
                        "instrument": symbol,
                        "portfolio": pname,
                        "category": "Red" if invested >= large_amt else "Yellow",
                        "rule": f"Unique loss >= {uniq_loss_thresh}%",
                        "message": f"Unique holding down {loss_pct:.2f}% (₹{pl_abs:.0f})"
                    })

                # Common stock – scale thresholds
                if is_common:
                    if loss_pct >= common_large_loss:
                        alerts.append({
                            "instrument": symbol,
                            "portfolio": pname,
                            "category": "Red",
                            "rule": f"Common loss >= {common_large_loss}%",
                            "message": f"Common holding heavy loss {loss_pct:.2f}%"
                        })
                    elif loss_pct >= common_small_loss:
                        alerts.append({
                            "instrument": symbol,
                            "portfolio": pname,
                            "category": "Yellow",
                            "rule": f"Common loss >= {common_small_loss}%",
                            "message": f"Common holding moderate loss {loss_pct:.2f}%"
                        })

            # Profit booking
            if pl_pct > 0:
                if invested >= large_amt and pl_pct >= profit_large_pct:
                    alerts.append({
                        "instrument": symbol,
                        "portfolio": pname,
                        "category": "Green",
                        "rule": f"Large invest profit >= {profit_large_pct}%",
                        "message": f"Large position up {pl_pct:.2f}% (₹{pl_abs:.0f})"
                    })
                elif invested < large_amt and pl_pct >= profit_small_pct:
                    alerts.append({
                        "instrument": symbol,
                        "portfolio": pname,
                        "category": "Green",
                        "rule": f"Small invest profit >= {profit_small_pct}%",
                        "message": f"Up {pl_pct:.2f}% (₹{pl_abs:.0f})"
                    })

    if not alerts:
        return pd.DataFrame(columns=["instrument","portfolio","category","rule","message"])

    return pd.DataFrame(alerts)
