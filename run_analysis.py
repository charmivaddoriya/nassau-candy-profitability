"""Batch run: cleaning log, tables (CSV) and figures (PNG) used in the research paper."""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd
from pathlib import Path
from src.analysis import *

OUT = Path("outputs"); FIG = OUT / "figures"; FIG.mkdir(parents=True, exist_ok=True)
df, log = load_and_clean()
pd.DataFrame(log, columns=["Step", "Value"]).to_csv(OUT / "cleaning_log.csv", index=False)
pm = classify_products(product_metrics(df))
dm = division_metrics(df)
pm.round(3).to_csv(OUT / "product_metrics.csv", index=False)
dm.round(3).to_csv(OUT / "division_metrics.csv", index=False)
ps = pareto_summary(pm)
print(log); print(pm.round(2).to_string()); print(dm.round(2).to_string()); print(ps)
print("threshold", pm.attrs["threshold"])

plt.rcParams.update({"figure.dpi": 130, "axes.spines.top": False, "axes.spines.right": False})
# 1 leaderboard
s = pm.sort_values("Gross_Margin_%")
plt.figure(figsize=(8, 5)); plt.barh(s["Product Name"], s["Gross_Margin_%"], color="#c0392b")
plt.axvline(pm.attrs["threshold"], ls="--", c="k"); plt.xlabel("Gross margin (%)"); plt.title("Product gross margin leaderboard")
plt.tight_layout(); plt.savefig(FIG / "01_margin_leaderboard.png"); plt.close()
# 2 profit contribution
s = pm.sort_values("Gross_Profit")
plt.figure(figsize=(8, 5)); plt.barh(s["Product Name"], s["Gross_Profit"], color="#2c7fb8")
plt.xlabel("Gross profit ($)"); plt.title("Total profit contribution by product"); plt.tight_layout(); plt.savefig(FIG / "02_profit_contribution.png"); plt.close()
# 3 division
fig, ax = plt.subplots(1, 2, figsize=(10, 4))
ax[0].bar(dm["Division"], dm["Revenue_Share_%"], width=.4, label="Revenue share", align="edge")
ax[0].bar(dm["Division"], dm["Profit_Share_%"], width=-.4, label="Profit share", align="edge"); ax[0].legend(); ax[0].set_title("Revenue vs profit share (%)")
ax[1].bar(dm["Division"], dm["Gross_Margin_%"], color="#27ae60"); ax[1].set_title("Gross margin by division (%)")
plt.tight_layout(); plt.savefig(FIG / "03_division.png"); plt.close()
# 4 pareto
fig, ax = plt.subplots(1, 2, figsize=(11, 4))
for a, col, t in [(ax[0], "Sales", "Revenue"), (ax[1], "Gross_Profit", "Profit")]:
    p = pareto(pm, col); a.bar(p["Rank"], p[col], color="#95a5a6"); b = a.twinx(); b.plot(p["Rank"], p["Cum_%"], "o-", c="#c0392b")
    b.axhline(80, ls="--", c="k"); b.set_ylim(0, 105); a.set_title(f"Pareto - {t}"); a.set_xlabel("Product rank")
plt.tight_layout(); plt.savefig(FIG / "04_pareto.png"); plt.close()
# 5 cost vs sales
plt.figure(figsize=(7, 5))
plt.scatter(pm["Sales"], pm["Cost"], s=60, c=["#c0392b" if x else "#2c7fb8" for x in pm["Below_Threshold"]])
for _, r in pm.iterrows(): plt.annotate(r["Product Name"].replace("Wonka Bar - ", "WB-"), (r["Sales"], r["Cost"]), fontsize=7)
plt.xscale("log"); plt.yscale("log"); plt.xlabel("Sales ($, log)"); plt.ylabel("Cost ($, log)"); plt.title("Cost vs sales (red = below margin threshold)")
plt.tight_layout(); plt.savefig(FIG / "05_cost_vs_sales.png"); plt.close()
# 6 trend
t = monthly_trend(df, "Division")
plt.figure(figsize=(9, 4))
for k, g in t.groupby("Division"): plt.plot(g["Month"], g["Gross_Margin_%"], label=k)
plt.legend(); plt.ylabel("Gross margin (%)"); plt.title("Monthly gross margin by division"); plt.tight_layout(); plt.savefig(FIG / "06_margin_trend.png"); plt.close()
