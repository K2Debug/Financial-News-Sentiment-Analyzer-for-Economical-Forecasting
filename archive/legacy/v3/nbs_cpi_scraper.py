"""
EF-02 | NBS CPI Excel Scraper
------------------------------
Scrapes and downloads the monthly CPI summary .xls files
from nbs.go.tz for years 2022, 2023, 2024.

Each year has 3 pages. Per month there are:
  - 2 PDFs  (English + Kiswahili) — skipped
  - 1 .xls  (CPI Summary)         — downloaded

Output folder structure:
    nbs_cpi_raw/
        2022/
            CPI_Summary_012022.xls
            CPI_Summary_022022.xls
            ...
        2023/
            ...
        2024/
            ...

Usage (in Jupyter):
    Run cells top to bottom.
    After downloading, run the "Parse & Combine" cell to produce:
        nbs_cpi_monthly.csv  — one row per month, ready for correlation analysis
"""

# ════════════════════════════════════════════════════════════
# CELL 1 — Imports
# ════════════════════════════════════════════════════════════

import os
import time
import re
import requests
from bs4 import BeautifulSoup
import pandas as pd

BASE_URL    = "https://www.nbs.go.tz"
YEARS       = [2022, 2023, 2024]
PAGES       = [1, 2, 3]           # each year has 3 pages
OUTPUT_DIR  = "nbs_cpi_raw"
SLEEP_SEC   = 1.5                  # polite delay between requests

# Year slug differs slightly for each year on the NBS site
YEAR_SLUGS = {
    2022: "consumer-price-index-2022",
    2023: "consumer-price-index-2023",
    2024: "consumer-price-index-2024",
}

os.makedirs(OUTPUT_DIR, exist_ok=True)
for yr in YEARS:
    os.makedirs(os.path.join(OUTPUT_DIR, str(yr)), exist_ok=True)

print("Folders ready.")
print(f"Will download to: {os.path.abspath(OUTPUT_DIR)}/")


# ════════════════════════════════════════════════════════════
# CELL 2 — Link Extractor
# ════════════════════════════════════════════════════════════

def get_xls_links(year, page):
    """
    Fetches one page of the NBS CPI listing for a given year
    and returns all .xls download links found on that page.
    Returns list of dicts: [{"filename": "...", "url": "..."}, ...]
    """
    slug = YEAR_SLUGS[year]
    url  = f"{BASE_URL}/statistics/topic/{slug}?page={page}"

    try:
        resp = requests.get(url, timeout=15)
        resp.raise_for_status()
    except requests.RequestException as e:
        print(f"  Failed to fetch {url}: {e}")
        return []

    soup  = BeautifulSoup(resp.text, "html.parser")
    links = []

    for a in soup.find_all("a", href=True):
        href = a["href"]
        # Only grab .xls files — skip PDFs
        if href.lower().endswith(".xls") or href.lower().endswith(".xlsx"):
            # Build absolute URL if path is relative
            full_url = href if href.startswith("http") else BASE_URL + href
            # Use the filename from the URL, cleaned up
            raw_name = href.split("/")[-1]
            filename = requests.utils.unquote(raw_name)
            links.append({"filename": filename, "url": full_url})

    return links


# Quick test — preview what page 1 of 2022 has
print("Testing link extraction on 2022 page 1...")
test_links = get_xls_links(2022, 1)
for l in test_links:
    print(f"  {l['filename']}")
    print(f"  → {l['url']}\n")


# ════════════════════════════════════════════════════════════
# CELL 3 — Downloader
# ════════════════════════════════════════════════════════════

