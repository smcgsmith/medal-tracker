import json
import os
import re
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import requests

# -----------------------------
# Config
# -----------------------------
WIKI_MEDAL_URL = "https://en.wikipedia.org/wiki/2026_Winter_Olympics#Medal_table"

# Daily double events
DAILY_DOUBLE_EVENTS = [
    {
        "name": "Women's Ski Cross",
        "url": "https://en.wikipedia.org/wiki/Freestyle_skiing_at_the_2026_Winter_Olympics_%E2%80%93_Women%27s_ski_cross",
    },
    {
        "name": "Women's Luge Singles",
        "url": "https://en.wikipedia.org/wiki/Luge_at_the_2026_Winter_Olympics_%E2%80%93_Women%27s_singles",
    },
    {
        "name": "Men's 1500m Speed Skating",
        "url": "https://en.wikipedia.org/wiki/Speed_skating_at_the_2026_Winter_Olympics_%E2%80%93_Men%27s_1500_metres",
    },
    {
        "name": "Men's Alpine Slalom",
        "url": "https://en.wikipedia.org/wiki/Alpine_skiing_at_the_2026_Winter_Olympics_%E2%80%93_Men%27s_slalom",
    },
]

SCORING_WEIGHTS = {"gold": 3, "silver": 2, "bronze": 1}

HEADERS = {"User-Agent": "Mozilla/5.0"}

REPO_ROOT = Path(__file__).resolve().parent
DATA_DIR = REPO_ROOT / "data"
FRIENDS_FILE = DATA_DIR / "friends.csv"
OUTPUT_DIR = REPO_ROOT / "docs"
OUTPUT_FILE = OUTPUT_DIR / "index.html"

# -----------------------------
# Medal fetch
# -----------------------------
def fetch_overall_medals():
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
        raise ValueError("Medal table not found")

    medal_table.columns = [str(c).lower() for c in medal_table.columns]
    medal_table = medal_table[
        ~medal_table.iloc[:, 0].astype(str).str.contains("total", case=False, na=False)
    ]

    medal_table["country"] = medal_table.iloc[:, 1]
    medal_table["noc"] = medal_table["noc"]

    df = medal_table[["noc", "country", "gold", "silver", "bronze"]].copy()
    df[["gold", "silver", "bronze"]] = df[
        ["gold", "silver", "bronze"]
    ].fillna(0).astype(int)

    return df


# -----------------------------
# Daily double events
# -----------------------------
def fetch_daily_doubles():
    rows = []
    results = []

    for event in DAILY_DOUBLE_EVENTS:
        try:
            r = requests.get(event["url"], headers=HEADERS, timeout=20)
            r.raise_for_status()
            tables = pd.read_html(r.text)

            medal_table = tables[0]
            medal_table.columns = [str(c).lower() for c in medal_table.columns]

            event_result = {"event": event["name"], "results": []}

            for _, row in medal_table.iterrows():
                noc = row.get("noc")
                medal = str(row.get("medal", "")).lower()

                if medal in ["gold", "silver", "bronze"]:
                    rows.append(
                        {
                            "noc": noc,
                            "gold": int(medal == "gold"),
                            "silver": int(medal == "silver"),
                            "bronze": int(medal == "bronze"),
                        }
                    )
                    event_result["results"].append((medal.title(), noc))

            if not event_result["results"]:
                event_result["scheduled"] = True

            results.append(event_result)

        except Exception:
            results.append(
                {"event": event["name"], "scheduled": True}
            )

    df = pd.DataFrame(rows)
    if df.empty:
        return df, results

    df = df.groupby("noc").sum().reset_index()
    return df, results


# -----------------------------
# Friends
# -----------------------------
def load_friends():
    return pd.read_csv(FRIENDS_FILE)


def build_friend_scores(friends_df, medals_df, double_df):
    medals_df = medals_df.rename(columns={"country": "country_name"})
    medals_1 = medals_df.add_suffix("_1")
    medals_2 = medals_df.add_suffix("_2")

    merged = friends_df.merge(medals_1, how="left", on="noc_1").merge(
        medals_2, how="left", on="noc_2"
    )

    merged = merged.fillna(0)

    merged["points_1"] = (
        merged["gold_1"] * 3 + merged["silver_1"] * 2 + merged["bronze_1"]
    )
    merged["points_2"] = (
        merged["gold_2"] * 3 + merged["silver_2"] * 2 + merged["bronze_2"]
    )

    # Daily doubles
    if not double_df.empty:
        dd = double_df.set_index("noc")

        def get_dd(noc):
            if noc in dd.index:
                r = dd.loc[noc]
                return r["gold"] * 3 + r["silver"] * 2 + r["bronze"]
            return 0

        merged["daily_double"] = (
            merged["noc_1"].apply(get_dd) + merged["noc_2"].apply(get_dd)
        )
    else:
        merged["daily_double"] = 0

    merged["points_total"] = (
        merged["points_1"] + merged["points_2"] + merged["daily_double"]
    )

    return merged.sort_values("points_total", ascending=False)


# -----------------------------
# HTML builders
# -----------------------------
def build_daily_double_html(results):
    rows = []

    for event in results:
        if event.get("scheduled"):
            rows.append(
                f"<tr><td>{event['event']}</td><td>Scheduled for later</td></tr>"
            )
        else:
            medals = ", ".join(
                [f"{m} – {c}" for m, c in event["results"]]
            )
            rows.append(
                f"<tr><td>{event['event']}</td><td>{medals}</td></tr>"
            )

    return f"""
    <h2>Daily Double Events</h2>
    <table>
        <tr><th>Event</th><th>Result</th></tr>
        {''.join(rows)}
    </table>
    """


def build_html(table_html, doubles_html):
    return f"""
    <html>
    <body>
    <h1>Fantasy Olympic Leaderboard</h1>
    {table_html}
    {doubles_html}
    </body>
    </html>
    """


# -----------------------------
# Main
# -----------------------------
if __name__ == "__main__":
    OUTPUT_DIR.mkdir(exist_ok=True)
    DATA_DIR.mkdir(exist_ok=True)

    medals_df = fetch_overall_medals()
    double_df, double_results = fetch_daily_doubles()
    friends_df = load_friends()

    scored = build_friend_scores(friends_df, medals_df, double_df)

    table_html = scored[["friend", "points_total"]].to_html(index=False)
    doubles_html = build_daily_double_html(double_results)

    OUTPUT_FILE.write_text(build_html(table_html, doubles_html))
    print("Dashboard updated.")
