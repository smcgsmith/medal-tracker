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
    "Accept": "application/json",
}

REPO_ROOT = Path(__file__).resolve().parent
DATA_DIR = REPO_ROOT / "data"
FRIENDS_FILE = DATA_DIR / "friends.csv"
MEDALS_CACHE_FILE = DATA_DIR / "medals_cache.csv"

OUTPUT_DIR = REPO_ROOT / "docs"
OUTPUT_FILE = OUTPUT_DIR / "index.html"

SCORING_WEIGHTS = {
    "gold": 3,
    "silver": 2,
    "bronze": 1,
}

BAR_COLOR = "#2E86AB"  # all bars same color

# ISO NOC → flag CDN
FLAG_URL = "https://flagcdn.com/w40/{code}.png"


# -----------------------------
# Fetch medals
# -----------------------------
def fetch_medals():
    response = requests.get(API_URL, headers=HEADERS, timeout=20)
    response.raise_for_status()
    data = response.json()

    rows = []
    for country in data:
        rows.append(
            {
                "noc": country["noc"],
                "country": country["country"],
                "gold": country.get("gold", 0),
                "silver": country.get("silver", 0),
                "bronze": country.get("bronze", 0),
                "total": country.get("total", 0),
            }
        )

    medals_df = pd.DataFrame(rows)
    medals_df.to_csv(MEDALS_CACHE_FILE, index=False)
    return medals_df


def load_medals_cache():
    if MEDALS_CACHE_FILE.exists():
        return pd.read_csv(MEDALS_CACHE_FILE)
    return None


# -----------------------------
# Friends data
# -----------------------------
def load_friends():
    return pd.read_csv(FRIENDS_FILE)


def build_friend_scores(friends_df, medals_df):
    merged = friends_df.merge(medals_df, how="left", on="noc")
    merged[["gold", "silver", "bronze", "total"]] = (
        merged[["gold", "silver", "bronze", "total"]].fillna(0).astype(int)
    )
    merged["points"] = (
        merged["gold"] * SCORING_WEIGHTS["gold"]
        + merged["silver"] * SCORING_WEIGHTS["silver"]
        + merged["bronze"] * SCORING_WEIGHTS["bronze"]
    )
    return merged.sort_values(["points", "total"], ascending=False)


# -----------------------------
# Build interactive plot
# -----------------------------
def make_plot(df):
    fig = go.Figure()

    fig.add_trace(
        go.Bar(
            x=df["points"],
            y=df["friend"],
            orientation="h",
            marker=dict(color=BAR_COLOR),
            hovertemplate=(
                "<b>%{y}</b><br>"
                "%{customdata[0]} (%{customdata[1]})<br>"
                "Points: %{x}<br><br>"
                "🥇 Gold: %{customdata[2]}<br>"
                "🥈 Silver: %{customdata[3]}<br>"
                "🥉 Bronze: %{customdata[4]}<br>"
                "Total: %{customdata[5]}"
                "<extra></extra>"
            ),
            customdata=df[["country", "noc", "gold", "silver", "bronze", "total"]].values,
        )
    )

    # Add flags at end of bars
    for _, row in df.iterrows():
        fig.add_layout_image(
            dict(
                source=FLAG_URL.format(code=row["noc"][:2].lower()),
                x=row["points"],
                y=row["friend"],
                xref="x",
                yref="y",
                xanchor="left",
                yanchor="middle",
                sizex=0.6,
                sizey=0.6,
                layer="above",
            )
        )

    fig.update_layout(
        title="Fantasy Draft — Points by Friend",
        xaxis_title="Points",
        yaxis_title="",
        template="simple_white",
        height=400 + 28 * len(df),
        margin=dict(l=120, r=60, t=80, b=40),
        yaxis=dict(autorange="reversed"),
    )

    return fig


# -----------------------------
# HTML output
# -----------------------------
def build_html(table_html, plot_html, last_updated):
    return f"""<!doctype html>
<html lang=\"en\">
<head>
  <meta charset=\"utf-8\">
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">
  <title>Fantasy Olympics Medal Draft</title>
  <style>
    body {{ font-family: 'Helvetica Neue', Arial, sans-serif; margin: 32px; color: #1a1a1a; }}
    h1 {{ margin-bottom: 4px; }}
    .subtitle {{ color: #555; margin-bottom: 24px; }}
    table {{ border-collapse: collapse; width: 100%; margin-top: 16px; }}
    th, td {{ border-bottom: 1px solid #e0e0e0; padding: 10px 12px; text-align: left; }}
    th {{ background: #f5f5f5; }}
    .container {{ max-width: 1000px; margin: 0 auto; }}
    .section {{ margin-top: 32px; }}
  </style>
</head>
<body>
  <div class=\"container\">
    <h1>Fantasy Olympics Medal Draft</h1>
    <div class=\"subtitle\">Updated: {last_updated}</div>

    <div class=\"section\">
      <h2>Points Table</h2>
      {table_html}
    </div>

    <div class=\"section\">
      <h2>Points by Friend</h2>
      {plot_html}
    </div>
  </div>
</body>
</html>"""


# -----------------------------
# Main
# -----------------------------
if __name__ == "__main__":
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    try:
        medals_df = fetch_medals()
    except requests.exceptions.RequestException:
        medals_df = load_medals_cache()
        if medals_df is None:
            raise
        print("Warning: using cached medal data (network request failed).")
    friends_df = load_friends()
    scored_df = build_friend_scores(friends_df, medals_df)

    table_html = scored_df[
        ["friend", "country", "noc", "points", "gold", "silver", "bronze", "total"]
    ].to_html(index=False, classes="dataframe")

    plot = make_plot(scored_df)
    plot_html = plot.to_html(full_html=False, include_plotlyjs="cdn")

    last_updated = pd.Timestamp.utcnow().strftime("%Y-%m-%d %H:%M UTC")
    OUTPUT_FILE.write_text(build_html(table_html, plot_html, last_updated))

    print(f"Updated {OUTPUT_FILE}")
