"""
Medal Events Fetcher
Fetches detailed medal events from Wikipedia with athlete names and full event descriptions.
"""

import re
import io
import requests
import pandas as pd

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)",
    "Accept": "application/json",
}

# Country name to NOC mapping
COUNTRY_TO_NOC = {
    "norway": "NOR", "united states": "USA", "italy": "ITA", "japan": "JPN",
    "austria": "AUT", "germany": "GER", "czech republic": "CZE", "france": "FRA",
    "sweden": "SWE", "switzerland": "SUI", "canada": "CAN", "netherlands": "NED",
    "china": "CHN", "poland": "POL", "south korea": "KOR", "finland": "FIN",
    "new zealand": "NZL", "slovenia": "SLO", "australia": "AUS", "great britain": "GBR",
    "belgium": "BEL", "hungary": "HUN", "slovakia": "SVK", "bulgaria": "BUL",
}

# Sport URL mappings
SPORT_URLS = {
    "Alpine skiing": "https://en.wikipedia.org/wiki/Alpine_skiing_at_the_2026_Winter_Olympics",
    "Biathlon": "https://en.wikipedia.org/wiki/Biathlon_at_the_2026_Winter_Olympics",
    "Bobsleigh": "https://en.wikipedia.org/wiki/Bobsleigh_at_the_2026_Winter_Olympics",
    "Cross-country skiing": "https://en.wikipedia.org/wiki/Cross-country_skiing_at_the_2026_Winter_Olympics",
    "Curling": "https://en.wikipedia.org/wiki/Curling_at_the_2026_Winter_Olympics",
    "Figure skating": "https://en.wikipedia.org/wiki/Figure_skating_at_the_2026_Winter_Olympics",
    "Freestyle skiing": "https://en.wikipedia.org/wiki/Freestyle_skiing_at_the_2026_Winter_Olympics",
    "Ice hockey": "https://en.wikipedia.org/wiki/Ice_hockey_at_the_2026_Winter_Olympics",
    "Luge": "https://en.wikipedia.org/wiki/Luge_at_the_2026_Winter_Olympics",
    "Nordic combined": "https://en.wikipedia.org/wiki/Nordic_combined_at_the_2026_Winter_Olympics",
    "Short track speed skating": "https://en.wikipedia.org/wiki/Short_track_speed_skating_at_the_2026_Winter_Olympics",
    "Skeleton": "https://en.wikipedia.org/wiki/Skeleton_at_the_2026_Winter_Olympics",
    "Ski jumping": "https://en.wikipedia.org/wiki/Ski_jumping_at_the_2026_Winter_Olympics",
    "Snowboarding": "https://en.wikipedia.org/wiki/Snowboarding_at_the_2026_Winter_Olympics",
    "Speed skating": "https://en.wikipedia.org/wiki/Speed_skating_at_the_2026_Winter_Olympics",
}


def extract_athlete_and_country(cell_text):
    """Extract athlete name and country from a cell like 'Franjo von Allmen  Switzerland'"""
    if not cell_text or cell_text == 'nan' or len(cell_text) < 3:
        return None, None

    cell_lower = cell_text.lower()

    for country_name, noc in COUNTRY_TO_NOC.items():
        if country_name in cell_lower:
            # Find where country name starts and extract athlete name
            idx = cell_lower.find(country_name)
            athlete = cell_text[:idx].strip()
            # Clean up athlete name
            athlete = re.sub(r'\s+', ' ', athlete).strip()
            return athlete, noc

    return None, None


def fetch_sport_medals(sport_name, sport_url):
    """Fetch medals from a specific sport's Wikipedia page."""
    events = []

    try:
        response = requests.get(sport_url, headers=HEADERS, timeout=15)
        response.raise_for_status()
        tables = pd.read_html(io.StringIO(response.text))

        current_gender = ""

        for table in tables:
            cols = [str(c).lower() for c in table.columns]

            # Look for medal tables with Event/Gold/Silver/Bronze columns
            if 'event' not in cols:
                continue
            if 'gold' not in cols and 'silver' not in cols:
                continue

            for _, row in table.iterrows():
                event_raw = str(row.get('Event', row.get('event', '')))
                if not event_raw or event_raw == 'nan':
                    continue

                # Skip header rows
                if 'event' in event_raw.lower() and len(event_raw) < 10:
                    continue

                # Clean event name
                event_name = event_raw.replace(' details', '').replace(' Details', '').strip()

                # Detect gender from event name
                event_lower = event_name.lower()
                if "women" in event_lower or "ladies" in event_lower:
                    gender = "Women's"
                elif "men" in event_lower and "women" not in event_lower:
                    gender = "Men's"
                elif "mixed" in event_lower or "team" in event_lower:
                    gender = ""
                else:
                    gender = current_gender  # Use previous gender context

                current_gender = gender if gender else current_gender

                # Build full event name
                if gender and gender.lower().replace("'s", "") not in event_lower:
                    full_event = f"{gender} {sport_name}: {event_name}"
                else:
                    full_event = f"{sport_name}: {event_name}"

                # Process each medal
                for medal_col in ['Gold', 'Silver', 'Bronze', 'gold', 'silver', 'bronze']:
                    cell = str(row.get(medal_col, ''))
                    athlete, noc = extract_athlete_and_country(cell)

                    if noc and athlete:
                        events.append({
                            "noc": noc,
                            "event": full_event,
                            "athlete": athlete,
                            "medal": medal_col.lower(),
                            "url": sport_url
                        })

    except Exception as e:
        print(f"  Failed to fetch {sport_name}: {e}")

    return events


def fetch_medal_events():
    """Fetch individual medal events from each sport's Wikipedia page."""
    events_by_noc = {}

    print("Fetching medal events from sport pages...")

    for sport_name, sport_url in SPORT_URLS.items():
        print(f"  Fetching {sport_name}...")
        sport_events = fetch_sport_medals(sport_name, sport_url)

        for event in sport_events:
            noc = event["noc"]
            if noc not in events_by_noc:
                events_by_noc[noc] = []

            events_by_noc[noc].append({
                "event": event["event"],
                "athlete": event["athlete"],
                "medal": event["medal"],
                "url": event["url"]
            })

    print(f"Fetched medal events for {len(events_by_noc)} countries")
    return events_by_noc


if __name__ == "__main__":
    # Test the fetcher
    events = fetch_medal_events()
    for noc, evts in list(events.items())[:3]:
        print(f"\n{noc}:")
        for e in evts[:3]:
            print(f"  {e['medal'].upper()}: {e['event']} - {e['athlete']}")