def download_file(url, save_path):
    """
    Downloads a file to save_path.
    Skips if file already exists (safe to rerun).
    Returns True on success, False on failure.
    """
    if os.path.exists(save_path):
        print(f"  Already exists, skipping: {os.path.basename(save_path)}")
        return True

    try:
        resp = requests.get(url, timeout=30)
        resp.raise_for_status()
        with open(save_path, "wb") as f:
            f.write(resp.content)
        print(f"  Downloaded: {os.path.basename(save_path)}")
        return True
    except requests.RequestException as e:
        print(f"  FAILED: {os.path.basename(save_path)} — {e}")
        return False


def scrape_all_years():
    """
    Main loop. Goes through all years and all pages,
    collects .xls links, and downloads each one.
    """
    total_found    = 0
    total_downloaded = 0
    failed         = []

    for year in YEARS:
        print(f"\n{'='*50}")
        print(f"Year: {year}")
        print(f"{'='*50}")
        year_dir = os.path.join(OUTPUT_DIR, str(year))

        for page in PAGES:
            print(f"\n  Page {page}...")
            links = get_xls_links(year, page)

            if not links:
                print(f"  No .xls files found on page {page} — skipping.")
                time.sleep(SLEEP_SEC)
                continue

            for item in links:
                total_found += 1
                save_path = os.path.join(year_dir, item["filename"])
                success   = download_file(item["url"], save_path)

                if success:
                    total_downloaded += 1
                else:
                    failed.append(item)

                time.sleep(0.5)   # short pause between file downloads

            time.sleep(SLEEP_SEC)  # longer pause between page requests

    print(f"\n{'='*50}")
    print(f"DONE")
    print(f"  Files found    : {total_found}")
    print(f"  Downloaded     : {total_downloaded}")
    print(f"  Failed         : {len(failed)}")
    if failed:
        print(f"\n  Failed files:")
        for f in failed:
            print(f"    {f['filename']} → {f['url']}")

    return total_downloaded, failed


# Run the scraper
downloaded, failed = scrape_all_years()


# ════════════════════════════════════════════════════════════
# CELL 4 — Inspect One File (run after downloading)
# ════════════════════════════════════════════════════════════
#
# Before parsing all files, peek at one to understand the structure.
# NBS xls files sometimes have merged header rows or metadata rows
# at the top — we need to know which row the actual data starts on.

def inspect_file(filepath):
    """Print first 15 rows of every sheet in an xls file."""
    try:
        sheets = pd.read_excel(filepath, sheet_name=None, header=None)
        for sheet_name, df in sheets.items():
            print(f"\n--- Sheet: {sheet_name} ---")
            print(df.head(15).to_string())
    except Exception as e:
        print(f"Could not read {filepath}: {e}")

# Find the first downloaded file and inspect it
first_file = None
for yr in YEARS:
    yr_dir = os.path.join(OUTPUT_DIR, str(yr))
    files  = [f for f in os.listdir(yr_dir) if f.endswith(".xls") or f.endswith(".xlsx")]
    if files:
        first_file = os.path.join(yr_dir, files[0])
        break

if first_file:
    print(f"Inspecting: {first_file}\n")
    inspect_file(first_file)
else:
    print("No files downloaded yet — run the scraper first.")


# ════════════════════════════════════════════════════════════
# CELL 5 — Parse & Combine (run after inspecting)
# ════════════════════════════════════════════════════════════
#
# After inspecting, set HEADER_ROW and CPI_COLUMN below to match
# what you see in the actual files, then run this cell.
#
# What we're extracting:
#   - year_month  (e.g. "2022-01")
#   - cpi_index   (the headline all-items CPI value)
#   - yoy_pct     (year-on-year % change, if present in the file)

HEADER_ROW  = 2    # ← adjust after inspecting (0-indexed)
CPI_COLUMN  = None # ← set to column name or index after inspecting
                   #   e.g. "All Items" or 3

# Month name → number mapping (NBS files use month names in filenames)
MONTH_MAP = {
    "01": "January",  "02": "February", "03": "March",
    "04": "April",    "05": "May",       "06": "June",
    "07": "July",     "08": "August",    "09": "September",
    "10": "October",  "11": "November",  "12": "December",
    # also handle if month appears in filename as name
    "jan":"01","feb":"02","mar":"03","apr":"04","may":"05","jun":"06",
    "jul":"07","aug":"08","sep":"09","oct":"10","nov":"11","dec":"12",
}

