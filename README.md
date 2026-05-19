# scrape-autoscout24

A [Cursor skill](https://docs.cursor.com/context/skills) that scrapes [AutoScout24.com](https://www.autoscout24.com/) for Toyota Yaris 2005–2008 car listings in Germany, using [Webshare](https://www.webshare.io/) proxies for request distribution and an LLM for intelligent analysis of vehicle descriptions.

## What it does

1. **Fetches proxies** from your Webshare account via MCP
2. **Scrapes listings** from AutoScout24 search results (Next.js `__NEXT_DATA__` parsing)
3. **Fetches detail pages** for each listing to extract vehicle descriptions
4. **Downloads thumbnails** and embeds them as base64 data URIs
5. **LLM classifies** each description for:
   - **Rust/body condition** — flags "no rust" claims or body concerns
   - **Service history** — detects documented maintenance records
6. **Picks top 5** most reliable options based on holistic analysis
7. **Renders a Cursor Canvas** with interactive table, thumbnails, flags, and highlighted picks

## Requirements

- [Cursor IDE](https://cursor.com/) with skills support
- A Webshare account with an active plan (proxies needed for scraping)
- Webshare MCP server connected (`project-0-webshare-webshare`)
- Python 3.10+ with `httpx`, `beautifulsoup4`, `lxml`

## Usage

Trigger the skill by asking your Cursor agent:

> "Scrape AutoScout24 for Toyota Yaris listings"

or

> "Find Toyota Yaris 2005-2008 advertisements for today"

The agent will execute the full workflow and present results as an interactive canvas.

## Manual script usage

```bash
python scripts/scrape.py \
  --proxies '[{"proxy_address":"1.2.3.4","port":8080,"username":"user","password":"pass"}]' \
  --embed-thumbnails \
  --fetch-descriptions \
  --pages 2
```

### Arguments

| Flag | Description |
|------|-------------|
| `--proxies` | **Required.** JSON array of proxy objects |
| `--pages N` | Number of search result pages to scrape (default: 1, 20 listings/page) |
| `--embed-thumbnails` | Download thumbnails and convert to base64 data URIs |
| `--fetch-descriptions` | Fetch each listing's detail page for vehicle description |

### Output

JSON to stdout:

```json
{
  "listings": [
    {
      "title": "Toyota Yaris 1.0 VVT-i Sol",
      "price": "€ 3,200",
      "year": "06/2006",
      "mileage": "142,000 km",
      "fuel": "Gasoline",
      "power": "51 kW (69 hp)",
      "seller": "Autohaus Meyer",
      "location": "DE-10115 Berlin",
      "url": "https://www.autoscout24.com/offers/...",
      "thumbnail": "data:image/webp;base64,...",
      "description": "Fahrzeug ist komplett rostfrei..."
    }
  ],
  "meta": {
    "total_found": 20,
    "scraped_at": "2026-05-19T12:00:00+00:00",
    "proxies_used": 10,
    "pages_fetched": 1
  }
}
```

## Project structure

```
├── SKILL.md              # Cursor skill definition (agent instructions)
├── USECASES.md           # Example use cases and customization guide
├── README.md             # This file
└── scripts/
    └── scrape.py         # Python scraper (httpx + BeautifulSoup)
```

## How it works

### Scraping strategy

- Parses the `__NEXT_DATA__` JSON embedded in AutoScout24's Next.js pages (more reliable than HTML scraping since listing URLs are client-side rendered)
- Rotates through provided proxies with random User-Agent headers
- Adds 1–3s random delays between requests to avoid detection
- Falls back to HTML article parsing if `__NEXT_DATA__` is unavailable

### LLM analysis (performed by the Cursor agent, not the script)

The Python scraper only fetches raw data. Classification is performed by the LLM agent after scraping:

- **Multilingual understanding** — reads German, Italian, French descriptions natively
- **Semantic reasoning** — e.g., "Unterboden neu versiegelt" (underbody re-sealed) implies prior rust
- **Conservative flagging** — only marks positive/warning when there's clear evidence
- **Holistic ranking** — considers service history, mileage, seller transparency, description quality, and price-to-value ratio

## License

MIT
