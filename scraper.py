"""
SAFE Official Reserve Assets Scraper
Fetches monthly reserve data from China's State Administration of Foreign Exchange.
Designed to run via GitHub Actions on the 15th of each month.

Usage:
    pip install -r requirements.txt
    python scraper.py
"""

import json
import re
import os
import sys
from datetime import date
from urllib.request import urlopen, Request
from urllib.error import URLError, HTTPError

try:
    from bs4 import BeautifulSoup
    HAS_BS4 = True
except ImportError:
    HAS_BS4 = False

# Source URLs for each year (official reserve assets pages)
SOURCE_URLS = {
    "2018": "https://www.safe.gov.cn/safe/2018/0408/8785.html",
    "2019": "https://www.safe.gov.cn/safe/2019/0211/11348.html",
    "2020": "https://www.safe.gov.cn/safe/2020/0207/15340.html",
    "2021": "https://www.safe.gov.cn/safe/2021/0202/18181.html",
    "2022": "https://www.safe.gov.cn/safe/2022/0207/22233.html",
    "2023": "https://www.safe.gov.cn/safe/2022/0207/20625.html",
    "2024": "https://www.safe.gov.cn/safe/2022/0207/23934.html",
    "2025": "https://www.safe.gov.cn/safe/2025/0206/27115.html",
    "2026": "https://www.safe.gov.cn/safe/2026/0206/27116.html",
}

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(SCRIPT_DIR, "data")
JSON_PATH = os.path.join(DATA_DIR, "reserves.json")
CSV_PATH = os.path.join(DATA_DIR, "reserves.csv")


def fetch_url(url: str) -> str:
    """Fetch a URL and return decoded text content."""
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/126.0.0.0 Safari/537.36"
        )
    }
    req = Request(url, headers=headers)
    with urlopen(req, timeout=60) as resp:
        raw = resp.read()
    for enc in ("utf-8", "gb2312", "gbk", "latin-1"):
        try:
            return raw.decode(enc)
        except (UnicodeDecodeError, LookupError):
            continue
    return raw.decode("utf-8", errors="replace")


def clean_number(text: str) -> str:
    """Remove commas, spaces, and other formatting from a number string."""
    return text.replace(",", "").replace("，", "").replace(" ", "").strip()


def parse_float(text: str) -> float:
    """Parse a cleaned number string to float, return 0 on failure."""
    text = clean_number(text)
    if not text or text == "-" or text == "—":
        return 0.0
    try:
        return float(text)
    except ValueError:
        return 0.0


def parse_table_bs4(html: str, year: str) -> list:
    """Parse the reserve assets table using BeautifulSoup."""
    soup = BeautifulSoup(html, "lxml")
    records = []

    for table in soup.find_all("table"):
        rows = table.find_all("tr")
        for row in rows:
            cells = row.find_all(["td", "th"])
            cell_texts = [c.get_text(strip=True) for c in cells]

            if not cell_texts:
                continue

            # Match date pattern YYYY.MM
            date_match = re.match(r"^(\d{4})\.(\d{1,2})$", cell_texts[0])
            if not date_match:
                continue

            row_year = date_match.group(1)
            row_month = date_match.group(2).zfill(2)

            if row_year != year:
                continue

            # Need at least 7 columns: date, forex, imf, sdr, gold_usd, gold_oz, other
            if len(cell_texts) >= 7:
                try:
                    record = {
                        "date": f"{row_year}.{row_month}",
                        "foreign_exchange_sdr": parse_float(cell_texts[1]),
                        "imf_reserve_position_sdr": parse_float(cell_texts[2]),
                        "sdr_sdr": parse_float(cell_texts[3]),
                        "gold_usd": parse_float(cell_texts[4]),
                        "gold_oz": int(parse_float(cell_texts[5])),
                        "other_reserves_sdr": parse_float(cell_texts[6]),
                    }
                    records.append(record)
                except (ValueError, IndexError) as e:
                    print(f"  Warning: skip row {cell_texts[0]}: {e}", file=sys.stderr)

    return records


def parse_table_regex(html: str, year: str) -> list:
    """Fallback parser using regex when BeautifulSoup is not available."""
    records = []
    tr_pattern = re.compile(r"<tr[^>]*>(.*?)</tr>", re.DOTALL | re.IGNORECASE)
    td_pattern = re.compile(r"<t[dh][^>]*>(.*?)</t[dh]>", re.DOTALL | re.IGNORECASE)
    tag_strip = re.compile(r"<[^>]+>")

    for row_match in tr_pattern.finditer(html):
        row_html = row_match.group(1)
        cells = td_pattern.findall(row_html)
        cells = [tag_strip.sub("", c).strip() for c in cells]
        cells = [clean_number(c) for c in cells]

        if not cells:
            continue

        date_match = re.match(r"^(\d{4})\.(\d{1,2})$", cells[0])
        if not date_match:
            continue

        row_year = date_match.group(1)
        row_month = date_match.group(2).zfill(2)
        if row_year != year:
            continue

        if len(cells) >= 7:
            try:
                record = {
                    "date": f"{row_year}.{row_month}",
                    "foreign_exchange_sdr": parse_float(cells[1]),
                    "imf_reserve_position_sdr": parse_float(cells[2]),
                    "sdr_sdr": parse_float(cells[3]),
                    "gold_usd": parse_float(cells[4]),
                    "gold_oz": int(parse_float(cells[5])),
                    "other_reserves_sdr": parse_float(cells[6]),
                }
                records.append(record)
            except (ValueError, IndexError):
                continue

    return records


