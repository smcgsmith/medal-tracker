import json
import os
import re
import io   

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
    "South Korea": "KOR",
    "Finland": "FIN",
    "Slovakia": "SVK",
    "Belgium": "BEL",
    "Hungary": "HUN",
    "New Zealand": "NZL",
    "Australia": "AUS",
    "Slovenia": "SLO",
    "Bulgaria": "BUL",
    "Great Britain": "GBR",
    "Russia": "RUS",
}

NOC_TO_ISO = {
    "NOR": "NO",
    "USA": "US",
    "ITA": "IT",
    "JPN": "JP",
    "AUT": "AT",
    "GER": "DE",
    "CZE": "CZ",
    "FRA": "FR",
    "SWE": "SE",
    "SUI": "CH",
    "CAN": "CA",
    "NED": "NL",
    "CHN": "CN",
    "POL": "PL",
    "KOR": "KR",
    "FIN": "FI",
    "SVK": "SK",
    "BEL": "BE",
    "HUN": "HU",
    "NZL": "NZ",
    "AUS": "AU",
    "SLO": "SI",   # Slovenia
    "BUL": "BG",   # Bulgaria
    "GBR": "GB",   # Great Britain
    "RUS": "RU",   # Russia
}

WIKI_MEDAL_URL = "https://en.wikipedia.org/wiki/2026_Winter_Olympics_medal_table"

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
# Daily double config
# -----------------------------
DAILY_DOUBLE_EVENTS = [
    {
        "name": "Women's Ski Cross",
        "sport": "Freestyle skiing",
        "gender": "Women's",
        "event_keywords": ["ski cross"],
    },
    {
        "name": "Women's Luge Singles",
        "sport": "Luge",
        "event_keywords": ["women's singles"],
    },
    {
        # Explicitly short track (not long track speed skating).
        "name": "Men's 1500m Short Track Speed Skating",
        "sport": "Short track speed skating",
        "gender": "Men's",
        "event_keywords": ["1500"],
    },
    {
        "name": "Men's Alpine Slalom",
        "sport": "Alpine skiing",
        "gender": "Men's",
        "event_keywords": ["slalom"],
        "event_exact": ["slalom"],
    },
]

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


def clean_noc(value):
    if pd.isna(value):
        return ""
    return str(value).strip().upper()


def normalize_medals_df(medals_df):
    columns = ["noc", "country", "gold", "silver", "bronze", "total"]
    if medals_df is None:
        return pd.DataFrame(columns=columns)

    cleaned = medals_df.copy()
    if "noc" not in cleaned.columns:
        cleaned["noc"] = ""
    if "country" not in cleaned.columns:
        cleaned["country"] = ""

    cleaned["noc"] = cleaned["noc"].map(clean_noc)
    cleaned["country"] = cleaned["country"].fillna("").astype(str).str.strip()

    for medal_col in ["gold", "silver", "bronze", "total"]:
        if medal_col not in cleaned.columns:
            cleaned[medal_col] = 0
        cleaned[medal_col] = (
            pd.to_numeric(cleaned[medal_col], errors="coerce")
            .fillna(0)
            .astype(int)
        )

    cleaned = cleaned[cleaned["noc"] != ""].copy()
    cleaned = cleaned.sort_values(
        ["total", "gold", "silver", "bronze", "country"],
        ascending=[False, False, False, False, True],
    )
    cleaned = cleaned.drop_duplicates(subset=["noc"], keep="first")

    return cleaned[columns]


