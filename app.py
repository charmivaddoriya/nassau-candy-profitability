"""Nassau Candy - Product Line Profitability & Margin Performance dashboard (Streamlit)."""
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from src.analysis import (classify_products, division_metrics, load_and_clean, monthly_trend,
                          pareto, pareto_summary, product_metrics)

st.set_page_config(page_title="Nassau Candy - Profitability", page_icon="🍬", layout="wide")


@st.cache_data
def get_data():
    df, log = load_and_clean()
    return df, log


df_all, clean_log = get_data()

# ---------------- Sidebar controls ----------------
st.sidebar.title("🍬 Filters")
dmin, dmax = df_all["Order Date"].min().date(), df_all["Order Date"].max().date()
date_range = st.sidebar.date_input("Order date range", (dmin, dmax), min_value=dmin, max_value=dmax)
divisions = sorted(df_all["Division"].unique())
sel_div = st.sidebar.multiselect("Division", divisions, default=divisions)
search = st.sidebar.text_input("Product search", placeholder="e.g. Wonka, Gum, Taffy")
margin_thr = st.sidebar.slider("Margin threshold (%)", 0, 100, 50, help="Products below this gross margin are flagged as margin risks.")

if isinstance(date_range, (tuple, list)) and len(date_range) == 2:
    start, end = date_range
else:
    start, end = dmin, dmax

df = df_all[(df_all["Order Date"].dt.date >= start) & (df_all["Order Date"].dt.date <= end) & (df_all["Division"].isin(sel_div))]
if search:
    df = df[df["Product Name"].str.contains(search, case=False, regex=False)]

st.title("Product Line Profitability & Margin Performance")
st.caption("Nassau Candy Distributor · Gross margin = Gross Profit ÷ Sales")

if df.empty:
    st.warning("No data for the selected filters.")
    st.stop()

pm = classify_products(product_metrics(df), margin_threshold=float(margin_thr))
dm = division_metrics(df)

# ---------------- KPI strip ----------------
tot_s, tot_p = df["Sales"].sum(), df["Gross Profit"].sum()
k = st.columns(5)
k[0].metric("Sales", f"${tot_s:,.0f}")
k[1].metric("Gross profit", f"${tot_p:,.0f}")
k[2].metric("Gross margin", f"{tot_p / tot_s * 100:.1f}%")
k[3].metric("Profit / unit", f"${tot_p / df['Units'].sum():.2f}")
k[4].metric("Products below threshold", int(pm["Below_Threshold"].sum()), help=f"Gross margin < {margin_thr}%")

tab1, tab2, tab3, tab4, tab5 = st.tabs(["Product overview", "Division performance", "Cost vs margin", "Profit concentration", "Data & method"])

# ---------------- Tab 1 ----------------
with tab1:
    c1, c2 = st.columns(2)
    lb = pm.sort_values("Gross_Margin_%")
    fig = px.bar(lb, x="Gross_Margin_%", y="Product Name", orientation="h", color="Gross_Margin_%",
                 color_continuous_scale="RdYlGn", title="Gross margin leaderboard (%)")
    fig.add_vline(x=margin_thr, line_dash="dash", line_color="black")
    fig.update_layout(coloraxis_showscale=False, yaxis_title=None)
    c1.plotly_chart(fig, use_container_width=True)
    fig = px.bar(pm.sort_values("Gross_Profit"), x="Gross_Profit", y="Product Name", orientation="h",
                 color="Division", title="Total profit contribution ($)")
    fig.update_layout(yaxis_title=None)
    c2.plotly_chart(fig, use_container_width=True)

    seg = px.scatter(pm, x="Sales", y="Gross_Margin_%", size="Gross_Profit", color="Segment", hover_name="Product Name",
                     log_x=True, title="Sales vs margin segments (bubble = gross profit)")
    seg.add_hline(y=margin_thr, line_dash="dash")
    st.plotly_chart(seg, use_container_width=True)

    st.subheader("Product table")
    show = pm[["Product Name", "Division", "Sales", "Gross_Profit", "Gross_Margin_%", "Profit_per_Unit",
               "Revenue_Contribution_%", "Profit_Contribution_%", "Margin_Volatility", "Segment"]].round(2)
    st.dataframe(show, use_container_width=True, hide_index=True)

# ---------------- Tab 2 ----------------
with tab2:
    c1, c2 = st.columns(2)
    long = dm.melt(id_vars="Division", value_vars=["Sales", "Gross_Profit"], var_name="Metric", value_name="USD")
    c1.plotly_chart(px.bar(long, x="Division", y="USD", color="Metric", barmode="group", title="Revenue vs gross profit"),
                    use_container_width=True)
    share = dm.melt(id_vars="Division", value_vars=["Revenue_Share_%", "Profit_Share_%"], var_name="Metric", value_name="%")
    c2.plotly_chart(px.bar(share, x="Division", y="%", color="Metric", barmode="group", title="Revenue share vs profit share"),
                    use_container_width=True)
    c3, c4 = st.columns(2)
    c3.plotly_chart(px.bar(dm, x="Division", y="Gross_Margin_%", color="Division", title="Gross margin by division (%)"),
                    use_container_width=True)
    c4.plotly_chart(px.box(pm, x="Division", y="Gross_Margin_%", points="all", hover_name="Product Name",
                           title="Margin distribution across products in each division"), use_container_width=True)
    trend = monthly_trend(df, "Division")
    st.plotly_chart(px.line(trend, x="Month", y="Gross_Margin_%", color="Division", title="Monthly gross margin by division"),
                    use_container_width=True)
    st.dataframe(dm.round(2), use_container_width=True, hide_index=True)

