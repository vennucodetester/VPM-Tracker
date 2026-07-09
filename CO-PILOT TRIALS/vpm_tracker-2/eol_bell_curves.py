import argparse
import os
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from scipy import stats

DATA_FILE = os.path.join(os.path.dirname(__file__), "SAVE FILES", "Run test data start to 4-27-26.xlsx")
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "eol_output")

BOM_MAP = {"CRS0000675": "LT", "CRS0000674": "MT"}

MEASUREMENT_COLS = [
    ("RunTestSuctionTubeTemp", "Suction Tube Temp"),
    ("RunTestEvapInletRetBendATemp", "Evap Inlet Ret Bend A Temp"),
    ("RunTestEvapInletRetBendBTemp", "Evap Inlet Ret Bend B Temp"),
    ("RunTestEvapOutletAirTemp", "Evap Outlet Air Temp"),
    ("RunTestEvap_B_OutletAirTemp", "Evap B Outlet Air Temp"),
    ("RunTestInletOutletAirTempDelta", "Inlet/Outlet Air Temp Delta"),
    ("RunTestInletOutlet_B_AirTempDelta", "Inlet/Outlet B Air Temp Delta"),
    ("RunTestAmbientTemperature", "Ambient Temperature"),
    ("RunTestVoltageStartup", "Startup Voltage"),
    ("RunTestFinalVoltage", "Final Voltage"),
    ("RunTestCurrentStartup", "Startup Current"),
    ("RunTestFinalCurrent", "Final Current"),
]


def load_data():
    df = pd.read_excel(DATA_FILE, engine="openpyxl")
    df["UnitType"] = df["BomNo"].map(BOM_MAP)
    df["TestDate"] = pd.to_datetime(df["TestDate"], errors="coerce")
    return df


def filter_data(df, unit_type=None, result=None, date_start=None, date_end=None):
    mask = pd.Series(True, index=df.index)
    if unit_type:
        mask &= df["UnitType"] == unit_type
    if result:
        mask &= df["OverallPassFail"].str.upper() == result.upper()
    if date_start:
        mask &= df["TestDate"] >= pd.to_datetime(date_start)
    if date_end:
        mask &= df["TestDate"] <= pd.to_datetime(date_end)
    return df[mask].copy()


def plot_bell_curve(ax, series, title, sigma_threshold):
    clean = pd.to_numeric(series, errors="coerce").dropna()
    clean = clean[clean != 0]
    if len(clean) < 5:
        ax.set_title(f"{title}\n(insufficient data: n={len(clean)})", fontsize=9)
        ax.set_visible(True)
        return None
    mu, sigma = clean.mean(), clean.std()
    n = len(clean)
    outlier_count = (np.abs(clean - mu) > sigma_threshold * sigma).sum()
    ax.hist(clean, bins=30, density=True, alpha=0.6, color="steelblue", edgecolor="white")
    x = np.linspace(clean.min() - sigma, clean.max() + sigma, 200)
    ax.plot(x, stats.norm.pdf(x, mu, sigma), "r-", lw=2)
    for k, style in [(2, "--"), (3, ":")]:
        ax.axvline(mu - k * sigma, color="orange", ls=style, lw=1)
        ax.axvline(mu + k * sigma, color="orange", ls=style, lw=1)
    ax.axvline(mu, color="red", ls="-", lw=1, alpha=0.5)
    ax.set_title(f"{title}\nμ={mu:.2f}  σ={sigma:.2f}  n={n}  outliers({sigma_threshold}σ)={outlier_count}", fontsize=8)
    ax.tick_params(labelsize=7)
    return {"col": title, "mean": mu, "std": sigma, "n": n, "outliers": outlier_count}


def identify_outliers(df, col_name, col_label, sigma_threshold):
    series = pd.to_numeric(df[col_name], errors="coerce")
    clean_mask = series.notna() & (series != 0)
    clean = series[clean_mask]
    if len(clean) < 5:
        return pd.DataFrame()
    mu, sigma = clean.mean(), clean.std()
    if sigma == 0:
        return pd.DataFrame()
    z = (series - mu) / sigma
    outlier_mask = clean_mask & (np.abs(z) > sigma_threshold)
    if not outlier_mask.any():
        return pd.DataFrame()
    out = df.loc[outlier_mask, ["SerialNo", "BomNo", "TestDate", "OverallPassFail"]].copy()
    out["Measurement"] = col_label
    out["Value"] = series[outlier_mask]
    out["Z_Score"] = z[outlier_mask].round(2)
    return out


def generate_report(df, unit_type, sigma_threshold):
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    fig, axes = plt.subplots(4, 3, figsize=(16, 14))
    fig.suptitle(f"EOL Bell Curves — {unit_type} Unit", fontsize=14, fontweight="bold")
    stats_rows = []
    all_outliers = []

    for i, (col, label) in enumerate(MEASUREMENT_COLS):
        ax = axes[i // 3][i % 3]
        if col not in df.columns:
            ax.set_title(f"{label}\n(column not found)", fontsize=9)
            continue
        result = plot_bell_curve(ax, df[col], label, sigma_threshold)
        if result:
            stats_rows.append(result)
        outliers = identify_outliers(df, col, label, sigma_threshold)
        if not outliers.empty:
            all_outliers.append(outliers)

    fig.tight_layout(rect=[0, 0, 1, 0.96])
    png_path = os.path.join(OUTPUT_DIR, f"{unit_type}_bell_curves.png")
    fig.savefig(png_path, dpi=150)
    plt.close(fig)
    print(f"Saved: {png_path}")

    if all_outliers:
        outlier_df = pd.concat(all_outliers, ignore_index=True)
        csv_path = os.path.join(OUTPUT_DIR, f"{unit_type}_outliers.csv")
        outlier_df.to_csv(csv_path, index=False)
        print(f"Saved: {csv_path} ({len(outlier_df)} outlier records)")

    return stats_rows


def main():
    parser = argparse.ArgumentParser(description="EOL Test Data Bell Curve Analyzer")
    parser.add_argument("--unit", choices=["LT", "MT", "both"], default="both")
    parser.add_argument("--result", choices=["Pass", "Fail", "all"], default="all")
    parser.add_argument("--date-start", default=None)
    parser.add_argument("--date-end", default=None)
    parser.add_argument("--sigma", type=float, default=3.0)
    args = parser.parse_args()

    df = load_data()
    result_filter = None if args.result == "all" else args.result

    units = ["LT", "MT"] if args.unit == "both" else [args.unit]
    all_stats = []

    for unit in units:
        filtered = filter_data(df, unit_type=unit, result=result_filter,
                               date_start=args.date_start, date_end=args.date_end)
        print(f"\n{unit}: {len(filtered)} records after filtering")
        if len(filtered) == 0:
            print(f"  Skipping {unit} — no data")
            continue
        s = generate_report(filtered, unit, args.sigma)
        for row in s:
            row["unit"] = unit
        all_stats.extend(s)

    if all_stats:
        stats_df = pd.DataFrame(all_stats)
        stats_path = os.path.join(OUTPUT_DIR, "summary_stats.csv")
        stats_df.to_csv(stats_path, index=False)
        print(f"\nSaved: {stats_path}")


if __name__ == "__main__":
    main()
