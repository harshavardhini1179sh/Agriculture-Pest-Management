#!/usr/bin/env python3
"""Load regions and crops from a USDA QuickStats CSV, then add pests, treatments,
and synthetic pest reports / treatment applications.

This lets you honestly say the base dataset for regions and crops comes from
USDA QuickStats, while still using realistic pest and treatment information
inspired by Extension.org and EPPO.

Usage (after downloading the CSV as described in README/HOW_IT_WORKS):

    python3 init_db.py
    python3 load_quickstats_dataset.py
    python3 app.py
"""

import csv
import os
import random
import sys
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import config  # type: ignore
import psycopg2  # type: ignore


SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
QUICKSTATS_CSV = os.path.join(SCRIPT_DIR, "data", "usda_quickstats_crops.csv")

# Domain pests and treatments (previously came from sample_data.json).
DOMAIN_PESTS = [
    {
        "common_name": "Corn Earworm",
        "scientific_name": "Helicoverpa zea",
        "pest_type": "insect",
        "description": "Major pest of corn and cotton; larvae feed on kernels and bolls.",
    },
    {
        "common_name": "Aphid",
        "scientific_name": "Aphidoidea",
        "pest_type": "insect",
        "description": "Sapsucking insects; vector viruses and reduce yield.",
    },
    {
        "common_name": "Early Blight",
        "scientific_name": "Alternaria solani",
        "pest_type": "disease",
        "description": "Fungal disease of tomato and potato; leaf spots and defoliation.",
    },
    {
        "common_name": "Fall Armyworm",
        "scientific_name": "Spodoptera frugiperda",
        "pest_type": "insect",
        "description": "Feeds on corn, sorghum, and pasture; invasive.",
    },
    {
        "common_name": "Cotton Bollworm",
        "scientific_name": "Helicoverpa armigera",
        "pest_type": "insect",
        "description": "Damages cotton bolls and corn ears.",
    },
    {
        "common_name": "Spider Mite",
        "scientific_name": "Tetranychus urticae",
        "pest_type": "insect",
        "description": "Sucks sap; causes stippling and webbing.",
    },
    {
        "common_name": "Whitefly",
        "scientific_name": "Bemisia tabaci",
        "pest_type": "insect",
        "description": "Vector of viruses; honeydew and sooty mold.",
    },
    {
        "common_name": "Corn Borer",
        "scientific_name": "Ostrinia nubilalis",
        "pest_type": "insect",
        "description": "European corn borer; tunnels in stalks and ears.",
    },
    {
        "common_name": "Root Knot Nematode",
        "scientific_name": "Meloidogyne spp.",
        "pest_type": "nematode",
        "description": "Galls on roots; stunts growth of many crops.",
    },
    {
        "common_name": "Late Blight",
        "scientific_name": "Phytophthora infestans",
        "pest_type": "disease",
        "description": "Devastating on tomato and potato.",
    },
    {
        "common_name": "Stink Bug",
        "scientific_name": "Pentatomidae",
        "pest_type": "insect",
        "description": "Feeds on seeds and fruits; damage to soybeans and cotton.",
    },
    {
        "common_name": "Thrips",
        "scientific_name": "Thysanoptera",
        "pest_type": "insect",
        "description": "Scarring and virus transmission.",
    },
    {
        "common_name": "Citrus Greening",
        "scientific_name": "Candidatus Liberibacter",
        "pest_type": "disease",
        "description": "Bacterial disease of citrus; vector psyllid.",
    },
    {
        "common_name": "Rust",
        "scientific_name": "Pucciniales",
        "pest_type": "disease",
        "description": "Fungal rust on wheat, corn, and many crops.",
    },
    {
        "common_name": "Cutworm",
        "scientific_name": "Noctuidae",
        "pest_type": "insect",
        "description": "Larvae cut seedlings at base.",
    },
]

DOMAIN_TREATMENTS = [
    {"name": "Insecticide A (Pyrethroid)", "type": "chemical", "cost_per_acre": 25.00},
    {"name": "Neem Oil", "type": "biological", "cost_per_acre": 15.00},
    {"name": "Crop Rotation", "type": "cultural", "cost_per_acre": 0},
    {"name": "Bt (Bacillus thuringiensis)", "type": "biological", "cost_per_acre": 18.00},
    {"name": "Insecticide B (Organophosphate)", "type": "chemical", "cost_per_acre": 30.00},
    {"name": "Fungicide Copper", "type": "chemical", "cost_per_acre": 22.00},
    {"name": "Beneficial Nematodes", "type": "biological", "cost_per_acre": 35.00},
    {"name": "Trap Crops", "type": "cultural", "cost_per_acre": 8.00},
    {"name": "Spinosad", "type": "biological", "cost_per_acre": 28.00},
    {"name": "Fungicide Chlorothalonil", "type": "chemical", "cost_per_acre": 20.00},
]


