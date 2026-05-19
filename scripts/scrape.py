"""
AutoScout24 scraper for Toyota Yaris 2005-2008 listings in Germany.

Usage:
    python scrape.py --proxies '[{"proxy_address":"1.2.3.4","port":8080,"username":"u","password":"p"}]'
    python scrape.py --proxies '[...]' --pages 3
"""

import argparse
import base64
import json
import os
import random
import sys
import time
from datetime import datetime, timezone
from itertools import cycle
from pathlib import Path

import httpx
from bs4 import BeautifulSoup

USAGE_LOG_PATH = Path(__file__).parent.parent / "usage_log.jsonl"


class UsageTracker:
    def __init__(self):
        self.requests: list[dict] = []
        self.session_start = datetime.now(timezone.utc)

    def record(self, *, proxy: str, url: str, status: int | None, size_bytes: int, latency_ms: float, success: bool):
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "proxy": proxy,
            "url": url,
            "status": status,
            "size_bytes": size_bytes,
            "latency_ms": round(latency_ms, 1),
            "success": success,
        }
        self.requests.append(entry)

    def flush(self):
        session = {
            "session_start": self.session_start.isoformat(),
            "session_end": datetime.now(timezone.utc).isoformat(),
            "total_requests": len(self.requests),
            "successful_requests": sum(1 for r in self.requests if r["success"]),
            "total_bytes": sum(r["size_bytes"] for r in self.requests),
            "requests": self.requests,
        }
        with open(USAGE_LOG_PATH, "a") as f:
            f.write(json.dumps(session, ensure_ascii=False) + "\n")
        total_kb = session["total_bytes"] / 1024
        print(
            f"[USAGE] Session: {session['total_requests']} requests, "
            f"{total_kb:.1f} KB transferred, "
            f"{session['successful_requests']}/{session['total_requests']} succeeded. "
            f"Log: {USAGE_LOG_PATH}",
            file=sys.stderr,
        )


tracker = UsageTracker()

BASE_URL = "https://www.autoscout24.com/lst/toyota/yaris"
DEFAULT_PARAMS = {
    "sort": "age",
    "desc": "1",
    "ustate": "N,U",
    "atype": "C",
    "cy": "D",
    "fregfrom": "2005",
    "fregto": "2008",
    "damaged_listing": "exclude",
}

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:128.0) Gecko/20100101 Firefox/128.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:128.0) Gecko/20100101 Firefox/128.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36 Edg/125.0.0.0",
]


def build_proxy_url(proxy: dict) -> str:
    username = proxy["username"]
    password = proxy["password"]
    address = proxy["proxy_address"]
    port = proxy["port"]
    return f"http://{username}:{password}@{address}:{port}"


def fetch_page(page_num: int, proxy_url: str) -> str | None:
    params = {**DEFAULT_PARAMS, "page": str(page_num)}
    headers = {
        "User-Agent": random.choice(USER_AGENTS),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9,de;q=0.8",
        "Accept-Encoding": "gzip, deflate, br",
        "DNT": "1",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
    }

    proxy_host = proxy_url.split("@")[1] if "@" in proxy_url else proxy_url
    request_url = f"{BASE_URL}?page={page_num}"
    start = time.perf_counter()
    try:
        with httpx.Client(
            proxy=proxy_url,
            timeout=30.0,
            follow_redirects=True,
        ) as client:
            response = client.get(BASE_URL, params=params, headers=headers)
            latency = (time.perf_counter() - start) * 1000
            response.raise_for_status()
            tracker.record(
                proxy=proxy_host, url=request_url,
                status=response.status_code, size_bytes=len(response.content),
                latency_ms=latency, success=True,
            )
            return response.text
    except httpx.HTTPError as e:
        latency = (time.perf_counter() - start) * 1000
        tracker.record(
            proxy=proxy_host, url=request_url,
            status=None, size_bytes=0, latency_ms=latency, success=False,
        )
        print(f"[WARN] Request failed with proxy {proxy_host}: {e}", file=sys.stderr)
        return None


