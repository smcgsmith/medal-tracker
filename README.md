# Fantasy Olympics Medal Tracker

This repo generates a static HTML page that tracks your fantasy draft points based on real medal counts. You can publish the `docs/` folder with GitHub Pages so everyone can view it.

## How it works

- Medal totals are pulled from the official Olympics API (with fallbacks to the Olympic site HTML).
- If the API is unavailable, the script falls back to `data/medals_cache.csv`.
- Friends are mapped to countries via `data/friends.csv`.
- Points are calculated using the scoring weights in `olympic_test.py`.
- A table and a Plotly chart are exported to `docs/index.html`.

## Setup

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python olympic_test.py

## Update the data

1. Edit `data/friends.csv` with your friends and their two countries.
2. Run the script:

```bash
python olympic_test.py
```

That will regenerate `docs/index.html`.

If you need to run the script offline, update `data/medals_cache.csv` with the latest medal totals and rerun the script. The cache is automatically refreshed whenever the API request succeeds.
You can override the default medal endpoints by setting `MEDALS_API_URLS` (comma-separated URLs) before running the script.

### Friends format

`data/friends.csv` should include two countries per friend:

```csv
friend,noc_1,country_1,noc_2,country_2
Alex,USA,United States,JPN,Japan
Jamie,CAN,Canada,GBR,Great Britain
```

The script will total points across both countries.

## Publish with GitHub Pages

1. Push your changes to GitHub.
2. In the repo settings, enable GitHub Pages:
   - **Source**: `main` branch
   - **Folder**: `/docs`
3. Your site will be available at the GitHub Pages URL.

## Daily updates

This repo includes a GitHub Actions workflow that refreshes the medal data daily at 12 PM Eastern Time
(scheduled in UTC). It regenerates `docs/index.html` and pushes the update so your GitHub Pages link stays live.

## Customize scoring

Adjust the `SCORING_WEIGHTS` dictionary in `olympic_test.py` to change points per medal type.
