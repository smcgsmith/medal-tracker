import json
import os
import re

import pandas as pd
import plotly.graph_objects as go
import requests
from pathlib import Path

# -----------------------------
# Config
# -----------------------------
DEFAULT_API_URLS = [
    "https://api.olympics.com/medals/v1/games/OWG2026/medals",
    "https://api.olympics.com/medals/v1/games/MCO2026/medals",
    "https://olympics.com/en/olympic-games/milano-cortina-2026/medals",
]

COUNTRY_TO_NOC = {
    "Norway": "NOR",
    "United States": "USA",
    "Italy": "ITA",
    "Japan": "JPN",
    "Austria": "AUT",
    "Germany": "GER",
    "Czech Republic": "CZE",
    "France": "FRA",
    "Sweden": "SWE",
    "Switzerland": "SUI",
    "Canada": "CAN",
    "Netherlands": "NED",
    "China": "CHN",
    "Poland": "POL",
    "Korea": "KOR",
    "Finland": "FIN",
    "Slovakia": "SVK",
    "Belgium": "BEL",
    "Hungary": "HUN",
    "New Zealand": "NZL",
    "Australia": "AUS",
}


WIKI_MEDAL_URL = "https://en.wikipedia.org/wiki/2026_Winter_Olympics#Medal_table"

ENV_API_URLS = os.environ.get("MEDALS_API_URLS")
API_URLS = (
    [url.strip() for url in ENV_API_URLS.split(",") if url.strip()]
    if ENV_API_URLS
    else DEFAULT_API_URLS
)

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
def extract_medal_rows(payload):
    if isinstance(payload, list):
        if payload and all(isinstance(item, dict) for item in payload):
            medal_keys = {"gold", "silver", "bronze", "total", "medals"}
            if any("noc" in item or "organisation" in item for item in payload) and any(
                medal_keys.intersection(item.keys()) for item in payload
            ):
                return payload
        for item in payload:
            found = extract_medal_rows(item)
            if found:
                return found
    if isinstance(payload, dict):
        for value in payload.values():
            found = extract_medal_rows(value)
            if found:
                return found
    return []


def normalize_medal_row(row):
    medals = row.get("medals") if isinstance(row.get("medals"), dict) else row
    return {
        "noc": row.get("noc")
        or row.get("organisation")
        or row.get("countryCode")
        or row.get("code"),
        "country": row.get("country")
        or row.get("description")
        or row.get("name")
        or row.get("countryName")
        or row.get("organisation")
        or row.get("noc"),
        "gold": medals.get("gold")
        or medals.get("goldMedals")
        or medals.get("gold_medals")
        or 0,
        "silver": medals.get("silver")
        or medals.get("silverMedals")
        or medals.get("silver_medals")
        or 0,
        "bronze": medals.get("bronze")
        or medals.get("bronzeMedals")
        or medals.get("bronze_medals")
        or 0,
        "total": medals.get("total")
        or medals.get("totalMedals")
        or medals.get("total_medals")
        or 0,
    }


def parse_medals_from_html(html):
    match = re.search(
        r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>',
        html,
        re.DOTALL,
    )
    if not match:
        return []
    payload = json.loads(match.group(1))
    return extract_medal_rows(payload)


def parse_medals_payload(payload):
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        rows = extract_medal_rows(payload)
        if rows:
            return rows
    return []