def parse_listings(html: str) -> list[dict]:
    soup = BeautifulSoup(html, "lxml")

    listings = parse_from_next_data(soup)
    if listings:
        return listings

    results = []
    articles = soup.find_all("article")
    if not articles:
        articles = soup.find_all("div", attrs={"data-testid": lambda v: v and "listing" in v.lower()})

    for article in articles:
        listing = extract_listing_from_article(article)
        if listing and listing.get("title"):
            results.append(listing)

    return results


def extract_listing_from_article(article) -> dict | None:
    listing = {}

    title_el = article.find("h2") or article.find("a", attrs={"title": True})
    if title_el:
        if title_el.get("title"):
            listing["title"] = title_el["title"].strip()
        else:
            listing["title"] = title_el.get_text(strip=True)

    for a_tag in article.find_all("a", href=True):
        href = a_tag.get("href", "")
        if "/offers/" in href or "/angebote/" in href:
            if href.startswith("/"):
                href = f"https://www.autoscout24.com{href}"
            listing["url"] = href.split("?")[0]
            break

    img_el = article.find("img", src=True)
    if not img_el:
        img_el = article.find("img", attrs={"data-src": True})
    if img_el:
        src = img_el.get("src") or img_el.get("data-src", "")
        if src and src.startswith("http"):
            listing["thumbnail"] = src

    price_el = (
        article.find(attrs={"data-testid": lambda v: v and "price" in v.lower()})
        or article.find("p", class_=lambda c: c and "price" in " ".join(c).lower())
        or article.find("span", class_=lambda c: c and "price" in " ".join(c).lower())
    )
    if price_el:
        listing["price"] = price_el.get_text(strip=True)

    details = article.find_all("span")
    detail_texts = [s.get_text(strip=True) for s in details if s.get_text(strip=True)]

    for text in detail_texts:
        if "/" in text and len(text) <= 7 and any(c.isdigit() for c in text):
            if not listing.get("year"):
                listing["year"] = text
        elif "km" in text.lower() and any(c.isdigit() for c in text):
            if not listing.get("mileage"):
                listing["mileage"] = text
        elif text in ("Gasoline", "Diesel", "Electric/Gasoline", "Electric", "LPG", "CNG", "Hydrogen"):
            if not listing.get("fuel"):
                listing["fuel"] = text
        elif "kW" in text and "hp" in text:
            if not listing.get("power"):
                listing["power"] = text

    seller_el = article.find(attrs={"data-testid": lambda v: v and "seller" in v.lower()})
    if seller_el:
        listing["seller"] = seller_el.get_text(strip=True)

    location_texts = [t for t in detail_texts if t.startswith("DE-") or t.startswith("AT-")]
    if location_texts:
        listing["location"] = location_texts[0]

    if not listing.get("location"):
        for text in detail_texts:
            if len(text) > 4 and any(prefix in text for prefix in ("DE-", "DE ", "AT-", "NL-", "IT-", "FR-", "BE-", "ES-")):
                listing["location"] = text
                break

    return listing if listing.get("title") else None