def normalise_commodity(commodity_desc: str):
    """Map QuickStats COMMODITY_DESC to friendly crop name."""
    if not commodity_desc:
        return "Unknown"
    key = commodity_desc.strip().upper()
    mapping = {
        "CORN": "Corn",
        "SOYBEANS": "Soybeans",
        "WHEAT": "Wheat",
        "COTTON": "Cotton",
        "RICE": "Rice",
        "PEANUTS": "Peanuts",
        "TOMATOES": "Tomato",
        "POTATOES": "Potato",
        "ALFALFA": "Alfalfa",
        "SUGARCANE": "Sugarcane",
        "CITRUS": "Citrus",
        "ORANGES": "Citrus",
        "PEACHES": "Peaches",
        "APPLES": "Apples",
        "TOBACCO": "Tobacco",
        "SWEET POTATOES": "Sweet Potato",
        "BARLEY": "Barley",
        "OATS": "Oats",
        "SORGHUM": "Sorghum",
        "HAY": "Hay",
        "LETTUCE": "Lettuce",
        "ONIONS": "Onions",
        "ALMONDS": "Almonds",
    }
    if key in mapping:
        return mapping[key]
    return commodity_desc.title()


def read_quickstats_rows(path: str):
    """Read a QuickStats-style CSV and extract regions and (state, commodity) pairs.

    The official API uses STATE_ALPHA / STATE_NAME / COMMODITY_DESC, but the web UI
    download often uses shorter headers like State and Commodity. Support both.
    """
    regions = {}  # (state_code) -> state_name
    crop_keys = set()  # (state_code, commodity_desc)

    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            # State code: try STATE_ALPHA, then State, then GEO_ID style codes if present.
            state_alpha = (
                row.get("state_alpha")
                or row.get("STATE_ALPHA")
                or row.get("State")
                or row.get("STATE")
            )
            state_name = (
                row.get("state_name")
                or row.get("STATE_NAME")
                or row.get("State Name")
                or row.get("State")
                or row.get("STATE")
            )
            commodity_desc = (
                row.get("commodity_desc")
                or row.get("COMMODITY_DESC")
                or row.get("Commodity")
                or row.get("COMMODITY")
            )

            # Some downloads only have the full state name (no 2-letter code). In that
            # case use the name itself as the code.
            if not state_alpha and state_name:
                # e.g. "ALABAMA" -> "ALABAMA" as code; still better than dropping the row.
                state_alpha = state_name.upper()

            if not state_alpha or not state_name or not commodity_desc:
                continue

            # Skip national-level or aggregate rows if they appear.
            if state_alpha.upper() in {"US", "OTHER STATES"}:
                continue

            regions[state_alpha] = state_name.title()
            crop_keys.add((state_alpha, commodity_desc))

    return regions, crop_keys


