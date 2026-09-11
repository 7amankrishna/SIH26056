"""Standalone OTA scrape-to-CSV CLI.

Runs the Cleartrip / EaseMyTrip scrapers outside the API, writing a CSV in the
schema the `ankit70808` project produced (so it can also feed the "bring your
own data" import path, `data/` or `python -m app.custom_data --import`):

    python -m app.collect.ota.cli --source cleartrip --routes DEL-BOM,BLR-DEL \
        --lead-times 1,7,30 --out data/ota_cleartrip.csv

Unlike the original ankit scripts, the CLI actually honours its arguments
(route list, lead-time window, source, output path, headless toggle).
"""

from __future__ import annotations

import argparse
import csv
import random
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path

from .extractors import (
    EASEMYTRIP_EXTRACT_JS,
    build_cleartrip_url,
    build_easemytrip_url,
    parse_cleartrip_cards,
    parse_easemytrip_cards,
)

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Safari/605.1.15",
]

CSV_FIELDS = [
    "Origin", "Destination", "Airline name", "Flight_code", "Stops", "Travel_date",
    "Departure_time", "Arrival_time", "Duration", "Fare", "Base price", "GST",
    "Currency", "Seats_left", "Scraped_at time", "Source",
]

DEFAULT_ROUTES = [
    "DEL-BOM", "BLR-DEL", "BLR-BOM", "DEL-HYD", "DEL-PNQ", "DEL-CCU",
    "AMD-DEL", "MAA-DEL", "HYD-BOM", "BLR-CCU",
]


def _to_csv_row(payload: dict) -> dict:
    stops = payload.get("stops")
    return {
        "Origin": payload["origin"],
        "Destination": payload["destination"],
        "Airline name": payload.get("airline") or "Unknown",
        "Flight_code": payload.get("flight_number") or "Unknown",
        "Stops": "Non-stop" if stops == 0 else (f"{stops} stop" if stops else "Unknown"),
        "Travel_date": payload["departure_date"],
        "Departure_time": payload.get("departure_time"),
        "Arrival_time": payload.get("arrival_time"),
        "Duration": payload.get("duration"),
        "Fare": payload["total_fare"],
        "Base price": payload["base_fare"],
        "GST": payload["taxes"],
        "Currency": payload["currency"],
        "Seats_left": payload.get("seats_remaining"),
        "Scraped_at time": payload.get("scraped_at"),
        "Source": payload.get("source_label"),
    }


def scrape_one(playwright, browser, site: str, origin: str, dest: str, travel_date: str, headless: bool) -> list[dict]:
    context = browser.new_context(user_agent=random.choice(USER_AGENTS), viewport={"width": 1366, "height": 768})
    page = context.new_page()
    try:
        if site == "cleartrip":
            url = build_cleartrip_url(origin, dest, travel_date)
            page.goto(url, wait_until="domcontentloaded", timeout=60000)
            page.wait_for_timeout(10000)
            card_texts = page.locator("div").all_inner_texts()
            return parse_cleartrip_cards(card_texts, origin, dest, travel_date)
        url = build_easemytrip_url(origin, dest, travel_date)
        page.goto(url, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(8000)
        raw_cards = page.evaluate(EASEMYTRIP_EXTRACT_JS)
        return parse_easemytrip_cards(raw_cards, origin, dest, travel_date)
    finally:
        page.close()
        context.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="OTA airfare scrape-to-CSV (Cleartrip / EaseMyTrip)")
    parser.add_argument("--source", choices=["cleartrip", "easemytrip"], default="cleartrip")
    parser.add_argument("--routes", default=",".join(DEFAULT_ROUTES),
                        help="comma-separated ORIGIN-DEST pairs (default: top 10)")
    parser.add_argument("--lead-times", default="1,7,15,30,45",
                        help="comma-separated advance-purchase windows in days")
    parser.add_argument("--out", default="data/ota_scrape.csv", help="output CSV path")
    parser.add_argument("--headless", dest="headless", action="store_true", default=True)
    parser.add_argument("--headed", dest="headless", action="store_false", help="show the browser window")
    parser.add_argument("--delay", type=float, default=3.0, help="seconds between searches")
    args = parser.parse_args(argv)

    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        print(f"playwright is not installed: {exc}", file=sys.stderr)
        return 2

    routes = [r.strip().upper() for r in args.routes.split(",") if r.strip()]
    lead_times = [int(x) for x in args.lead_times.split(",") if x.strip()]
    today = datetime.now()
    dates = [(today + timedelta(days=d)).strftime("%Y-%m-%d") for d in lead_times]

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    append = out_path.exists()

    total = len(routes) * len(dates)
    written = 0
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=args.headless)
        try:
            with open(out_path, "a", newline="", encoding="utf-8") as fh:
                writer = csv.DictWriter(fh, fieldnames=CSV_FIELDS)
                if not append:
                    writer.writeheader()
                for i, (origin, dest) in enumerate(routes):
                    for travel_date in dates:
                        print(f"[{i * len(dates) + dates.index(travel_date) + 1}/{total}] {origin}->{dest} on {travel_date} ...")
                        try:
                            rows = scrape_one(p, browser, args.source, origin, dest, travel_date, args.headless)
                        except Exception as exc:  # one bad search must not kill the run
                            print(f"  error on {origin}->{dest} {travel_date}: {exc}")
                            rows = []
                        for payload in rows:
                            writer.writerow(_to_csv_row(payload))
                            written += 1
                        time.sleep(args.delay)
        finally:
            browser.close()

    print(f"done: {written} rows -> {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