def fetch_medals():
    try:
        response = requests.get(WIKI_MEDAL_URL, headers=HEADERS, timeout=20)
        response.raise_for_status()

        tables = pd.read_html(response.text)

        medal_table = None
        for table in tables:
            cols = [str(c).lower() for c in table.columns]
            if "gold" in cols and "silver" in cols and "bronze" in cols:
                medal_table = table
                break

        if medal_table is None:
            raise ValueError("Medal table not found on Wikipedia page")

        # Normalize column names
        medal_table.columns = [str(c).lower() for c in medal_table.columns]

        # Remove totals row
        medal_table = medal_table[
            ~medal_table.iloc[:, 0].astype(str).str.contains("total", case=False, na=False)
        ]

        # Extract country name from NOC column
        country_col = None
        for col in medal_table.columns:
            if "noc" in col:
                country_col = col
                break

        if country_col is None:
            raise ValueError("NOC column not found")

        medal_table["country"] = (
            medal_table[country_col]
            .astype(str)
            .str.replace(r"\*+", "", regex=True)
            .str.strip()
        )

        # Map to NOC codes
        medal_table["noc"] = medal_table["country"].map(COUNTRY_TO_NOC)

        medals_df = medal_table[
            ["noc", "country", "gold", "silver", "bronze", "total"]
        ].copy()

        medals_df[["gold", "silver", "bronze", "total"]] = (
            medals_df[["gold", "silver", "bronze", "total"]]
            .fillna(0)
            .astype(int)
        )

        medals_df.to_csv(MEDALS_CACHE_FILE, index=False)
        print("Fetched medals from Wikipedia")
        return medals_df

    except Exception as e:
        print("Wikipedia fetch failed:", e)
        raise

def load_medals_cache():
    if MEDALS_CACHE_FILE.exists():
        return pd.read_csv(MEDALS_CACHE_FILE)
    return None


# -----------------------------
# Friends data
# -----------------------------
def load_friends():
    friends_df = pd.read_csv(FRIENDS_FILE)
    if "noc" in friends_df.columns and "noc_1" not in friends_df.columns:
        friends_df = friends_df.rename(columns={"noc": "noc_1", "country": "country_1"})
        friends_df["noc_2"] = ""
        friends_df["country_2"] = ""

    if "country_1" not in friends_df.columns:
        friends_df["country_1"] = ""
    if "country_2" not in friends_df.columns:
        friends_df["country_2"] = ""

    required_columns = {"friend", "noc_1", "noc_2"}
    missing = required_columns - set(friends_df.columns)
    if missing:
        raise ValueError(f"friends.csv missing columns: {', '.join(sorted(missing))}")
    return friends_df


def build_friend_scores(friends_df, medals_df):
    medals_df = medals_df.rename(columns={"country": "country_name"})
    medals_1 = medals_df.add_suffix("_1")
    medals_2 = medals_df.add_suffix("_2")

    merged = friends_df.merge(medals_1, how="left", on="noc_1").merge(
        medals_2, how="left", on="noc_2"
    )

    merged["country_1"] = merged["country_1"].fillna(merged["country_name_1"])
    merged["country_2"] = merged["country_2"].fillna(merged["country_name_2"])

    medal_columns = [
        "gold_1",
        "silver_1",
        "bronze_1",
        "total_1",
        "gold_2",
        "silver_2",
        "bronze_2",
        "total_2",
    ]
    merged[medal_columns] = merged[medal_columns].fillna(0).astype(int)

    merged["points_1"] = (
        merged["gold_1"] * SCORING_WEIGHTS["gold"]
        + merged["silver_1"] * SCORING_WEIGHTS["silver"]
        + merged["bronze_1"] * SCORING_WEIGHTS["bronze"]
    )
    merged["points_2"] = (
        merged["gold_2"] * SCORING_WEIGHTS["gold"]
        + merged["silver_2"] * SCORING_WEIGHTS["silver"]
        + merged["bronze_2"] * SCORING_WEIGHTS["bronze"]
    )

    # ---------------------------------
    # Norway penalty: halve only Norway points
    # ---------------------------------
    merged.loc[merged["noc_1"] == "NOR", "points_1"] *= 0.5
    merged.loc[merged["noc_2"] == "NOR", "points_2"] *= 0.5

    merged["points_total"] = merged["points_1"] + merged["points_2"]
    merged["total_medals"] = merged["total_1"] + merged["total_2"]

    return merged.sort_values(["points_total", "total_medals"], ascending=False)