def main():
    if not os.path.exists(QUICKSTATS_CSV):
        print("QuickStats CSV not found at:", QUICKSTATS_CSV)
        print("Place your downloaded USDA QuickStats file there and run again.")
        return

    print("Loading USDA QuickStats CSV:", QUICKSTATS_CSV)
    regions_data, crop_keys = read_quickstats_rows(QUICKSTATS_CSV)
    print("Unique states in CSV:", len(regions_data))
    print("Unique (state, commodity) crop combinations:", len(crop_keys))

    try:
        conn = psycopg2.connect(config.DATABASE_URL)
    except Exception as e:
        print("Database connection failed:", e)
        print("Start PostgreSQL, then: python3 init_db.py && python3 load_quickstats_dataset.py")
        return

    cur = conn.cursor()
    try:
        # Start from a clean slate for all 6 tables
        cur.execute(
            "TRUNCATE TABLE treatment_application, pest_report, treatment, pest, crop, region "
            "RESTART IDENTITY CASCADE"
        )
        conn.commit()

        # Insert regions from QuickStats (state code, state name). state_code column
        # is limited to VARCHAR(10), so truncate any longer codes.
        region_ids = {}
        for state_alpha, state_name in sorted(regions_data.items()):
            state_code = state_alpha[:10]
            cur.execute(
                "INSERT INTO region (state_code, name) VALUES (%s, %s) RETURNING region_id",
                (state_code, state_name),
            )
            region_id = cur.fetchone()[0]
            region_ids[state_alpha] = region_id
        conn.commit()
        print("Regions inserted from QuickStats:", len(region_ids))

        # Insert crops based on (state, commodity) keys
        crop_ids = []
        crop_region_map = {}  # crop_id -> region_id
        for state_alpha, commodity_desc in sorted(crop_keys):
            region_id = region_ids.get(state_alpha)
            if not region_id:
                continue
            name = normalise_commodity(commodity_desc)
            cur.execute(
                """INSERT INTO crop (region_id, name, scientific_name)
                   VALUES (%s, %s, %s) RETURNING crop_id""",
                (region_id, name, None),
            )
            cid = cur.fetchone()[0]
            crop_ids.append(cid)
            crop_region_map[cid] = region_id
        conn.commit()
        print("Crops inserted from QuickStats:", len(crop_ids))

        # Insert pests (from embedded domain data, inspired by Extension.org / EPPO)
        pest_ids = []
        for p in DOMAIN_PESTS:
            cur.execute(
                """INSERT INTO pest (common_name, scientific_name, pest_type, description)
                   VALUES (%s, %s, %s, %s) RETURNING pest_id""",
                (p["common_name"], p.get("scientific_name"), p.get("pest_type"), p.get("description")),
            )
            pest_ids.append(cur.fetchone()[0])
        conn.commit()
        print("Pests inserted from domain JSON:", len(pest_ids))

        # Insert treatments (from embedded domain data)
        treatment_ids = []
        for t in DOMAIN_TREATMENTS:
            cur.execute(
                """INSERT INTO treatment (name, type, cost_per_acre)
                   VALUES (%s, %s, %s) RETURNING treatment_id""",
                (t["name"], t.get("type"), t.get("cost_per_acre")),
            )
            treatment_ids.append(cur.fetchone()[0])
        conn.commit()
        print("Treatments inserted from domain JSON:", len(treatment_ids))

        # Generate synthetic pest reports leveraging QuickStats-based regions/crops
        random.seed(101)
        base_date = date.today() - timedelta(days=365 * 3)
        report_ids = []
        if not crop_ids or not pest_ids:
            print("No crops or pests available to generate reports.")
        else:
            for _ in range(200):
                pid = random.choice(pest_ids)
                cid = random.choice(crop_ids)
                rid = crop_region_map.get(cid)
                status = random.choice(["pending", "verified", "resolved"])
                cur.execute(
                    """INSERT INTO pest_report (pest_id, crop_id, region_id, status, created_by)
                       VALUES (%s, %s, %s, %s, NULL) RETURNING report_id""",
                    (pid, cid, rid, status),
                )
                report_ids.append(cur.fetchone()[0])
            conn.commit()
        print("Synthetic pest reports generated:", len(report_ids))

        # Generate synthetic treatment applications for those reports
        extra_apps = 0
        for rpt_id in report_ids:
            # About 70% of reports get 1–2 applications
            if random.random() < 0.7:
                for _ in range(random.randint(1, 2)):
                    crop_id = None
                    # Look up crop_id via pest_report row
                    cur.execute("SELECT crop_id FROM pest_report WHERE report_id = %s", (rpt_id,))
                    row = cur.fetchone()
                    if row:
                        crop_id = row[0]
                    if crop_id is None:
                        continue

                    tid = random.choice(treatment_ids)
                    app_date = base_date + timedelta(days=random.randint(0, 365 * 3))
                    effectiveness = random.randint(2, 5)
                    cost_value = 80 + random.randint(-20, 40)
                    cur.execute(
                        """INSERT INTO treatment_application (pest_report_id, treatment_id, crop_id, application_date, effectiveness_rating, cost)
                           VALUES (%s, %s, %s, %s, %s, %s)""",
                        (rpt_id, tid, crop_id, app_date, effectiveness, cost_value),
                    )
                    extra_apps += 1
        conn.commit()
        print("Synthetic treatment applications generated:", extra_apps)

        # Final counts for sanity
        cur.execute("SELECT COUNT(*) FROM region")
        print("Region rows:", cur.fetchone()[0])
        cur.execute("SELECT COUNT(*) FROM crop")
        print("Crop rows:", cur.fetchone()[0])
        cur.execute("SELECT COUNT(*) FROM pest_report")
        print("Pest report rows:", cur.fetchone()[0])
        cur.execute("SELECT COUNT(*) FROM treatment_application")
        print("Treatment application rows:", cur.fetchone()[0])
        print("Done. Dataset now grounded in USDA QuickStats regions/crops plus domain pests/treatments.")
    finally:
        cur.close()
        conn.close()


if __name__ == "__main__":
    main()

