"""
Medal Events Fetcher
Fetches ALL medal events from the comprehensive Wikipedia medal winners page.
"""

import re
import io
import requests
import pandas as pd

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)",
    "Accept": "text/html",
}

# Country name to NOC mapping (comprehensive list)
COUNTRY_TO_NOC = {
    "norway": "NOR", "united states": "USA", "italy": "ITA", "japan": "JPN",
    "austria": "AUT", "germany": "GER", "czech republic": "CZE", "czechia": "CZE",
    "france": "FRA", "sweden": "SWE", "switzerland": "SUI", "canada": "CAN",
    "netherlands": "NED", "the netherlands": "NED", "holland": "NED",
    "china": "CHN", "poland": "POL", "south korea": "KOR", "korea": "KOR",
    "finland": "FIN", "new zealand": "NZL", "slovenia": "SLO", "australia": "AUS",
    "great britain": "GBR", "united kingdom": "GBR", "britain": "GBR",
    "belgium": "BEL", "hungary": "HUN", "slovakia": "SVK", "bulgaria": "BUL",
    "latvia": "LAT", "russia": "RUS", "roc": "RUS", "spain": "ESP",
    "ukraine": "UKR", "croatia": "CRO", "estonia": "EST", "lithuania": "LTU",
    "romania": "ROU", "kazakhstan": "KAZ", "brazil": "BRA", "denmark": "DEN",
    "monaco": "MON", "andorra": "AND", "liechtenstein": "LIE",
}

COUNTRY_NAMES_BY_LENGTH = sorted(COUNTRY_TO_NOC.keys(), key=len, reverse=True)

# Map table indices to sport names (based on actual page structure)
TABLE_TO_SPORT = {
    2: ("Alpine skiing", "Men's"),
    3: ("Alpine skiing", "Women's"),
    4: ("Biathlon", "Men's"),
    5: ("Biathlon", "Women's"),
    6: ("Biathlon", "Mixed"),
    7: ("Bobsleigh", ""),
    8: ("Cross-country skiing", "Men's"),
    9: ("Cross-country skiing", "Women's"),
    10: ("Curling", ""),
    11: ("Figure skating", ""),
    12: ("Freestyle skiing", "Men's"),
    13: ("Freestyle skiing", "Women's"),
    14: ("Freestyle skiing", "Mixed"),
    15: ("Ice hockey", ""),
    16: ("Luge", ""),
    17: ("Nordic combined", ""),
    18: ("Short track speed skating", "Men's"),
    19: ("Short track speed skating", "Women's"),
    20: ("Short track speed skating", "Mixed"),
    21: ("Skeleton", ""),
    22: ("Ski jumping", "Men's"),
    23: ("Ski jumping", "Women's"),
    24: ("Ski jumping", "Mixed"),
    25: ("Snowboarding", "Men's"),
    26: ("Snowboarding", "Men's"),  # Big air
    27: ("Snowboarding", "Women's"),  # Big air
    28: ("Snowboarding", "Mixed"),  # Team snowboard cross
    29: ("Speed skating", "Men's"),
    30: ("Speed skating", "Women's"),
}

# Wikipedia page with ALL medal winners
MEDAL_WINNERS_URL = "https://en.wikipedia.org/wiki/List_of_2026_Winter_Olympics_medal_winners"


def clean_event_name(event_raw):
    event_name = str(event_raw).replace(" details", "").replace("details", "").strip()
    return re.sub(r"\s+", " ", event_name)


def extract_athlete_and_country(cell_text):
    """Extract athlete name and country from cell like 'Franjo von Allmen  Switzerland'"""
    if not cell_text or cell_text == 'nan' or len(cell_text) < 3:
        return None, None

    cell_text = re.sub(r"\[[^\]]+\]", "", str(cell_text))
    cell_text = re.sub(r"\s+", " ", cell_text).strip()
    cell_lower = cell_text.lower()

    # Prefer a strict country suffix match (longest names first).
    for country_name in COUNTRY_NAMES_BY_LENGTH:
        if not cell_lower.endswith(country_name):
            continue
        noc = COUNTRY_TO_NOC[country_name]
        athlete = cell_text[:-len(country_name)].strip(" ,;:-")
        athlete = re.sub(r'\s+', ' ', athlete).strip()
        return athlete, noc

    # Fallback: last whole-word country mention.
    for country_name in COUNTRY_NAMES_BY_LENGTH:
        match = None
        for m in re.finditer(rf"\b{re.escape(country_name)}\b", cell_lower):
            match = m
        if not match:
            continue
        noc = COUNTRY_TO_NOC[country_name]
        athlete = cell_text[:match.start()].strip(" ,;:-")
        athlete = re.sub(r'\s+', ' ', athlete).strip()
        return athlete, noc

    return None, None