def extract_year_month_from_filename(filename):
    """
    NBS filenames follow patterns like:
      CPI_Summary_122022.xls   → 2022-12
      CPI Summary_122022.xls   → 2022-12
      CPI_Summary_January 2023.xls → 2023-01
    Tries numeric pattern first, then month-name pattern.
    """
    # Pattern 1: MMYYYY at end  e.g. 122022
    m = re.search(r'(\d{2})(\d{4})\.xls', filename, re.IGNORECASE)
    if m:
        return f"{m.group(2)}-{m.group(1)}"

    # Pattern 2: month name + year  e.g. "January 2023"
    m = re.search(
        r'(January|February|March|April|May|June|July|August|'
        r'September|October|November|December)\s+(\d{4})',
        filename, re.IGNORECASE
    )
    if m:
        month_num = {v: k for k, v in {
            "01":"January","02":"February","03":"March","04":"April",
            "05":"May","06":"June","07":"July","08":"August",
            "09":"September","10":"October","11":"November","12":"December"
        }.items()}[m.group(1).capitalize()]
        return f"{m.group(2)}-{month_num}"

    return None


def parse_cpi_file(filepath, header_row, cpi_col):
    """
    Reads one CPI summary xls and returns a single-row dict:
    { year_month, cpi_index, yoy_pct }
    Returns None if parsing fails.
    """
    filename   = os.path.basename(filepath)
    year_month = extract_year_month_from_filename(filename)

    if not year_month:
        print(f"  Could not parse date from filename: {filename}")
        return None

    try:
        df = pd.read_excel(filepath, header=header_row)

        # If cpi_col is set, extract that column's value
        if cpi_col is not None:
            # Try to find a row labelled "All items" or similar
            # For now take the first numeric value in the column
            col_data = pd.to_numeric(df[cpi_col], errors='coerce').dropna()
            cpi_val  = col_data.iloc[0] if len(col_data) > 0 else None
        else:
            cpi_val = None   # will be set after you inspect and configure above

        return {
            "year_month": year_month,
            "cpi_index":  cpi_val,
            "source":     "NBS Tanzania"
        }

    except Exception as e:
        print(f"  Failed to parse {filename}: {e}")
        return None


def combine_all_files():
    """Walk nbs_cpi_raw/, parse every xls, combine into one DataFrame."""
    records = []

    for yr in YEARS:
        yr_dir = os.path.join(OUTPUT_DIR, str(yr))
        if not os.path.exists(yr_dir):
            continue
        files = sorted([
            f for f in os.listdir(yr_dir)
            if f.lower().endswith(".xls") or f.lower().endswith(".xlsx")
        ])
        print(f"\nYear {yr}: {len(files)} files")

        for fname in files:
            fpath  = os.path.join(yr_dir, fname)
            record = parse_cpi_file(fpath, HEADER_ROW, CPI_COLUMN)
            if record:
                records.append(record)
                print(f"  {record['year_month']} — CPI: {record['cpi_index']}")

    if not records:
        print("\nNo records parsed. Check HEADER_ROW and CPI_COLUMN settings.")
        return None

    df = pd.DataFrame(records).sort_values("year_month").reset_index(drop=True)

    output_path = "nbs_cpi_monthly.csv"
    df.to_csv(output_path, index=False)

    print(f"\n{'='*50}")
    print(f"Saved {len(df)} monthly records to {output_path}")
    print(f"\nPreview:")
    print(df.to_string(index=False))

    return df

# Run the parser
# NOTE: inspect Cell 4 output first, then set HEADER_ROW and CPI_COLUMN above
df_cpi = combine_all_files()