def fetch_medals():
    try:
        response = requests.get(WIKI_MEDAL_URL, headers=HEADERS, timeout=20)
        response.raise_for_status()

        #tables = pd.read_html(response.text)
        #tables = pd.read_html(response.text, flavor="bs4")
        tables = pd.read_html(io.StringIO(response.text))

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
        # medal_table = medal_table[
        #     ~medal_table.iloc[:, 0].astype(str).str.contains("total", case=False, na=False)
        # ]
        medal_table = medal_table[
            ~medal_table.iloc[:, 0].astype(str).str.contains("total", case=False, na=False)
        ].copy()

        # Extract country name from NOC column
        country_col = None
        for col in medal_table.columns:
            if "noc" in col:
                country_col = col
                break

        if country_col is None:
            raise ValueError("NOC column not found")

        # medal_table["country"] = (
        #     medal_table[country_col]
        #     .astype(str)
        #     .str.replace(r"\*+", "", regex=True)
        #     .str.strip()
        # )

        # Map to NOC codes
        # medal_table["noc"] = medal_table["country"].map(COUNTRY_TO_NOC)

        medal_table.loc[:, "country"] = (
            medal_table[country_col]
            .astype(str)
            .str.replace(r"\*+", "", regex=True)
            .str.strip()
        )

        medal_table.loc[:, "noc"] = medal_table["country"].map(COUNTRY_TO_NOC)

        medals_df = normalize_medals_df(
            medal_table[["noc", "country", "gold", "silver", "bronze", "total"]].copy()
        )

        medals_df.to_csv(MEDALS_CACHE_FILE, index=False)
        print("Fetched medals from Wikipedia")
        return medals_df

    except Exception as e:
        print("Wikipedia fetch failed:", e)
        raise

# Import medal events fetchers from separate module
from medal_events import fetch_medal_events, fetch_medal_winner_rows

# -----------------------------
# Fetch daily double medals
# -----------------------------
def normalize_text(value):
    return re.sub(r"\s+", " ", str(value).strip().lower())


def canonical_text(value):
    return re.sub(r"[^a-z0-9]+", "", normalize_text(value))


def matches_daily_double(winner_row, event_config):
    sport = canonical_text(winner_row.get("sport", ""))
    gender = canonical_text(winner_row.get("gender", ""))
    event_name = canonical_text(winner_row.get("event", ""))

    required_sport = canonical_text(event_config.get("sport", ""))
    required_gender = canonical_text(event_config.get("gender", ""))
    required_keywords = [
        canonical_text(keyword) for keyword in event_config.get("event_keywords", [])
    ]
    required_exclude_keywords = [
        canonical_text(keyword)
        for keyword in event_config.get("event_exclude_keywords", [])
    ]
    required_exact = [
        canonical_text(exact_name) for exact_name in event_config.get("event_exact", [])
    ]

    if required_sport and sport != required_sport:
        return False
    if required_gender and gender != required_gender:
        return False

    required_keywords = [keyword for keyword in required_keywords if keyword]
    required_exclude_keywords = [
        keyword for keyword in required_exclude_keywords if keyword
    ]
    required_exact = [exact_name for exact_name in required_exact if exact_name]

    if required_exact and event_name not in required_exact:
        return False
    if any(keyword in event_name for keyword in required_exclude_keywords):
        return False

    return all(keyword in event_name for keyword in required_keywords)


def fetch_daily_doubles(winner_rows):
    rows = []
    results_by_event = {
        event["name"]: {"event": event["name"], "results": []}
        for event in DAILY_DOUBLE_EVENTS
    }
    seen_rows = {event["name"]: set() for event in DAILY_DOUBLE_EVENTS}

    for winner_row in winner_rows:
        medal = normalize_text(winner_row.get("medal", ""))
        noc = clean_noc(winner_row.get("noc"))

        if medal not in ["gold", "silver", "bronze"] or not noc:
            continue

        for event in DAILY_DOUBLE_EVENTS:
            if not matches_daily_double(winner_row, event):
                continue

            row_key = (
                canonical_text(winner_row.get("sport", "")),
                canonical_text(winner_row.get("gender", "")),
                canonical_text(winner_row.get("event", "")),
                medal,
                noc,
            )
            if row_key in seen_rows[event["name"]]:
                break
            seen_rows[event["name"]].add(row_key)

            rows.append(
                {
                    "noc": noc,
                    "gold": int(medal == "gold"),
                    "silver": int(medal == "silver"),
                    "bronze": int(medal == "bronze"),
                }
            )
            results_by_event[event["name"]]["results"].append((medal.title(), noc))
            break

    results = []
    for event in DAILY_DOUBLE_EVENTS:
        event_result = results_by_event[event["name"]]
        if not event_result["results"]:
            event_result["scheduled"] = True
        results.append(event_result)

    df = pd.DataFrame(rows)
    if df.empty:
        return df, results

    df = df.groupby("noc").sum().reset_index()
    return df, results

