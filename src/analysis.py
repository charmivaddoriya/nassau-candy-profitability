"""Core analytics for the Nassau Candy product-line profitability project.

Used by both the Streamlit dashboard (app.py) and the batch script (run_analysis.py).
"""
from pathlib import Path

import numpy as np
import pandas as pd

DATA_PATH = Path(__file__).resolve().parent.parent / "data" / "Nassau_Candy_Distributor.csv"

FACTORY_MAP = {
    "Wonka Bar - Nutty Crunch Surprise": "Lot's O' Nuts",
    "Wonka Bar - Fudge Mallows": "Lot's O' Nuts",
    "Wonka Bar - Scrumdiddlyumptious": "Lot's O' Nuts",
    "Wonka Bar - Milk Chocolate": "Wicked Choccy's",
    "Wonka Bar - Triple Dazzle Caramel": "Wicked Choccy's",
    "Laffy Taffy": "Sugar Shack",
    "SweeTARTS": "Sugar Shack",
    "Nerds": "Sugar Shack",
    "Fun Dip": "Sugar Shack",
    "Fizzy Lifting Drinks": "Sugar Shack",
    "Everlasting Gobstopper": "Secret Factory",
    "Hair Toffee": "The Other Factory",
    "Lickable Wallpaper": "Secret Factory",
    "Wonka Gum": "Secret Factory",
    "Kazookles": "The Other Factory",
}


def standardize_label(s: pd.Series) -> pd.Series:
    """Trim, collapse spaces and fix hyphen spacing, e.g. 'Wonka Bar -X' -> 'Wonka Bar - X'."""
    s = s.astype(str).str.strip().str.replace(r"\s+", " ", regex=True)
    s = s.str.replace(r"\s*-\s*", " - ", regex=True)
    return s


def load_and_clean(path=DATA_PATH):
    """Return (clean_df, log) where log lists every cleaning step and rows affected."""
    df = pd.read_csv(path)
    log = [("Raw rows", len(df))]

    df["Order Date"] = pd.to_datetime(df["Order Date"], format="%d-%m-%Y", errors="coerce")
    df["Ship Date"] = pd.to_datetime(df["Ship Date"], format="%d-%m-%Y", errors="coerce")
    log.append(("Unparseable order dates", int(df["Order Date"].isna().sum())))

    df["Product Name"] = standardize_label(df["Product Name"])
    df["Division"] = standardize_label(df["Division"]).str.title()

    n0 = len(df)
    df = df.drop_duplicates(subset="Row ID")
    log.append(("Duplicate Row IDs removed", n0 - len(df)))

    n0 = len(df)
    df = df[(df["Sales"] > 0) & df["Order Date"].notna()]
    log.append(("Zero/negative-sales or undated rows removed", n0 - len(df)))

    # Units: impute missing/zero from sales / median unit price of the product
    bad_units = df["Units"].isna() | (df["Units"] <= 0)
    log.append(("Missing/zero unit values imputed", int(bad_units.sum())))
    if bad_units.any():
        price = (df["Sales"] / df["Units"].where(df["Units"] > 0)).groupby(df["Product Name"]).transform("median")
        df.loc[bad_units, "Units"] = (df.loc[bad_units, "Sales"] / price[bad_units]).round().clip(lower=1)

    # Validate Gross Profit = Sales - Cost
    mismatch = (df["Sales"] - df["Cost"] - df["Gross Profit"]).abs() > 0.02
    log.append(("Rows where Gross Profit != Sales - Cost (recomputed)", int(mismatch.sum())))
    df.loc[mismatch, "Gross Profit"] = df.loc[mismatch, "Sales"] - df.loc[mismatch, "Cost"]

    n0 = len(df)
    df = df[(df["Cost"] >= 0) & (df["Gross Profit"].notna())]
    log.append(("Invalid cost/profit rows removed", n0 - len(df)))

    df["Factory"] = df["Product Name"].map(FACTORY_MAP)
    df["Month"] = df["Order Date"].dt.to_period("M").dt.to_timestamp()
    log.append(("Clean rows", len(df)))
    return df.reset_index(drop=True), log


def product_metrics(df: pd.DataFrame) -> pd.DataFrame:
    """Per-product KPIs including margin volatility (std-dev of monthly margin, in pct-points)."""
    g = df.groupby(["Division", "Product Name", "Factory"], dropna=False).agg(
        Sales=("Sales", "sum"), Cost=("Cost", "sum"), Gross_Profit=("Gross Profit", "sum"),
        Units=("Units", "sum"), Orders=("Order ID", "nunique"),
    ).reset_index()
    tot_s, tot_p = g["Sales"].sum(), g["Gross_Profit"].sum()
    g["Gross_Margin_%"] = g["Gross_Profit"] / g["Sales"] * 100
    g["Profit_per_Unit"] = g["Gross_Profit"] / g["Units"]
    g["Price_per_Unit"] = g["Sales"] / g["Units"]
    g["Cost_per_Unit"] = g["Cost"] / g["Units"]
    g["Revenue_Contribution_%"] = g["Sales"] / tot_s * 100
    g["Profit_Contribution_%"] = g["Gross_Profit"] / tot_p * 100

    m = df.groupby(["Product Name", "Month"]).agg(S=("Sales", "sum"), P=("Gross Profit", "sum")).reset_index()
    m = m[m["S"] > 0]
    m["gm"] = m["P"] / m["S"] * 100
    vol = m.groupby("Product Name")["gm"].agg(["std", "count"])
    # require >= 6 active months for a meaningful volatility figure
    vol.loc[vol["count"] < 6, "std"] = np.nan
    g["Margin_Volatility"] = g["Product Name"].map(vol["std"]).round(6)
    return g.sort_values("Gross_Profit", ascending=False).reset_index(drop=True)