def parse_from_next_data(soup) -> list[dict]:
    """Parse listings from Next.js __NEXT_DATA__ embedded JSON."""
    script_tag = soup.find("script", id="__NEXT_DATA__")
    if not script_tag:
        return []

    try:
        data = json.loads(script_tag.string)
        props = data.get("props", {}).get("pageProps", {})
        listing_data = props.get("listings", []) or props.get("searchResult", {}).get("listings", [])

        listings = []
        for item in listing_data:
            vehicle = item.get("vehicle", {})
            price_obj = item.get("price", {})
            location_obj = item.get("location", {})
            seller_obj = item.get("seller", {})
            tracking = item.get("tracking", {})
            vehicle_details = item.get("vehicleDetails", [])

            make = vehicle.get("make", "")
            model = vehicle.get("model", "")
            version = vehicle.get("modelVersionInput", "")
            title = f"{make} {model} {version}".strip() if version else f"{make} {model}"

            listing = {"title": title.strip()}

            if isinstance(price_obj, dict):
                listing["price"] = price_obj.get("priceFormatted", "")
            elif isinstance(price_obj, str):
                listing["price"] = price_obj

            detail_map = {}
            for detail in vehicle_details:
                label = detail.get("ariaLabel", "").lower()
                detail_map[label] = detail.get("data", "")

            listing["year"] = detail_map.get("first registration", tracking.get("firstRegistration", ""))
            listing["mileage"] = detail_map.get("mileage", vehicle.get("mileageInKm", ""))
            listing["fuel"] = detail_map.get("fuel type", vehicle.get("fuel", ""))
            listing["power"] = detail_map.get("power", "")

            listing["seller"] = seller_obj.get("companyName", "") or seller_obj.get("contactName", "")

            country = location_obj.get("countryCode", "") if isinstance(location_obj, dict) else ""
            city = location_obj.get("city", "") if isinstance(location_obj, dict) else ""
            zip_code = location_obj.get("zip", "") if isinstance(location_obj, dict) else ""
            listing["location"] = f"{country}-{zip_code} {city}".strip() if country else city

            url = item.get("url", "") or item.get("detailUrl", "")
            if url and not url.startswith("http"):
                url = f"https://www.autoscout24.com{url}"
            listing["url"] = url

            images = item.get("images", [])
            listing["thumbnail"] = images[0] if images else ""

            if listing["title"]:
                listings.append(listing)

        return listings
    except (json.JSONDecodeError, KeyError, TypeError):
        return []


def download_thumbnail(url: str, client: httpx.Client) -> str:
    """Download a thumbnail and return it as a base64 data URI."""
    if not url:
        return ""
    try:
        resp = client.get(url, timeout=10)
        resp.raise_for_status()
        content_type = resp.headers.get("content-type", "image/webp")
        if ";" in content_type:
            content_type = content_type.split(";")[0].strip()
        b64 = base64.b64encode(resp.content).decode()
        return f"data:{content_type};base64,{b64}"
    except (httpx.HTTPError, Exception):
        return ""


def fetch_detail_page(url: str, proxy_url: str) -> str | None:
    """Fetch an individual listing detail page."""
    headers = {
        "User-Agent": random.choice(USER_AGENTS),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9,de;q=0.8",
        "DNT": "1",
        "Connection": "keep-alive",
    }
    proxy_host = proxy_url.split("@")[1] if "@" in proxy_url else proxy_url
    start = time.perf_counter()
    try:
        with httpx.Client(proxy=proxy_url, timeout=30.0, follow_redirects=True) as client:
            response = client.get(url, headers=headers)
            latency = (time.perf_counter() - start) * 1000
            response.raise_for_status()
            tracker.record(
                proxy=proxy_host, url=url,
                status=response.status_code, size_bytes=len(response.content),
                latency_ms=latency, success=True,
            )
            return response.text
    except httpx.HTTPError:
        latency = (time.perf_counter() - start) * 1000
        tracker.record(
            proxy=proxy_host, url=url,
            status=None, size_bytes=0, latency_ms=latency, success=False,
        )
        return None


def extract_description(html: str) -> str:
    """Extract vehicle description text from a detail page."""
    soup = BeautifulSoup(html, "lxml")

    for heading in soup.find_all(["h2", "h3"]):
        heading_text = heading.get_text(strip=True).lower()
        if any(kw in heading_text for kw in ("vehicle description", "beschreibung", "description du véhicule")):
            section = heading.find_parent("section")
            if section:
                full_text = section.get_text(separator=" ", strip=True)
                heading_str = heading.get_text(strip=True)
                if full_text.startswith(heading_str):
                    full_text = full_text[len(heading_str):].strip()
                return full_text

            title_container = heading.parent
            content_sibling = title_container.find_next_sibling()
            if content_sibling:
                return content_sibling.get_text(separator=" ", strip=True)

    script_tag = soup.find("script", id="__NEXT_DATA__")
    if script_tag:
        try:
            data = json.loads(script_tag.string)
            props = data.get("props", {}).get("pageProps", {})
            listing_obj = props.get("listing", {}) or props.get("listingDetails", {})
            desc = listing_obj.get("description", "") or listing_obj.get("vehicleDescription", "")
            if desc:
                return desc
        except (json.JSONDecodeError, KeyError, TypeError, AttributeError):
            pass

    return ""


