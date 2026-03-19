#!/usr/bin/env python3
"""
Redraw the Lines — Data Preprocessing Pipeline
================================================
Run once to produce 3 static files the web app loads:

  data/precincts.geojson     ~9,000 TX precincts + vote + demographics  (~8-15 MB)
  data/districts.geojson     38 Plan C2193 boundaries                   (<1 MB)
  data/assignment.json       { precinct_id: district_number }           (<500 KB)
  data/district_stats.json   precomputed per-district aggregates        (<50 KB)

REQUIREMENTS:
  pip install -r requirements.txt

DATA SOURCES (both free, no account required):
  1. MIT VEST 2020 Texas precincts
     https://dataverse.harvard.edu/dataverse/electionscience
     Search "2020 Precinct-Level Election Results" -> download tx_2020.zip
     Unzip into: pipeline/raw_data/vest/

  2. TLC Plan C2193 congressional shapefile
     https://tlc.texas.gov/redist/data/planc2193.zip
     Unzip into: pipeline/raw_data/districts/

USAGE:
  python build_data.py
  python build_data.py --precincts raw_data/vest/tx_2020.shp --districts raw_data/districts/PlanC2193.shp
  python build_data.py --synthetic   # dev mode, no downloads needed
"""

import argparse
import json
import sys
import time
from pathlib import Path

try:
    import geopandas as gpd
    import numpy as np
    import pandas as pd
    from shapely.geometry import box
    from shapely.ops import unary_union
    from shapely.validation import make_valid
except ImportError as e:
    print(f"\nERROR: {e}\nRun: pip install -r requirements.txt\n")
    sys.exit(1)

OUT_DIR           = Path("../data")
RAW_DIR           = Path("raw_data")
PRECINCT_SIMPLIFY = 0.005
DISTRICT_SIMPLIFY = 0.002
IDEAL_POP         = 761169

VEST_COL_MAP = {
    "G20PREDBID": "biden",  "G20PRERTRM": "trump",
    "G20USSDHEG": "hegar",  "G20USSRCON": "cornyn",
    "G20PRE_DEM": "biden",  "G20PRE_REP": "trump",
    "G20USS_DEM": "hegar",  "G20USS_REP": "cornyn",
    "TOTPOP20":   "pop",    "TOTPOP":     "pop",
    "NH_WHITE20": "white",  "NH_WHITE":   "white",
    "NH_BLACK20": "black",  "NH_BLACK":   "black",
    "HISP20":     "hisp",   "HISP":       "hisp",
    "NH_ASIAN20": "asian",  "NH_ASIAN":   "asian",
    "NH_AMIN20":  "native", "NH_2MORE20": "multi",
}

TLC_DIST_COLS = ["DISTRICT", "CONG_DIST", "CD", "PLANCD", "DISTRICT_N", "CONG"]


# ── helpers ───────────────────────────────────────────────────────────────────
def log(msg, indent=0):
    print("  " * indent + msg)


def find_shp(directory, keywords):
    if not Path(directory).exists():
        return None
    for f in Path(directory).rglob("*.shp"):
        if any(k.lower() in f.name.lower() for k in keywords):
            return f
    shps = list(Path(directory).rglob("*.shp"))
    return shps[0] if len(shps) == 1 else None


def normalize_cols(gdf, col_map):
    existing = {c.upper(): c for c in gdf.columns}
    rename = {}
    for vest, std in col_map.items():
        if vest.upper() in existing and std not in gdf.columns:
            rename[existing[vest.upper()]] = std
    return gdf.rename(columns=rename) if rename else gdf


def safe_simplify(geom, tol):
    if geom is None or geom.is_empty:
        return geom
    if not geom.is_valid:
        geom = make_valid(geom)
    return geom.simplify(tol, preserve_topology=True)


def ensure_int(gdf, cols):
    for c in cols:
        if c in gdf.columns:
            gdf[c] = pd.to_numeric(gdf[c], errors="coerce").fillna(0).astype(int)
    return gdf


# ── step 1: load precincts ────────────────────────────────────────────────────
def load_precincts(path_arg):
    path = None
    if path_arg:
        path = Path(path_arg)
    else:
        path = (find_shp(RAW_DIR / "vest", ["tx_2020", "tx2020", "texas_2020"]) or
                find_shp(RAW_DIR, ["tx_2020", "tx2020", "texas_2020"]))
    if not path or not path.exists():
        log("✗ VEST precinct shapefile not found.")
        print("""
╔═══════════════════════════════════════════════════════════╗
║  Download MIT VEST 2020 Texas precinct shapefile          ║
║                                                           ║
║  1. https://dataverse.harvard.edu/dataverse/electionscience
║  2. Search: "2020 Precinct-Level Election Results"       ║
║  3. Download: tx_2020.zip  (free, no login)              ║
║  4. Unzip to: pipeline/raw_data/vest/                    ║
║  5. Re-run:   python build_data.py                       ║
║                                                           ║
║  Or use: python build_data.py --synthetic                ║
╚═══════════════════════════════════════════════════════════╝""")
        return None
    log(f"Loading precincts: {path}", 1)
    t0 = time.time()
    gdf = gpd.read_file(path)
    log(f"✓ {len(gdf):,} precincts  ({time.time()-t0:.1f}s)", 2)
    return gdf