def parse_table(html: str, year: str) -> list:
    """Parse table using best available method."""
    if HAS_BS4:
        return parse_table_bs4(html, year)
    return parse_table_regex(html, year)


def discover_new_year_urls() -> dict:
    """
    Check the SAFE index page for any new year URLs not in SOURCE_URLS.
    Returns dict of {year: url} for newly discovered years.
    """
    new_urls = {}
    index_url = "https://www.safe.gov.cn/safe/whcb/index.html"
    try:
        html = fetch_url(index_url)
        # Match links like: <a href="/safe/2027/...html">官方储备资产（2027年）</a>
        pattern = re.compile(
            r'href=["\']([^"\']+)["\'][^>]*>[^<]*官方储备资产[^<]*\((\d{4})年\)',
            re.IGNORECASE
        )
        for url, yr in pattern.findall(html):
            if yr not in SOURCE_URLS:
                if not url.startswith("http"):
                    url = "https://www.safe.gov.cn" + url
                new_urls[yr] = url
                print(f"  Discovered new year: {yr} -> {url}")
    except Exception as e:
        print(f"  Warning: index page discovery failed: {e}", file=sys.stderr)
    return new_urls


def load_existing_data() -> dict:
    """Load existing JSON data file."""
    if os.path.exists(JSON_PATH):
        with open(JSON_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return {
        "title": "中国官方储备资产数据",
        "source": "国家外汇管理局 (SAFE)",
        "url": "https://www.safe.gov.cn/safe/whcb/index.html",
        "unit_sdr": "亿SDR",
        "unit_gold_usd": "亿美元",
        "unit_gold_oz": "万盎司",
        "source_urls": {},
        "data": [],
    }


def save_data(data: dict, has_new_data: bool = False):
    """Save data to JSON and CSV files."""
    os.makedirs(DATA_DIR, exist_ok=True)
    data["data"].sort(key=lambda x: x["date"])
    # Only update timestamp when data actually changed
    if has_new_data or "last_updated" not in data:
        data["last_updated"] = date.today().isoformat()

    with open(JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    with open(CSV_PATH, "w", encoding="utf-8") as f:
        header = "date,foreign_exchange_sdr,imf_reserve_position_sdr,sdr_sdr,gold_usd,gold_oz,other_reserves_sdr"
        f.write(header + "\n")
        for r in data["data"]:
            line = (
                f"{r['date']},{r['foreign_exchange_sdr']},"
                f"{r['imf_reserve_position_sdr']},{r['sdr_sdr']},"
                f"{r['gold_usd']},{r['gold_oz']},{r['other_reserves_sdr']}"
            )
            f.write(line + "\n")

    print(f"Saved {len(data['data'])} records")


def main():
    """Main: fetch all year pages, parse, merge, save."""
    existing = load_existing_data()
    existing_dates = {r["date"] for r in existing["data"]}

    # Build URL list: known + discover new
    urls = dict(SOURCE_URLS)
    new_urls = discover_new_year_urls()
    urls.update(new_urls)

    all_records = []
    new_count = 0

    for year in sorted(urls.keys()):
        url = urls[year]
        print(f"Fetching {year}: {url}")
        try:
            html = fetch_url(url)
            records = parse_table(html, year)
            print(f"  Parsed {len(records)} records")

            if not records:
                # Page fetched OK but no records parsed — preserve existing
                preserved = [r for r in existing["data"] if r["date"].startswith(year + ".")]
                if preserved:
                    print(f"  WARNING: 0 parsed, keeping {len(preserved)} existing for {year}",
                          file=sys.stderr)
                    records = preserved

            for r in records:
                if r["date"] not in existing_dates:
                    new_count += 1
                    print(f"  + NEW: {r['date']} gold_usd={r['gold_usd']} gold_oz={r['gold_oz']}")
            all_records.extend(records)
        except Exception as e:
            print(f"  ERROR fetching {year}: {e}", file=sys.stderr)
            # Preserve existing data for failed years
            preserved = [r for r in existing["data"] if r["date"].startswith(year + ".")]
            if preserved:
                print(f"  Keeping {len(preserved)} existing records for {year}")
                all_records.extend(preserved)

    data = {
        "title": existing["title"],
        "source": existing["source"],
        "url": existing["url"],
        "unit_sdr": existing["unit_sdr"],
        "unit_gold_usd": existing["unit_gold_usd"],
        "unit_gold_oz": existing["unit_gold_oz"],
        "source_urls": urls,
        "data": all_records,
    }

    save_data(data, has_new_data=(new_count > 0))

    updated = new_count > 0
    print(f"\nTotal: {len(all_records)} records, {new_count} new")
    print(f"DATA_UPDATED={'true' if updated else 'false'}")

    # GitHub Actions output
    gh_output = os.environ.get("GITHUB_OUTPUT", "")
    if gh_output:
        with open(gh_output, "a", encoding="utf-8") as f:
            f.write(f"updated={'true' if updated else 'false'}\n")
            f.write(f"new_records={new_count}\n")


if __name__ == "__main__":
    main()
