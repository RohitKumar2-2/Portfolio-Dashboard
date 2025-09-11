import pandas as pd

def load_csv_portfolio(file_path, portfolio_name="CSV Portfolio"):
    """Load Zerodha/Other portfolio CSV into standard format DataFrame."""
    try:
        df = pd.read_csv(file_path)

        # Try to match standard column names
        df.rename(columns={
            "Instrument": "instrument",
            "Qty.": "qty",
            "Avg. cost": "avg_cost",
            "LTP": "ltp",
            "Invested": "invested",
            "Cur. val": "cur_val",
            "P&L": "pl",
            "Net chg.": "net_chg",
            "Day chg.": "day_chg"
        }, inplace=True)

        # Calculate missing fields if not present
        if "invested" not in df.columns:
            df["invested"] = df["qty"] * df["avg_cost"]
        if "cur_val" not in df.columns:
            df["cur_val"] = df["qty"] * df["ltp"]
        if "pl" not in df.columns:
            df["pl"] = df["cur_val"] - df["invested"]

        df["portfolio"] = portfolio_name
        return df

    except Exception as e:
        print(f"❌ Failed to load {file_path}: {e}")
        return pd.DataFrame()

