# Redraw the Lines
### Interactive Texas Congressional Redistricting Tool
**Carnegie Young Leaders Project · 2026**

A browser-based tool for exploring how congressional district boundaries affect political representation. No server required — runs entirely in your browser.

---

## What It Does

- **Draw your own map** — click or paint TX counties into any of 38 congressional districts
- **Live statistics** — seats, efficiency gap, seat-vote gap, packed/cracked districts all update instantly
- **Fairness reference** — compare your map to Iowa, Wisconsin 2011, NC 2016, and the official Texas Plan C2193
- **District detail** — population, presidential vote, racial composition, compactness score, EG contribution
- **Share** — your map compresses into a URL so anyone can open your exact layout
- **Tour** — guided 5-step walkthrough explaining packing, cracking, and the efficiency gap

## What It Looks Like

| Feature | Detail |
|---|---|
| Map | 254 TX counties → 38 districts, colored by partisan lean |
| Mode | Click (select) or Paint (drag to bulk-assign) |
| Undo/Redo | Full history stack, Ctrl+Z / Ctrl+Y |
| Efficiency Gap | Animated number, needle gauge, flashes when crossing 7% |
| Seats Curve | Live bar chart of all 38 districts sorted by partisan lean |
| Compactness | Polsby-Popper score per district |
| Share URL | LZ-string compressed, encodes only your changes |

---

## Run Locally

```bash
# No build step needed — just serve the root folder
python -m http.server 8000
# then open http://localhost:8000
```

---

## Get Real Data (Optional but Recommended)

The app ships with synthetic data that approximates Plan C2193.
For accurate numbers, run the data pipeline once:

### 1. Install Python dependencies
```bash
cd pipeline
pip install -r requirements.txt
```

### 2. Download source data (both free, no account required)

**VEST 2020 Texas precincts** (votes + demographics pre-joined)
- Go to https://dataverse.harvard.edu/dataverse/electionscience
- Search: "2020 Precinct-Level Election Results"
- Download `tx_2020.zip` → unzip into `pipeline/raw_data/vest/`

**TLC Plan C2193 districts** (official TX congressional map)
- Go to https://tlc.texas.gov/redist/data/planc2193.zip
- Unzip into `pipeline/raw_data/districts/`

### 3. Run the pipeline
```bash
python build_data.py
```

This produces:
```
data/
├── precincts.geojson     ~9,000 TX precincts with vote + demographics
├── districts.geojson     38 Plan C2193 boundaries
├── assignment.json       precinct → district lookup
└── district_stats.json   precomputed per-district aggregates
```

### 4. For development (no downloads needed)
```bash
python build_data.py --synthetic
```

---

## Deploy to Vercel

1. Create a GitHub repo called `redraw-the-lines`
2. Push this folder to `main`
3. Go to [vercel.com](https://vercel.com) → New Project → Import repo → Deploy

Zero configuration needed. Every push to `main` redeploys in ~15 seconds.

---

## Project Structure

```
redraw-the-lines/
├── index.html              Single-file frontend (all HTML/CSS/JS)
├── data/                   Static data files (run pipeline to generate)
│   ├── precincts.geojson
│   ├── districts.geojson
│   ├── assignment.json
│   └── district_stats.json
├── pipeline/               Run once to generate /data/
│   ├── build_data.py
│   └── requirements.txt
└── README.md
```

---

## Key Concepts Explained

**Efficiency Gap** — Counts "wasted votes" (votes beyond what's needed to win, plus all losing votes) for each party. Divides the difference by total votes. Above 7% is presumptively problematic; courts struck down Wisconsin's 2011 map at 11.7%.

**Packing** — Drawing a district where one party wins 80%+ of votes. Their votes beyond the winning margin are wasted.

**Cracking** — Splitting a geographic community across multiple districts so it can't form a majority in any of them.

**Seat-Vote Gap** — The difference between a party's vote share and its seat share. A perfectly proportional map has 0% gap.

**Polsby-Popper Score** — Measures district shape. 1 = circular, 0 = extremely elongated. TX-35 (Austin→San Antonio) scores near 0.

---

## Data Sources

| Source | License | Description |
|---|---|---|
| MIT VEST 2020 TX | CC BY 4.0 | Precinct-level election results + Census demographics |
| TLC Plan C2193 | Public domain | Official Texas 2021 congressional redistricting |
| US Atlas (CDN) | Public domain | County boundaries (fallback when real data absent) |

---

*Built for the Carnegie Young Leaders project. For educational purposes.*