# ---------------- Tab 3 ----------------
with tab3:
    sc = px.scatter(pm, x="Sales", y="Cost", color="Margin_Risk_Flag", size="Units", hover_name="Product Name",
                    log_x=True, log_y=True, title="Cost vs sales (points above the dashed line sell below cost)")
    mx = float(max(pm["Sales"].max(), pm["Cost"].max()))
    sc.add_trace(go.Scatter(x=[1, mx], y=[1, mx], mode="lines", line=dict(dash="dash", color="grey"), name="Break-even"))
    st.plotly_chart(sc, use_container_width=True)
    c1, c2 = st.columns(2)
    unit = pm.melt(id_vars="Product Name", value_vars=["Price_per_Unit", "Cost_per_Unit"], var_name="Metric", value_name="USD")
    c1.plotly_chart(px.bar(unit, x="Product Name", y="USD", color="Metric", barmode="group", log_y=True,
                           title="Unit price vs unit cost (log scale)"), use_container_width=True)
    c2.plotly_chart(px.bar(pm.sort_values("Margin_Volatility", ascending=False).dropna(subset=["Margin_Volatility"]),
                           x="Product Name", y="Margin_Volatility", title="Margin volatility (std-dev of monthly margin, pp)"),
                    use_container_width=True)
    st.subheader("Margin risk flags")
    flags = pm[pm["Margin_Risk_Flag"] != "OK"][["Product Name", "Division", "Gross_Margin_%", "Cost_per_Unit",
                                                "Price_per_Unit", "Profit_Contribution_%", "Margin_Risk_Flag"]].round(2)
    if flags.empty:
        st.success("No products fall below the selected margin threshold.")
    else:
        st.dataframe(flags, use_container_width=True, hide_index=True)

# ---------------- Tab 4 ----------------
with tab4:
    ps = pareto_summary(pm)
    k = st.columns(4)
    k[0].metric("Products for 80% of revenue", f"{ps['revenue']['products']} of {len(pm)}")
    k[1].metric("Products for 80% of profit", f"{ps['profit']['products']} of {len(pm)}")
    k[2].metric("Top product profit share", f"{ps['profit']['top1_share']:.1f}%")
    hhi = ps["hhi_profit"]
    k[3].metric("Profit HHI", f"{hhi:,.0f}", help="<1500 diversified, 1500-2500 moderate, >2500 concentrated")
    c1, c2 = st.columns(2)
    for col, name, area in [("Sales", "Revenue", c1), ("Gross_Profit", "Profit", c2)]:
        p = pareto(pm, col)
        f = go.Figure()
        f.add_bar(x=p["Product Name"], y=p[col], name=name, marker_color="#95a5a6")
        f.add_scatter(x=p["Product Name"], y=p["Cum_%"], name="Cumulative %", yaxis="y2", mode="lines+markers")
        f.update_layout(title=f"Pareto - {name}", yaxis2=dict(overlaying="y", side="right", range=[0, 105], title="Cumulative %"),
                        xaxis_tickangle=-45, legend=dict(orientation="h"))
        f.add_hline(y=80, line_dash="dash", yref="y2")
        area.plotly_chart(f, use_container_width=True)
    div_share = pm.groupby("Division")["Profit_Contribution_%"].sum().max()
    fac = pm.groupby("Factory")["Profit_Contribution_%"].sum().sort_values(ascending=False)
    st.subheader("Dependency indicators")
    st.write(f"- Largest division supplies **{div_share:.1f}%** of gross profit.")
    st.write(f"- Largest factory by profit: **{fac.index[0]}** ({fac.iloc[0]:.1f}% of profit).")
    st.plotly_chart(px.bar(fac.reset_index(), x="Factory", y="Profit_Contribution_%", title="Profit share by factory (%)"),
                    use_container_width=True)

# ---------------- Tab 5 ----------------
with tab5:
    st.subheader("Cleaning log")
    st.dataframe(pd.DataFrame(clean_log, columns=["Step", "Value"]), hide_index=True)
    st.markdown("""
**KPIs** — Gross margin = GP ÷ Sales · Profit/unit = GP ÷ Units · Revenue/Profit contribution = product ÷ total ·
Margin volatility = std-dev of monthly margin (products with < 6 active months are left blank).

**Segments** — sales cut-off is the median product sales; margin cut-off is the sidebar threshold.

**Flags** — below threshold and tiny profit share (< 1%) → portfolio review (or discontinuation if margin < half the threshold);
cost ≥ 50% of sales → cost renegotiation / repricing; otherwise pricing review.
""")