def enrich_with_descriptions(listings: list[dict], proxy_urls: list[str]) -> None:
    """Fetch detail pages and add description to each listing."""
    proxy_cycle_detail = cycle(proxy_urls)
    for i, listing in enumerate(listings):
        url = listing.get("url", "")
        if not url:
            listing["description"] = ""
            continue

        proxy_url = next(proxy_cycle_detail)
        print(f"[INFO] Fetching detail {i+1}/{len(listings)}: {url.split('/')[-1][:40]}...", file=sys.stderr)

        html = fetch_detail_page(url, proxy_url)
        if html:
            listing["description"] = extract_description(html)
        else:
            listing["description"] = ""

        time.sleep(random.uniform(1.0, 2.5))


def main():
    parser = argparse.ArgumentParser(description="Scrape AutoScout24 for Toyota Yaris 2005-2008")
    parser.add_argument("--proxies", required=True, help="JSON array of proxy objects")
    parser.add_argument("--pages", type=int, default=1, help="Number of pages to scrape (default: 1)")
    parser.add_argument("--embed-thumbnails", action="store_true", help="Download thumbnails and embed as base64 data URIs")
    parser.add_argument("--fetch-descriptions", action="store_true", help="Fetch each listing's detail page for vehicle description and rust flags")
    args = parser.parse_args()

    try:
        proxies = json.loads(args.proxies)
    except json.JSONDecodeError as e:
        print(f"Error: Invalid JSON for --proxies: {e}", file=sys.stderr)
        sys.exit(1)

    if not proxies:
        print("Error: No proxies provided", file=sys.stderr)
        sys.exit(1)

    proxy_urls = [build_proxy_url(p) for p in proxies]
    proxy_cycle = cycle(proxy_urls)

    all_listings = []
    pages_fetched = 0

    for page_num in range(1, args.pages + 1):
        proxy_url = next(proxy_cycle)
        print(f"[INFO] Fetching page {page_num} via {proxy_url.split('@')[1]}...", file=sys.stderr)

        html = fetch_page(page_num, proxy_url)
        if html is None:
            proxy_url = next(proxy_cycle)
            print(f"[INFO] Retrying page {page_num} via {proxy_url.split('@')[1]}...", file=sys.stderr)
            html = fetch_page(page_num, proxy_url)

        if html:
            listings = parse_listings(html)
            all_listings.extend(listings)
            pages_fetched += 1
            print(f"[INFO] Page {page_num}: found {len(listings)} listings", file=sys.stderr)
        else:
            print(f"[WARN] Failed to fetch page {page_num} after retry", file=sys.stderr)

        if page_num < args.pages:
            delay = random.uniform(1.0, 3.0)
            time.sleep(delay)

    if args.fetch_descriptions and all_listings:
        enrich_with_descriptions(all_listings, proxy_urls)

    if args.embed_thumbnails and all_listings:
        print(f"[INFO] Downloading {len(all_listings)} thumbnails...", file=sys.stderr)
        with httpx.Client(follow_redirects=True) as client:
            for listing in all_listings:
                thumb_url = listing.get("thumbnail", "")
                listing["thumbnail"] = download_thumbnail(thumb_url, client)

    result = {
        "listings": all_listings,
        "meta": {
            "total_found": len(all_listings),
            "scraped_at": datetime.now(timezone.utc).isoformat(),
            "proxies_used": len(proxies),
            "pages_fetched": pages_fetched,
        },
    }

    tracker.flush()
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