def load_medals_cache():
    if MEDALS_CACHE_FILE.exists():
        return normalize_medals_df(pd.read_csv(MEDALS_CACHE_FILE))
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

    for col in ["friend", "country_1", "country_2"]:
        friends_df[col] = friends_df[col].fillna("").astype(str).str.strip()
    friends_df["noc_1"] = friends_df["noc_1"].map(clean_noc)
    friends_df["noc_2"] = friends_df["noc_2"].map(clean_noc)

    friends_df = friends_df[friends_df["friend"] != ""].copy()
    return friends_df


def build_friend_scores(friends_df, medals_df, double_df):
    friends_df = friends_df.copy()
    friends_df["noc_1"] = friends_df["noc_1"].map(clean_noc)
    friends_df["noc_2"] = friends_df["noc_2"].map(clean_noc)

    medals_df = normalize_medals_df(medals_df).rename(columns={"country": "country_name"})
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
    merged["points_1"] = merged["points_1"].astype(float)
    merged["points_2"] = merged["points_2"].astype(float)

    merged.loc[merged["noc_1"] == "NOR", "points_1"] *= 0.5
    merged.loc[merged["noc_2"] == "NOR", "points_2"] *= 0.5


    # merged["points_total"] = merged["points_1"] + merged["points_2"]
    # -----------------------------
    # Daily double scoring
    # -----------------------------
    if not double_df.empty:
        dd = double_df.set_index("noc")

        def get_dd_points(noc):
            if noc in dd.index:
                r = dd.loc[noc]
                # `double_df` contains only medals from daily-double events.
                # This adds a bonus equal to normal medal points, so the final
                # effect is exactly 2x for those medals:
                # gold 3+3=6, silver 2+2=4, bronze 1+1=2.
                # print(f"Calculating daily double points for {noc}: {r['gold']}G, {r['silver']}S, {r['bronze']}B")
                # print(f"  Base points: {r['gold'] * SCORING_WEIGHTS['gold']} + {r['silver'] * SCORING_WEIGHTS['silver']} + {r['bronze'] * SCORING_WEIGHTS['bronze']}")
                # print(f"  {noc} daily double points: {(r['gold'] * SCORING_WEIGHTS['gold'] + r['silver'] * SCORING_WEIGHTS['silver'] + r['bronze'] * SCORING_WEIGHTS['bronze']) * 2}")
                points = (
                    r["gold"] * SCORING_WEIGHTS["gold"]
                    + r["silver"] * SCORING_WEIGHTS["silver"]
                    + r["bronze"] * SCORING_WEIGHTS["bronze"]
                )
                if noc == "NOR":
                    points *= 0.5
                return points
            return 0

        merged["daily_double"] = (
            merged["noc_1"].apply(get_dd_points)
            + merged["noc_2"].apply(get_dd_points)
        )
    else:
        merged["daily_double"] = 0

    merged["points_total"] = (
        merged["points_1"] + merged["points_2"] + merged["daily_double"]
    )

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
  <title>Milano-Cortina 2026 Fantasy Country Draft</title>
  <style>
    * {{ box-sizing: border-box; }}
    body {{
      font-family: 'Helvetica Neue', Arial, sans-serif;
      margin: 0;
      padding: 32px;
      color: #333;
      background: #f8f9fa;
      min-height: 100vh;
    }}
    h1 {{
      margin-bottom: 4px;
      color: #1a1a1a;
      text-align: center;
      font-size: 2.5em;
    }}
    .subtitle {{
      color: #666;
      margin-bottom: 24px;
      text-align: center;
    }}
    .container {{ max-width: 1000px; margin: 0 auto; }}
    .section {{ margin-top: 32px; }}

    /* Animation Intro */
    #intro-overlay {{
      position: fixed;
      top: 0;
      left: 0;
      width: 100%;
      height: 100%;
      background: #f8f9fa;
      z-index: 1000;
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;
      transition: opacity 0.5s ease;
    }}
    #intro-overlay.hidden {{
      opacity: 0;
      pointer-events: none;
    }}

    .reveal-card {{
      background: #fff;
      border-radius: 20px;
      padding: 40px;
      text-align: center;
      opacity: 0;
      transform: translateY(50px) scale(0.9);
      transition: all 0.6s cubic-bezier(0.175, 0.885, 0.32, 1.275);
      box-shadow: 0 10px 40px rgba(0,0,0,0.1);
      min-width: 400px;
      border: 1px solid #e0e0e0;
    }}
    .reveal-card.visible {{
      opacity: 1;
      transform: translateY(0) scale(1);
    }}
    .reveal-card .rank-badge {{
      font-size: 4em;
      font-weight: bold;
      color: #ffd700;
      margin-bottom: 10px;
    }}
    .reveal-card .profile-pic {{
      width: 150px;
      height: 150px;
      border-radius: 50%;
      object-fit: cover;
      border: 4px solid #ffd700;
      margin: 20px auto;
      display: block;
      box-shadow: 0 5px 20px rgba(0,0,0,0.1);
    }}
    .reveal-card .name {{
      font-size: 2.5em;
      color: #1a1a1a;
      font-weight: bold;
      margin: 10px 0;
    }}
    .reveal-card .points {{
      font-size: 1.8em;
      color: #2563eb;
      font-weight: bold;
    }}
    .reveal-card .countries {{
      color: #666;
      font-size: 1.2em;
      margin-top: 15px;
    }}
    .reveal-card .medal-count {{
      font-size: 1.5em;
      margin-top: 10px;
    }}

    /* Podium animation for top 3 */
    .reveal-card.gold {{
      background: #fffbeb;
      border: 2px solid #ffd700;
    }}
    .reveal-card.silver {{
      background: #f8f9fa;
      border: 2px solid #c0c0c0;
    }}
    .reveal-card.bronze {{
      background: #fef3e7;
      border: 2px solid #cd7f32;
    }}

    /* Scoreboard */
    .scoreboard-container {{
      background: #fff;
      border-radius: 20px;
      padding: 30px;
      box-shadow: 0 4px 20px rgba(0,0,0,0.08);
    }}
    .player-row {{
      display: flex;
      align-items: center;
      padding: 15px 20px;
      margin: 10px 0;
      background: #f8f9fa;
      border-radius: 15px;
      cursor: pointer;
      transition: all 0.3s ease;
      opacity: 0;
      transform: translateX(-50px);
      border: 1px solid #e9ecef;
    }}
    .player-row.visible {{
      opacity: 1;
      transform: translateX(0);
    }}
    .player-row:hover {{
      background: #fff;
      transform: scale(1.02);
      box-shadow: 0 5px 20px rgba(0,0,0,0.1);
    }}
    .player-row.rank-1 {{ border-left: 4px solid #ffd700; background: #fffbeb; }}
    .player-row.rank-2 {{ border-left: 4px solid #c0c0c0; background: #f8f9fa; }}
    .player-row.rank-3 {{ border-left: 4px solid #cd7f32; background: #fef3e7; }}

    .rank-num {{
      font-size: 1.8em;
      font-weight: bold;
      color: #333;
      width: 50px;
      text-align: center;
    }}
    .player-pic {{
      width: 60px;
      height: 60px;
      border-radius: 50%;
      object-fit: cover;
      margin: 0 20px;
      border: 3px solid #e9ecef;
    }}
    .player-info {{
      flex: 1;
    }}
    .player-name {{
      font-size: 1.4em;
      font-weight: bold;
      color: #1a1a1a;
    }}
    .stacked-medals {{
      font-size: 0.7em;
      margin-left: 8px;
      letter-spacing: 2px;
    }}
    .player-countries {{
      color: #666;
      font-size: 0.95em;
      margin-top: 5px;
    }}
    .player-points {{
      font-size: 1.8em;
      font-weight: bold;
      color: #2563eb;
      text-align: right;
      min-width: 80px;
    }}

    /* Events dropdown */
    .events-panel {{
      display: none;
      background: #fff;
      border-radius: 10px;
      padding: 20px;
      margin: 10px 0 10px 70px;
      animation: slideDown 0.3s ease;
      border: 1px solid #e9ecef;
      box-shadow: 0 4px 15px rgba(0,0,0,0.05);
    }}
    .events-panel.open {{
      display: block;
    }}
    @keyframes slideDown {{
      from {{ opacity: 0; transform: translateY(-10px); }}
      to {{ opacity: 1; transform: translateY(0); }}
    }}
    .events-panel h4 {{
      color: #333;
      margin: 0 0 15px 0;
    }}
    .event-link {{
      display: block;
      color: #2563eb;
      text-decoration: none;
      padding: 8px 0;
      border-bottom: 1px solid #e9ecef;
      transition: all 0.2s;
    }}
    .event-link:hover {{
      color: #1d4ed8;
      padding-left: 5px;
      background: #f8f9fa;
    }}
    .event-link .medal-icon {{
      margin-right: 10px;
    }}
    .country-events {{
      margin-bottom: 15px;
    }}
    .country-events h5 {{
      color: #333;
      margin: 0 0 10px 0;
      font-size: 1em;
      border-bottom: 1px solid #e9ecef;
      padding-bottom: 5px;
    }}
    .event-item {{
      display: inline-block;
    }}
    .athlete-name {{
      color: #888;
      font-size: 0.85em;
      font-style: italic;
    }}

    /* Skip button */
    #skip-btn {{
      position: fixed;
      bottom: 30px;
      right: 30px;
      background: #fff;
      color: #333;
      border: 1px solid #ddd;
      padding: 12px 24px;
      border-radius: 30px;
      cursor: pointer;
      font-size: 1em;
      z-index: 1001;
      transition: all 0.3s;
      box-shadow: 0 2px 10px rgba(0,0,0,0.1);
    }}
    #skip-btn:hover {{
      background: #f8f9fa;
      box-shadow: 0 4px 15px rgba(0,0,0,0.15);
    }}

    /* Daily Double */
    .daily-double {{
      background: #fff;
      border-radius: 15px;
      padding: 20px;
      margin-top: 30px;
      box-shadow: 0 4px 20px rgba(0,0,0,0.08);
    }}
    .daily-double h2 {{
      color: #333;
      margin-bottom: 20px;
    }}
    .daily-double table {{
      width: 100%;
      color: #333;
    }}
    .daily-double th {{
      text-align: left;
      padding: 10px;
      color: #666;
      border-bottom: 1px solid #e9ecef;
    }}
    .daily-double td {{
      padding: 10px;
      border-bottom: 1px solid #f0f0f0;
    }}

    /* Mobile Responsive */
    @media (max-width: 768px) {{
      body {{
        padding: 16px;
      }}
      h1 {{
        font-size: 1.6em;
      }}
      .reveal-card {{
        min-width: 90vw;
        padding: 25px;
      }}
      .reveal-card .rank-badge {{
        font-size: 2.5em;
      }}
      .reveal-card .profile-pic {{
        width: 100px;
        height: 100px;
      }}
      .reveal-card .name {{
        font-size: 1.8em;
      }}
      .reveal-card .points {{
        font-size: 1.4em;
      }}
      .scoreboard-container {{
        padding: 15px;
      }}
      .player-row {{
        flex-wrap: wrap;
        padding: 12px;
      }}
      .rank-num {{
        font-size: 1.3em;
        width: 35px;
      }}
      .player-pic {{
        width: 45px;
        height: 45px;
        margin: 0 10px;
      }}
      .player-info {{
        flex: 1;
        min-width: 0;
      }}
      .player-name {{
        font-size: 1.1em;
      }}
      .player-countries {{
        font-size: 0.8em;
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
      }}
      .player-points {{
        font-size: 1.3em;
        min-width: 60px;
      }}
      .events-panel {{
        margin: 10px 0;
        padding: 15px;
      }}
      .event-item {{
        font-size: 0.9em;
      }}
      #skip-btn {{
        bottom: 15px;
        right: 15px;
        padding: 10px 18px;
        font-size: 0.9em;
      }}
      .daily-double {{
        padding: 15px;
      }}
      .daily-double th, .daily-double td {{
        padding: 8px 5px;
        font-size: 0.9em;
      }}
    }}

    @media (max-width: 480px) {{
      h1 {{
        font-size: 1.3em;
      }}
      .reveal-card {{
        padding: 20px;
      }}
      .reveal-card .rank-badge {{
        font-size: 2em;
      }}
      .reveal-card .profile-pic {{
        width: 80px;
        height: 80px;
      }}
      .reveal-card .name {{
        font-size: 1.4em;
      }}
      .player-row {{
        padding: 10px;
      }}
      .rank-num {{
        font-size: 1.1em;
        width: 30px;
      }}
      .player-pic {{
        width: 40px;
        height: 40px;
        margin: 0 8px;
      }}
      .player-name {{
        font-size: 1em;
      }}
      .player-points {{
        font-size: 1.1em;
        min-width: 50px;
      }}
    }}
  </style>
