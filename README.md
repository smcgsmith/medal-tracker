# Fantasy Olympics Medal Tracker

This repo generates a static HTML page that tracks your fantasy draft points based on real medal counts. You can publish the `docs/` folder with GitHub Pages so everyone can view it.

## How it works

- Medal totals are pulled from the official Olympics API.
- If the API is unavailable, the script falls back to `data/medals_cache.csv`.
- Friends are mapped to countries via `data/friends.csv`.
- Points are calculated using the scoring weights in `olympic_test.py`.
- A table and a Plotly chart are exported to `docs/index.html`.

## Update the data

1. Edit `data/friends.csv` with your friends and their countries.
2. Run the script:

```bash
python olympic_test.py
```

That will regenerate `docs/index.html`.

If you need to run the script offline, update `data/medals_cache.csv` with the latest medal totals and rerun the script. The cache is automatically refreshed whenever the API request succeeds.

## Publish with GitHub Pages

1. Push your changes to GitHub.
2. In the repo settings, enable GitHub Pages:
   - **Source**: `main` branch
   - **Folder**: `/docs`
3. Your site will be available at the GitHub Pages URL.

## Customize scoring

Adjust the `SCORING_WEIGHTS` dictionary in `olympic_test.py` to change points per medal type.