# -----------------------------
# Build interactive plot
# -----------------------------
def make_plot(df):
    fig = go.Figure()

    fig.add_trace(
        go.Bar(
            x=df["points_total"],
            y=df["friend"],
            orientation="h",
            marker=dict(color=BAR_COLOR),
            hovertemplate=(
                "<b>%{y}</b><br>"
                "%{customdata[0]} (%{customdata[1]})<br>"
                "🥇 %{customdata[2]} | 🥈 %{customdata[3]} | 🥉 %{customdata[4]} | Total: %{customdata[5]}<br><br>"
                "%{customdata[6]} (%{customdata[7]})<br>"
                "Points: %{x}<br><br>"
                "🥇 %{customdata[8]} | 🥈 %{customdata[9]} | 🥉 %{customdata[10]} | Total: %{customdata[11]}"
                "<extra></extra>"
            ),
            customdata=df[
                [
                    "country_1",
                    "noc_1",
                    "gold_1",
                    "silver_1",
                    "bronze_1",
                    "total_1",
                    "country_2",
                    "noc_2",
                    "gold_2",
                    "silver_2",
                    "bronze_2",
                    "total_2",
                ]
            ].values,
        )
    )

    # Add flags at end of bars
    for _, row in df.iterrows():
        if isinstance(row.get("noc_1"), str) and row["noc_1"]:
            fig.add_layout_image(
                dict(
                    source=FLAG_URL.format(code=row["noc_1"][:2].lower()),
                    x=row["points_total"],
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
        title="Milano-Cortina 2026 Fantasy Country Draft",
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
    .leaderboard {{
        display: flex;
        justify-content: space-around;
        background: #f7f7f7;
        padding: 16px;
        border-radius: 10px;
        margin-bottom: 24px;
        font-size: 1.2em;
    }}

    .leader {{
        text-align: center;
    }}

    .medal {{
        font-size: 1.5em;
        margin-right: 6px;
    }}

    .scoreboard {{
        width: 100%;
        border-collapse: collapse;
        margin-top: 20px;
    }}

    .scoreboard th, .scoreboard td {{
        padding: 12px;
        border-bottom: 1px solid #e0e0e0;
    }}

    .country-block div {{
        margin: 2px 0;
    }}
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

    def noc_to_flag(noc):
        if not isinstance(noc, str) or len(noc) != 3:
            return ""
        # Convert ISO country code to emoji flag
        code = noc[:2].upper()
        return "".join(chr(127397 + ord(c)) for c in code)

    def build_pretty_table(df):
        rows = []
        for i, row in df.reset_index(drop=True).iterrows():
            rank = i + 1

            flag1 = noc_to_flag(row["noc_1"])
            flag2 = noc_to_flag(row["noc_2"])

            countries_html = f"""
            <div class="country-block">
                <div>{flag1} {row['country_1']} — 🥇{row['gold_1']} 🥈{row['silver_1']} 🥉{row['bronze_1']}</div>
                <div>{flag2} {row['country_2']} — 🥇{row['gold_2']} 🥈{row['silver_2']} 🥉{row['bronze_2']}</div>
            </div>
            """

            rows.append(f"""
            <tr>
                <td>{rank}</td>
                <td><strong>{row['friend']}</strong></td>
                <td>{countries_html}</td>
                <td><strong>{row['points_total']}</strong></td>
            </tr>
            """)

        return f"""
        <table class="scoreboard">
            <thead>
                <tr>
                    <th>Rank</th>
                    <th>Friend</th>
                    <th>Countries</th>
                    <th>Points</th>
                </tr>
            </thead>
            <tbody>
                {''.join(rows)}
            </tbody>
        </table>
        """
    def build_leader_banner(df):
        top3 = df.head(3).reset_index(drop=True)
        medals = ["🥇", "🥈", "🥉"]

        rows = []
        for i, row in top3.iterrows():
            rows.append(f"""
            <div class="leader">
                <span class="medal">{medals[i]}</span>
                <span class="name">{row['friend']}</span>
                <span class="points">{row['points_total']} pts</span>
            </div>
            """)

        return f"""
        <div class="leaderboard">
            {''.join(rows)}
        </div>
        """

    table_html = build_pretty_table(scored_df)
    leader_html = build_leader_banner(scored_df)

    plot = make_plot(scored_df)
    plot_html = plot.to_html(full_html=False, include_plotlyjs="cdn")

    last_updated = pd.Timestamp.utcnow().strftime("%Y-%m-%d %H:%M UTC")
    OUTPUT_FILE.write_text(
        build_html(leader_html + table_html, plot_html, last_updated)
    )


    print(f"Updated {OUTPUT_FILE}")