</head>
<body>
  <div id=\"intro-overlay\">
    <div class=\"reveal-card\" id=\"reveal-card\">
      <div class=\"rank-badge\" id=\"reveal-rank\"></div>
      <img class=\"profile-pic\" id=\"reveal-pic\" src=\"\" alt=\"\">
      <div class=\"name\" id=\"reveal-name\"></div>
      <div class=\"points\" id=\"reveal-points\"></div>
      <div class=\"countries\" id=\"reveal-countries\"></div>
      <div class=\"medal-count\" id=\"reveal-medals\"></div>
    </div>
  </div>

  <button id=\"skip-btn\" onclick=\"skipAnimation()\">Skip Animation</button>

  <div class=\"container\">
    <h1>Milano-Cortina 2026 Fantasy Country Draft</h1>
    <div class=\"subtitle\">Updated: {last_updated}</div>

    <div class=\"section\">
      <div class=\"scoreboard-container\">
        {table_html}
      </div>
    </div>

  </div>

  <script>
    const players = window.playerData || [];
    let currentIndex = players.length - 1;
    let animationSkipped = false;

    function showRevealCard(player, index) {{
      const card = document.getElementById('reveal-card');
      const rankClasses = ['', 'gold', 'silver', 'bronze'];

      card.className = 'reveal-card ' + (rankClasses[player.rank] || '');

      document.getElementById('reveal-rank').textContent = '#' + player.rank;
      document.getElementById('reveal-pic').src = player.pic;
      document.getElementById('reveal-name').textContent = player.name;
      document.getElementById('reveal-points').textContent = player.points + ' pts';
      document.getElementById('reveal-countries').innerHTML = player.countries;
      document.getElementById('reveal-medals').innerHTML = player.medals;

      card.classList.remove('visible');
      setTimeout(() => card.classList.add('visible'), 50);
    }}

    function revealNext() {{
      if (animationSkipped || currentIndex < 0) {{
        finishAnimation();
        return;
      }}

      showRevealCard(players[currentIndex], currentIndex);
      currentIndex--;

      const delay = currentIndex >= 0 && currentIndex < 3 ? 2500 : 1500;
      setTimeout(revealNext, delay);
    }}

    function finishAnimation() {{
      document.getElementById('intro-overlay').classList.add('hidden');
      document.getElementById('skip-btn').style.display = 'none';

      // Animate scoreboard rows
      const rows = document.querySelectorAll('.player-row');
      rows.forEach((row, i) => {{
        setTimeout(() => row.classList.add('visible'), i * 100);
      }});
    }}

    function skipAnimation() {{
      animationSkipped = true;
      finishAnimation();
    }}

    function toggleEvents(friendName) {{
      const panel = document.getElementById('events-' + friendName.toLowerCase());
      if (panel) {{
        panel.classList.toggle('open');
      }}
    }}

    // Start animation after page load
    setTimeout(revealNext, 500);
  </script>