# ── step 2: load districts ────────────────────────────────────────────────────
def load_districts(path_arg):
    path = None
    if path_arg:
        path = Path(path_arg)
    else:
        path = (find_shp(RAW_DIR / "districts", ["c2193", "congress", "planc"]) or
                find_shp(RAW_DIR, ["c2193", "planc", "congress"]))
    if not path or not path.exists():
        log("✗ TLC district shapefile not found.")
        print("""
╔═══════════════════════════════════════════════════════════╗
║  Download TLC Plan C2193 congressional shapefile          ║
║                                                           ║
║  1. https://tlc.texas.gov/redist/data/planc2193.zip      ║
║  2. Unzip to: pipeline/raw_data/districts/               ║
║  3. Re-run:   python build_data.py                       ║
╚═══════════════════════════════════════════════════════════╝""")
        return None
    log(f"Loading districts: {path}", 1)
    gdf = gpd.read_file(path)
    log(f"✓ {len(gdf)} districts", 2)
    return gdf


# ── step 3: process precincts ─────────────────────────────────────────────────
def process_precincts(gdf):
    log("Processing precincts...", 1)
    if gdf.crs and gdf.crs.to_epsg() != 4326:
        log(f"Reprojecting {gdf.crs} → WGS84", 2)
        gdf = gdf.to_crs("EPSG:4326")

    gdf = normalize_cols(gdf, VEST_COL_MAP)

    for col in ["biden", "trump", "hegar", "cornyn", "pop", "white", "black", "hisp", "asian", "native", "multi"]:
        if col not in gdf.columns:
            gdf[col] = 0

    gdf["other"] = (gdf["pop"] - gdf["white"] - gdf["black"] - gdf["hisp"] - gdf["asian"]).clip(lower=0)
    gdf = ensure_int(gdf, ["biden", "trump", "hegar", "cornyn", "pop", "white", "black", "hisp", "asian", "other"])

    # Stable precinct ID
    for id_col in ["GEOID20", "GEOID", "VTDST20", "VTDST"]:
        if id_col in gdf.columns:
            gdf["precinct_id"] = gdf[id_col].astype(str)
            break
    else:
        gdf["precinct_id"] = ["TX" + str(i).zfill(6) for i in range(len(gdf))]

    log(f"Simplifying geometry (tol={PRECINCT_SIMPLIFY})...", 2)
    t0 = time.time()
    gdf["geometry"] = gdf["geometry"].apply(lambda g: safe_simplify(g, PRECINCT_SIMPLIFY))
    gdf = gdf[~gdf.geometry.is_empty & gdf.geometry.notna()].copy()
    log(f"✓ {len(gdf):,} precincts simplified  ({time.time()-t0:.1f}s)", 2)
    return gdf


# ── step 4: process districts ─────────────────────────────────────────────────
def process_districts(gdf):
    log("Processing districts...", 1)
    if gdf.crs and gdf.crs.to_epsg() != 4326:
        gdf = gdf.to_crs("EPSG:4326")

    dist_col = None
    cols_upper = {c.upper(): c for c in gdf.columns}
    for cand in TLC_DIST_COLS:
        if cand.upper() in cols_upper:
            dist_col = cols_upper[cand.upper()]
            break
    if not dist_col:
        log("WARNING: district column not found — using row index", 2)
        gdf["district_num"] = range(1, len(gdf) + 1)
        dist_col = "district_num"

    gdf = gdf.rename(columns={dist_col: "district_num"})
    gdf["district_num"] = pd.to_numeric(gdf["district_num"], errors="coerce").fillna(0).astype(int)
    gdf["geometry"] = gdf["geometry"].apply(lambda g: safe_simplify(g, DISTRICT_SIMPLIFY))
    gdf = gdf[~gdf.geometry.is_empty].copy()
    log(f"✓ {len(gdf)} districts ready", 2)
    return gdf