def fetch_medal_winner_rows():
    """Fetch medal-winning rows from the comprehensive Wikipedia page."""
    winner_rows = []
    seen_rows = set()
    print("Fetching medal events from comprehensive Wikipedia page...")

    try:
        response = requests.get(MEDAL_WINNERS_URL, headers=HEADERS, timeout=20)
        response.raise_for_status()
        tables = pd.read_html(io.StringIO(response.text))

        print(f"  Found {len(tables)} tables on page")

        for table_idx, table in enumerate(tables):
            cols = [str(c).lower() for c in table.columns]
            if 'event' not in cols or 'gold' not in cols:
                continue

            sport_info = TABLE_TO_SPORT.get(table_idx)
            if not sport_info:
                continue

            sport_name, gender_prefix = sport_info

            for _, row in table.iterrows():
                event_raw = str(row.get('Event', ''))
                if not event_raw or event_raw == 'nan':
                    continue

                event_name = clean_event_name(event_raw)
                if not event_name or event_name.lower() == 'event':
                    continue

                if gender_prefix:
                    full_event = f"{gender_prefix} {sport_name}: {event_name}"
                else:
                    full_event = f"{sport_name}: {event_name}"

                for medal_type in ['Gold', 'Silver', 'Bronze']:
                    cell = str(row.get(medal_type, ''))
                    if not cell or cell == 'nan' or cell == 'NaN':
                        continue

                    athlete, noc = extract_athlete_and_country(cell)
                    if not noc:
                        continue

                    row_data = {
                        "sport": sport_name,
                        "gender": gender_prefix,
                        "event": event_name,
                        "full_event": full_event,
                        "athlete": athlete or "",
                        "medal": medal_type.lower(),
                        "noc": noc,
                        "url": MEDAL_WINNERS_URL,
                    }
                    dedupe_key = (
                        row_data["sport"].lower(),
                        row_data["gender"].lower(),
                        row_data["event"].lower(),
                        row_data["medal"],
                        row_data["noc"],
                        row_data["athlete"].lower(),
                    )
                    if dedupe_key in seen_rows:
                        continue
                    seen_rows.add(dedupe_key)
                    winner_rows.append(row_data)

        print(f"Fetched {len(winner_rows)} medal-winning entries")

    except Exception as e:
        print(f"  Error fetching medal events: {e}")
        return []

    return winner_rows


def fetch_medal_events(winner_rows=None):
    """Fetch ALL medal events grouped by country NOC."""
    events_by_noc = {}
    seen_by_noc = {}

    if winner_rows is None:
        winner_rows = fetch_medal_winner_rows()

    for row in winner_rows:
        noc = row.get("noc")
        if not noc:
            continue

        if noc not in events_by_noc:
            events_by_noc[noc] = []
            seen_by_noc[noc] = set()

        event_data = {
            "event": row["full_event"],
            "athlete": row.get("athlete", ""),
            "medal": row["medal"],
            "url": row["url"],
        }
        dedupe_key = (
            event_data["event"].lower(),
            event_data["medal"],
            event_data["athlete"].lower(),
        )
        if dedupe_key in seen_by_noc[noc]:
            continue
        seen_by_noc[noc].add(dedupe_key)
        events_by_noc[noc].append(event_data)

    print(f"Fetched medal events for {len(events_by_noc)} countries")

    return events_by_noc


if __name__ == "__main__":
    # Test the fetcher
    events = fetch_medal_events()

    # Show summary
    total = sum(len(evts) for evts in events.values())
    print(f"\nTotal events found: {total}")

    # Show sample for a few countries
    for noc in ['USA', 'ITA', 'NOR', 'FRA', 'GER']:
        evts = events.get(noc, [])
        if evts:
            golds = sum(1 for e in evts if e['medal'] == 'gold')
            silvers = sum(1 for e in evts if e['medal'] == 'silver')
            bronzes = sum(1 for e in evts if e['medal'] == 'bronze')
            print(f"\n{noc}: {golds}G {silvers}S {bronzes}B = {len(evts)} events")
            for e in evts[:3]:
                print(f"  {e['medal'].upper()}: {e['event']} - {e['athlete']}")
