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


def extract_athlete_and_country(cell_text):
    """Extract athlete name and country from cell like 'Franjo von Allmen  Switzerland'"""
    if not cell_text or cell_text == 'nan' or len(cell_text) < 3:
        return None, None

    cell_text = str(cell_text).strip()
    cell_lower = cell_text.lower()

    # Check for full country name at the end of the text
    for country_name, noc in COUNTRY_TO_NOC.items():
        if country_name in cell_lower:
            idx = cell_lower.rfind(country_name)  # Use rfind for last occurrence
            athlete = cell_text[:idx].strip()
            # Clean up athlete name
            athlete = re.sub(r'\s+', ' ', athlete).strip()
            if athlete and len(athlete) > 1:
                return athlete, noc

    return None, None


def fetch_medal_events():
    """Fetch ALL medal events from the comprehensive Wikipedia page."""
    events_by_noc = {}

    print("Fetching medal events from comprehensive Wikipedia page...")

    try:
        response = requests.get(MEDAL_WINNERS_URL, headers=HEADERS, timeout=20)
        response.raise_for_status()
        tables = pd.read_html(io.StringIO(response.text))

        print(f"  Found {len(tables)} tables on page")

        for table_idx, table in enumerate(tables):
            # Check if this table has the right structure
            cols = [str(c).lower() for c in table.columns]
            if 'event' not in cols or 'gold' not in cols:
                continue

            # Get sport info from our mapping
            sport_info = TABLE_TO_SPORT.get(table_idx)
            if not sport_info:
                # Try to infer from table content or skip
                continue

            sport_name, gender_prefix = sport_info

            # Process each row
            for _, row in table.iterrows():
                event_raw = str(row.get('Event', ''))
                if not event_raw or event_raw == 'nan':
                    continue

                # Clean event name
                event_name = event_raw.replace(' details', '').replace('details', '').strip()
                if not event_name or event_name.lower() == 'event':
                    continue

                # Build full event name with sport
                if gender_prefix:
                    full_event = f"{gender_prefix} {sport_name}: {event_name}"
                else:
                    full_event = f"{sport_name}: {event_name}"

                # Process each medal column
                for medal_type in ['Gold', 'Silver', 'Bronze']:
                    cell = str(row.get(medal_type, ''))
                    if not cell or cell == 'nan' or cell == 'NaN':
                        continue

                    athlete, noc = extract_athlete_and_country(cell)

                    if noc and athlete:
                        if noc not in events_by_noc:
                            events_by_noc[noc] = []

                        events_by_noc[noc].append({
                            "event": full_event,
                            "athlete": athlete,
                            "medal": medal_type.lower(),
                            "url": MEDAL_WINNERS_URL
                        })

        print(f"Fetched medal events for {len(events_by_noc)} countries")

    except Exception as e:
        print(f"  Error fetching medal events: {e}")

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