# ── step 5: spatial join ──────────────────────────────────────────────────────
def spatial_join(precincts, districts):
    log("Spatial join: precinct centroids → districts...", 1)
    t0 = time.time()
    centroids = precincts[["precinct_id", "geometry"]].copy()
    centroids["geometry"] = precincts.geometry.centroid

    joined = gpd.sjoin(centroids, districts[["district_num", "geometry"]], how="left", predicate="within")

    # Fix unmatched (border effects)
    missing_mask = joined["district_num"].isna()
    if missing_mask.any():
        log(f"{missing_mask.sum()} centroids outside districts — nearest-distance fix", 2)
        for idx in joined[missing_mask].index:
            pt = centroids.loc[idx, "geometry"]
            nearest = districts.loc[districts.geometry.distance(pt).idxmin(), "district_num"]
            joined.loc[idx, "district_num"] = nearest

    joined["district_num"] = joined["district_num"].fillna(1).astype(int)
    assignment = dict(zip(joined["precinct_id"].astype(str), joined["district_num"].astype(int)))
    log(f"✓ {len(assignment):,} precincts assigned  ({time.time()-t0:.1f}s)", 2)
    return assignment


# ── step 6: export ────────────────────────────────────────────────────────────
def export_all(precincts, districts, assignment):
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    # precincts.geojson
    keep = ["precinct_id", "biden", "trump", "pop", "white", "black", "hisp", "asian", "other", "geometry"]
    exp = precincts[[c for c in keep if c in precincts.columns]].copy()
    exp["district"] = exp["precinct_id"].map(assignment).fillna(0).astype(int)
    for col in ["biden", "trump", "pop", "white", "black", "hisp", "asian", "other"]:
        if col in exp.columns:
            exp[col] = exp[col].round().astype(int)
    out = OUT_DIR / "precincts.geojson"
    exp.to_file(out, driver="GeoJSON")
    log(f"✓ precincts.geojson  ({out.stat().st_size/1e6:.1f} MB, {len(exp):,} features)", 2)

    # districts.geojson
    out = OUT_DIR / "districts.geojson"
    districts[["district_num", "geometry"]].to_file(out, driver="GeoJSON")
    log(f"✓ districts.geojson  ({out.stat().st_size/1e6:.1f} MB)", 2)

    # assignment.json
    out = OUT_DIR / "assignment.json"
    with open(out, "w") as f:
        json.dump(assignment, f, separators=(",", ":"))
    log(f"✓ assignment.json    ({out.stat().st_size/1e3:.0f} KB, {len(assignment):,} entries)", 2)

    # district_stats.json (precomputed for instant sidebar)
    stats = {i: {"biden":0,"trump":0,"pop":0,"white":0,"black":0,"hisp":0,"asian":0,"other":0} for i in range(1,39)}
    for _, row in precincts.iterrows():
        pid = str(row.get("precinct_id",""))
        d = assignment.get(pid, 0)
        if 1 <= d <= 38:
            for k in ["biden","trump","pop","white","black","hisp","asian","other"]:
                stats[d][k] += int(row.get(k, 0))
    for d, s in stats.items():
        tot = s["biden"] + s["trump"]
        s["winner"] = "D" if s["biden"] >= s["trump"] else "R"
        s["margin"] = round(abs(s["biden"]-s["trump"]) / max(tot,1) * 100, 1)
        s["tot_votes"] = tot
        s["dev_pct"] = round((s["pop"] - IDEAL_POP) / IDEAL_POP * 100, 2)
    out = OUT_DIR / "district_stats.json"
    with open(out, "w") as f:
        json.dump({str(k):v for k,v in stats.items()}, f, separators=(",",":"))
    log(f"✓ district_stats.json ({out.stat().st_size/1e3:.0f} KB)", 2)


