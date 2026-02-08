import requests
import pandas as pd
import plotly.graph_objects as go
from pathlib import Path

# -----------------------------
# Config
# -----------------------------
API_URL = "https://api.olympics.com/medals/v1/games/OWG2026/medals"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)",
    "Accept": "application/json"
}

OUTDIR = Path.home() / "scripts/olympics"
OUTDIR.mkdir(parents=True, exist_ok=True)
OUTFILE = OUTDIR / "medal_totals.html"

BAR_COLOR = "#2E86AB"  # all bars same color

# ISO NOC → flag CDN
FLAG_URL = "https://flagcdn.com/w40/{code}.png"


# -----------------------------
# Fetch medals
# -----------------------------
def fetch_medals():
    r = requests.get(API_URL, headers=HEADERS, timeout=20)
    r.raise_for_status()
    data = r.json()

    rows = []
    for c in data:
        rows.append({
            "noc": c["noc"],
            "country": c["country"],
            "gold": c.get("gold", 0),
            "silver": c.get("silver", 0),
            "bronze": c.get("bronze", 0),
            "total": c.get("total", 0)
        })

    df = pd.DataFrame(rows).sort_values("total", ascending=True)
    return df


# -----------------------------
# Build interactive plot
# -----------------------------
def make_plot(df):
    fig = go.Figure()

    fig.add_trace(go.Bar(
        x=df["total"],
        y=df["country"],
        orientation="h",
        marker=dict(color=BAR_COLOR),
        hovertemplate=(
            "<b>%{y}</b><br>"
            "Total: %{x}<br><br>"
            "🥇 Gold: %{customdata[0]}<br>"
            "🥈 Silver: %{customdata[1]}<br>"
            "🥉 Bronze: %{customdata[2]}"
            "<extra></extra>"
        ),
        customdata=df[["gold", "silver", "bronze"]].values
    ))

    # Add flags at end of bars
    for _, row in df.iterrows():
        fig.add_layout_image(
            dict(
                source=FLAG_URL.format(code=row["noc"][:2].lower()),
                x=row["total"],
                y=row["country"],
                xref="x",
                yref="y",
                xanchor="left",
                yanchor="middle",
                sizex=0.6,
                sizey=0.6,
                layer="above"
            )
        )

    fig.update_layout(
        title="Milano–Cortina 2026 — Total Medals by Country",
        xaxis_title="Total Medals",
        yaxis_title="",
        template="simple_white",
        height=600 + 20 * len(df),
        margin=dict(l=120, r=60, t=80, b=40),
        yaxis=dict(autorange="reversed")
    )

    return fig


# -----------------------------
# Main
# -----------------------------
if __name__ == "__main__":
    df = fetch_medals()
    fig = make_plot(df)
    fig.write_html(OUTFILE, include_plotlyjs="cdn")
    print(f"Updated {OUTFILE}")
