from utils.helpers import rupees
import math

def portfolio_highlights(df):
    """
    Return dict with top 3 by invested (capital), profit and loss.
    Works with any of these possible schemas:
      invested / Invested
      pl / P&L / pnl_abs
      pnl_pct (optional)
      avg_price + ltp (+ quantity) to derive values if missing
    """
    if df is None or df.empty:
        return {"max_capital": [], "max_profit": [], "max_loss": []}

    d = df.copy()

    # Standardize / derive invested
    if "invested" in d.columns:
        d["_invested"] = d["invested"]
    elif "Invested" in d.columns:
        d["_invested"] = d["Invested"]
    else:
        qty_col = next((c for c in ["quantity", "qty", "Quantity"] if c in d.columns), None)
        avg_col = next((c for c in ["avg_price", "average_price", "Avg. cost"] if c in d.columns), None)
        if qty_col and avg_col:
            d["_invested"] = d[qty_col].fillna(0) * d[avg_col].fillna(0)
        else:
            d["_invested"] = 0

    # Standardize / derive absolute P&L
    if "pl" in d.columns:
        d["_pl_abs"] = d["pl"]
    elif "P&L" in d.columns:
        d["_pl_abs"] = d["P&L"]
    elif "pnl_abs" in d.columns:
        d["_pl_abs"] = d["pnl_abs"]
    else:
        # derive from prices
        qty_col = next((c for c in ["quantity", "qty", "Quantity"] if c in d.columns), None)
        avg_col = next((c for c in ["avg_price", "average_price", "Avg. cost"] if c in d.columns), None)
        ltp_col = next((c for c in ["ltp", "LTP", "last_price"] if c in d.columns), None)
        if qty_col and avg_col and ltp_col:
            d["_pl_abs"] = (d[ltp_col] - d[avg_col]) * d[qty_col]
        else:
            d["_pl_abs"] = 0

    # Standardize / derive percentage P&L
    if "pnl_pct" in d.columns:
        d["_pl_pct"] = d["pnl_pct"]
    else:
        with_pct = (d["_invested"] != 0)
        d["_pl_pct"] = d["_pl_abs"] / d["_invested"].where(with_pct, 1).replace({0: 1}) * 100
        d.loc[~with_pct, "_pl_pct"] = 0

    # Instrument column
    inst_col = next((c for c in ["instrument", "symbol", "tradingsymbol", "name"] if c in d.columns), None)
    if not inst_col:
        return {"max_capital": [], "max_profit": [], "max_loss": []}

    # Clean numeric
    for c in ["_invested", "_pl_abs", "_pl_pct"]:
        d[c] = d[c].fillna(0)

    # Top 3 by capital
    cap = (
        d.sort_values("_invested", ascending=False)
         .head(3)
         .apply(lambda r: f"{r[inst_col]} | Invested ₹{r['_invested']:.0f} | P&L {r['_pl_abs']:.0f} ( {r['_pl_pct']:.2f}% )", axis=1)
         .tolist()
    )

    # Top 3 profit (positive pl_abs)
    prof_src = d[d["_pl_abs"] > 0].sort_values("_pl_abs", ascending=False).head(3)
    prof = prof_src.apply(lambda r: f"{r[inst_col]} | ₹{r['_pl_abs']:.0f} ( {r['_pl_pct']:.2f}% )", axis=1).tolist()

    # Top 3 loss (negative pl_abs)
    loss_src = d[d["_pl_abs"] < 0].sort_values("_pl_abs").head(3)
    loss = loss_src.apply(lambda r: f"{r[inst_col]} | ₹{r['_pl_abs']:.0f} ( {r['_pl_pct']:.2f}% )", axis=1).tolist()

    return {
        "max_capital": cap,
        "max_profit": prof,
        "max_loss": loss
    }