# ── synthetic data ────────────────────────────────────────────────────────────
def make_synthetic():
    log("Generating synthetic data (development mode)...", 1)
    np.random.seed(42)
    LON_MIN, LON_MAX = -106.65, -93.51
    LAT_MIN, LAT_MAX = 25.84, 36.50

    # 38 rough district centers across TX geography
    CENTERS = [
        (-94.2,33.0),(-94.5,31.5),(-95.3,30.5),(-94.7,32.5),
        (-95.4,29.8),(-95.2,29.5),(-95.6,29.9),(-95.1,29.6),
        (-95.7,30.2),(-95.5,30.5),(-97.0,32.8),(-97.2,32.7),
        (-96.8,32.9),(-97.3,32.6),(-97.1,33.0),(-96.9,33.1),
        (-97.0,32.5),(-97.8,30.3),(-97.5,30.1),(-98.2,30.5),
        (-97.7,31.5),(-98.5,29.4),(-98.4,29.6),(-98.3,29.3),
        (-100.4,31.8),(-101.8,33.6),(-103.0,31.9),(-102.0,32.5),
        (-99.5,27.5),(-98.8,26.2),(-99.0,27.0),(-97.5,26.0),
        (-97.7,30.25),(-97.8,30.4),(-96.5,31.5),(-97.3,31.2),
        (-98.9,28.7),(-97.0,28.0),
    ]

    rows = []
    for i in range(700):
        lon = np.random.uniform(LON_MIN, LON_MAX)
        lat = np.random.uniform(LAT_MIN, LAT_MAX)
        d_sq = [(lon-cx)**2+(lat-cy)**2 for cx,cy in CENTERS]
        district = d_sq.index(min(d_sq)) + 1

        is_border = lat < 27.5
        is_houston= abs(lon+95.4)<0.8 and abs(lat-29.7)<0.6
        is_austin = abs(lon+97.7)<0.5 and abs(lat-30.3)<0.4
        is_dallas = abs(lon+97.0)<0.8 and abs(lat-32.8)<0.6
        is_urban  = is_houston or is_austin or is_dallas or abs(lon+98.5)<0.4

        pop = int(np.clip(np.random.normal(1500 if is_urban else 3000, 600), 200, 8000))

        if is_border:
            h,w,b = np.random.uniform(.72,.92), np.random.uniform(.04,.14), np.random.uniform(.01,.04)
        elif is_houston:
            h,w,b = np.random.uniform(.28,.45), np.random.uniform(.30,.48), np.random.uniform(.12,.28)
        elif is_austin:
            h,w,b = np.random.uniform(.28,.42), np.random.uniform(.40,.58), np.random.uniform(.06,.14)
        elif is_dallas:
            h,w,b = np.random.uniform(.22,.38), np.random.uniform(.42,.58), np.random.uniform(.10,.22)
        else:
            h,w,b = np.random.uniform(.12,.28), np.random.uniform(.58,.78), np.random.uniform(.03,.10)
        a = np.random.uniform(.01,.08) if is_urban else np.random.uniform(.005,.03)
        o = max(0, 1-h-w-b-a)

        dem = float(np.clip(h*.63+b*.88+a*.61+w*.31+np.random.normal(0,.05), 0.08, 0.94))
        tv = int(pop * np.random.uniform(.55,.80))
        biden = int(tv*dem); trump = tv-biden

        hw2 = np.random.uniform(.06,.30); hh2 = np.random.uniform(.04,.20)
        geom = box(max(LON_MIN,lon-hw2),max(LAT_MIN,lat-hh2),min(LON_MAX,lon+hw2),min(LAT_MAX,lat+hh2))

        rows.append({
            "precinct_id": f"TX{i:06d}", "district": district,
            "biden": biden, "trump": trump,
            "hegar": int(biden*.96), "cornyn": int(trump*.96),
            "pop": pop, "white": int(pop*w), "black": int(pop*b),
            "hisp": int(pop*h), "asian": int(pop*a), "other": int(pop*o),
            "geometry": geom,
        })

    precincts = gpd.GeoDataFrame(rows, crs="EPSG:4326")
    assignment = {r["precinct_id"]: r["district"] for r in rows}

    dist_rows = []
    for d in range(1,39):
        geoms = precincts[precincts["district"]==d].geometry.tolist()
        if geoms:
            dist_rows.append({"district_num": d, "geometry": unary_union(geoms)})
    districts = gpd.GeoDataFrame(dist_rows, crs="EPSG:4326")

    log(f"✓ {len(precincts)} synthetic precincts, {len(districts)} districts", 2)
    return precincts, districts, assignment


# ── main ──────────────────────────────────────────────────────────────────────
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--precincts")
    ap.add_argument("--districts")
    ap.add_argument("--synthetic", action="store_true")
    ap.add_argument("--out", default=str(OUT_DIR))
    args = ap.parse_args()

    global OUT_DIR
    OUT_DIR = Path(args.out)

    print("\n" + "═"*58)
    print("  Redraw the Lines — Data Pipeline")
    print("═"*58)
    t0 = time.time()

    if args.synthetic:
        precincts, districts, assignment = make_synthetic()
    else:
        log("[1/4] Loading source data")
        precincts = load_precincts(args.precincts)
        districts = load_districts(args.districts)
        if precincts is None or districts is None:
            log("\nPipeline stopped. Run --synthetic for dev data.")
            sys.exit(1)
        log("[2/4] Processing precincts")
        precincts = process_precincts(precincts)
        log("[3/4] Processing districts")
        districts = process_districts(districts)
        log("[4/4] Spatial join")
        assignment = spatial_join(precincts, districts)

    log("Exporting files...")
    export_all(precincts, districts, assignment)

    print(f"\n  ✓ Done in {time.time()-t0:.1f}s")
    print(f"  Output: {OUT_DIR.resolve()}/\n")
    print("  To preview locally:")
    print("    cd ..  &&  python -m http.server 8000")
    print("    open http://localhost:8000\n")


if __name__ == "__main__":
    main()