</body>
</html>"""

def build_daily_double_table(results):
    rows = []

    for event in results:
        if event.get("scheduled"):
            result_text = '<span style="color: #888;">Scheduled for later</span>'
        else:
            result_text = ", ".join(
                [f"{m} – {c}" for m, c in event["results"]]
            )

        rows.append(f"""
        <tr>
            <td>{event['event']}</td>
            <td>{result_text}</td>
        </tr>
        """)

    return f"""
    <div class="daily-double">
      <h2>Daily Double Events</h2>
      <table>
        <thead>
            <tr>
                <th>Event</th>
                <th>Result</th>
            </tr>
        </thead>
        <tbody>
            {''.join(rows)}
        </tbody>
      </table>
    </div>
    """


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
    winner_rows = fetch_medal_winner_rows()
    double_df, double_results = fetch_daily_doubles(winner_rows)
    scored_df = build_friend_scores(friends_df, medals_df, double_df)

    # Fetch medal events dynamically
    EVENT_DATA = fetch_medal_events(winner_rows)
    print(f"Loaded events for {len(EVENT_DATA)} countries")

    def noc_to_flag(noc):
        if not isinstance(noc, str):
            return ""
        iso = NOC_TO_ISO.get(noc)
        if not iso:
            return ""
        return "".join(chr(127397 + ord(c)) for c in iso)

    def build_pretty_table(df):
        rows = []
        player_data = []
        medal_icons = {"gold": "🥇", "silver": "🥈", "bronze": "🥉"}

        for i, row in df.reset_index(drop=True).iterrows():
            rank = i + 1
            friend_name = row['friend']
            friend_lower = friend_name.lower()

            flag1 = noc_to_flag(row["noc_1"])
            flag2 = noc_to_flag(row["noc_2"])

            # Get event data for both countries
            events1 = EVENT_DATA.get(row["noc_1"], [])
            events2 = EVENT_DATA.get(row["noc_2"], [])

            # Build stacked medals display (🥇🥇🥈🥈🥉 etc)
            total_gold = int(row['gold_1'] + row['gold_2'])
            total_silver = int(row['silver_1'] + row['silver_2'])
            total_bronze = int(row['bronze_1'] + row['bronze_2'])
            stacked_medals = "🥇" * total_gold + "🥈" * total_silver + "🥉" * total_bronze
            if not stacked_medals:
                stacked_medals = "—"

            # Build country display - handle single country (Team USA) vs dual countries
            has_second_country = pd.notna(row['noc_2']) and str(row['noc_2']).strip() != ''
            if has_second_country:
                countries_display = f"{flag1} {row['country_1']} &amp; {flag2} {row['country_2']}"
            else:
                countries_display = f"{flag1} {row['country_1']}"

            # Build events panel with individual event links and athlete names
            events_html = ""

            # Country 1 events
            if events1:
                events_html += f'<div class="country-events"><h5>{flag1} {row["country_1"]}</h5>'
                for evt in events1:
                    medal_icon = medal_icons.get(evt["medal"], "🏅")
                    athlete = evt.get("athlete", "")
                    athlete_str = f' <span class="athlete-name">({athlete})</span>' if athlete else ""
                    events_html += f'<a href="{evt["url"]}" target="_blank" class="event-link"><span class="event-item">{medal_icon} {evt["event"]}{athlete_str}</span></a>'
                events_html += '</div>'

            # Country 2 events
            if events2:
                events_html += f'<div class="country-events"><h5>{flag2} {row["country_2"]}</h5>'
                for evt in events2:
                    medal_icon = medal_icons.get(evt["medal"], "🏅")
                    athlete = evt.get("athlete", "")
                    athlete_str = f' <span class="athlete-name">({athlete})</span>' if athlete else ""
                    events_html += f'<a href="{evt["url"]}" target="_blank" class="event-link"><span class="event-item">{medal_icon} {evt["event"]}{athlete_str}</span></a>'
                events_html += '</div>'

            if not events_html:
                events_html = '<span style="color: #888;">No medals yet - keep cheering! 📣</span>'

            rank_class = f"rank-{rank}" if rank <= 3 else ""

            rows.append(f"""
            <div class="player-row {rank_class}" onclick="toggleEvents('{friend_lower}')">
                <div class="rank-num">#{rank}</div>
                <img class="player-pic" src="pics/{friend_lower}.png" alt="{friend_name}">
                <div class="player-info">
                    <div class="player-name">{friend_name} <span class="stacked-medals">{stacked_medals}</span></div>
                    <div class="player-countries">{countries_display}</div>
                </div>
                <div class="player-points">{row['points_total']}</div>
            </div>
            <div class="events-panel" id="events-{friend_lower}">
                <h4>🏆 Medal Events</h4>
                {events_html}
            </div>
            """)

            # Build player data for animation
            player_data.append({
                "rank": rank,
                "name": friend_name,
                "pic": f"pics/{friend_lower}.png",
                "points": row['points_total'],
                "countries": countries_display,
                "medals": stacked_medals
            })

        # Generate JavaScript data
        import json
        player_json = json.dumps(player_data)

        return f"""
        <script>window.playerData = {player_json};</script>
        {''.join(rows)}
        """
    table_html = build_pretty_table(scored_df)

    plot = make_plot(scored_df)
    plot_html = plot.to_html(full_html=False, include_plotlyjs="cdn")

    last_updated = pd.Timestamp.utcnow().strftime("%Y-%m-%d %H:%M UTC")

    daily_double_html = build_daily_double_table(double_results)

    OUTPUT_FILE.write_text(
        build_html(table_html + daily_double_html, plot_html, last_updated)
    )



    print(f"Updated {OUTPUT_FILE}")