def classify_products(pm: pd.DataFrame, margin_threshold=None) -> pd.DataFrame:
    """Quadrant classification + action flag.

    Sales cut-off = median across products; margin cut-off = portfolio margin
    (or user-supplied threshold).
    """
    pm = pm.copy()
    portfolio_gm = pm["Gross_Profit"].sum() / pm["Sales"].sum() * 100
    thr = portfolio_gm if margin_threshold is None else margin_threshold
    s_med = pm["Sales"].median()

    def quad(r):
        hi_s = r["Sales"] >= s_med
        hi_m = r["Gross_Margin_%"] >= thr
        if hi_s and hi_m:
            return "High sales / High margin (Star)"
        if hi_s and not hi_m:
            return "High sales / Low margin (Watch)"
        if not hi_s and hi_m:
            return "Low sales / High margin (Niche)"
        return "Low sales / Low margin (Review)"

    def flag(r):
        low_margin = r["Gross_Margin_%"] < thr
        cost_heavy = r["Cost"] / r["Sales"] > 0.5
        small = r["Profit_Contribution_%"] < 1
        if not low_margin:
            return "OK"
        if small and r["Gross_Margin_%"] < 0.5 * thr:
            return "Discontinuation review"
        if small:
            return "Low-volume / portfolio review"
        if cost_heavy:
            return "Cost renegotiation / Repricing"
        return "Pricing review"

    pm["Segment"] = pm.apply(quad, axis=1)
    pm["Margin_Risk_Flag"] = pm.apply(flag, axis=1)
    pm["Below_Threshold"] = pm["Gross_Margin_%"] < thr
    pm.attrs["threshold"] = thr
    return pm


def division_metrics(df: pd.DataFrame) -> pd.DataFrame:
    d = df.groupby("Division").agg(
        Sales=("Sales", "sum"), Cost=("Cost", "sum"), Gross_Profit=("Gross Profit", "sum"),
        Units=("Units", "sum"), Products=("Product Name", "nunique"),
    ).reset_index()
    d["Gross_Margin_%"] = d["Gross_Profit"] / d["Sales"] * 100
    d["Revenue_Share_%"] = d["Sales"] / d["Sales"].sum() * 100
    d["Profit_Share_%"] = d["Gross_Profit"] / d["Gross_Profit"].sum() * 100
    d["Profit_minus_Revenue_Share_pp"] = d["Profit_Share_%"] - d["Revenue_Share_%"]
    d["Profit_per_Unit"] = d["Gross_Profit"] / d["Units"]
    avg_m = df.assign(gm=df["Gross Profit"] / df["Sales"] * 100).groupby("Division")["gm"].mean()
    d["Avg_Order_Line_Margin_%"] = d["Division"].map(avg_m)
    return d.sort_values("Gross_Profit", ascending=False).reset_index(drop=True)


def pareto(pm: pd.DataFrame, col: str) -> pd.DataFrame:
    p = pm[["Product Name", col]].sort_values(col, ascending=False).reset_index(drop=True)
    p["Cum_%"] = p[col].cumsum() / p[col].sum() * 100
    p["Rank"] = np.arange(1, len(p) + 1)
    p["Products_%"] = p["Rank"] / len(p) * 100
    return p


def pareto_summary(pm: pd.DataFrame) -> dict:
    out = {}
    for label, col in [("revenue", "Sales"), ("profit", "Gross_Profit")]:
        p = pareto(pm, col)
        k = int((p["Cum_%"] < 80).sum() + 1)
        out[label] = {"products": k, "pct_of_products": k / len(p) * 100, "top1_share": p[col].iloc[0] / p[col].sum() * 100}
    shares = pm["Profit_Contribution_%"] / 100
    out["hhi_profit"] = float((shares ** 2).sum() * 10000)
    return out


def monthly_trend(df: pd.DataFrame, by=None) -> pd.DataFrame:
    keys = ["Month"] + ([by] if by else [])
    t = df.groupby(keys).agg(Sales=("Sales", "sum"), Gross_Profit=("Gross Profit", "sum")).reset_index()
    t["Gross_Margin_%"] = t["Gross_Profit"] / t["Sales"] * 100
    return t
