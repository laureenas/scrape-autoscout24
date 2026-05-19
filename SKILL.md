---
name: scrape-autoscout24
description: >-
  Scrape AutoScout24.com for Toyota Yaris 2005-2008 car listings in Germany
  using Webshare DE proxies. Use when the user asks to scrape AutoScout24,
  find car listings, or search for Toyota Yaris advertisements.
disable-model-invocation: true
---

# Scrape AutoScout24 for Toyota Yaris 2005-2008

## Prerequisites

- Webshare MCP server (`project-0-webshare-webshare`) must be connected
- User must have an active Webshare plan with DE proxies available

## Workflow

### Step 1: Get the user's plan ID

Call the Webshare MCP tool `list_plans` to discover available plans:

```
CallMcpTool: server=project-0-webshare-webshare, toolName=list_plans
```

Pick the first active plan's `id` field.

### Step 2: Fetch ~10 DE proxies

Call `list_proxies` filtered to Germany:

```
CallMcpTool: server=project-0-webshare-webshare, toolName=list_proxies
arguments: { "plan_id": <PLAN_ID>, "mode": "direct", "country_code__in": "DE", "page_size": 10, "valid": true }
```

Extract from the response an array of proxy objects with fields: `proxy_address`, `port`, `username`, `password`.

### Step 3: Install dependencies and run the scraper

```bash
cd <workspace>/.cursor/skills/scrape-autoscout24
uv pip install httpx beautifulsoup4 lxml --quiet
python scripts/scrape.py --proxies '<JSON_ARRAY_OF_PROXIES>' --embed-thumbnails --fetch-descriptions
```

The `--proxies` argument is a JSON string, e.g.:
```json
[{"proxy_address":"1.2.3.4","port":8080,"username":"user","password":"pass"}, ...]
```

The script outputs a JSON object to stdout:
```json
{
  "listings": [...],
  "meta": { "total_found": 12, "scraped_at": "2026-05-19T12:00:00", "proxies_used": 10, "pages_fetched": 1 }
}
```

Each listing includes a `description` field with the raw vehicle description text (multilingual — German, Italian, French, etc.).

### Step 4: Classify descriptions with LLM

After the scraper returns JSON, analyze each listing's `description` field and assign two flags:

#### `rust_flag`

| Flag | Meaning | Examples of signals |
|------|---------|---------------------|
| `good` | Seller explicitly states no/minimal rust | "rostfrei", "kein Rost", "no rust", "kaum Rost", "rust-free", "Unterboden einwandfrei" |
| `warning` | Body/rust concerns are present or implied | "cosmetic body issues", "Karosserieschäden", "Rostansatz", "frisch lackiert" (suspicious repaint), "Unterbodenschutz erneuert" (underbody re-sealed → likely had rust), "some rust", "Lackmängel" |
| (empty string) | Description doesn't mention body/rust condition | Generic dealer boilerplate, financing info, feature lists |

#### `service_flag`

| Flag | Meaning | Examples of signals |
|------|---------|---------------------|
| `good` | Description indicates documented service history | "Scheckheft gepflegt", "lückenlose Historie", "vollständige Servicehistorie", "full service history", "alle Inspektionen durchgeführt", "service book", "carnet d'entretien" |
| (empty string) | No service history mentioned or unclear | Generic ads, feature lists, no maintenance claims |

**Instructions for the agent:**
- Read each description in its original language (DE/IT/FR/etc.) — do NOT rely on translation
- Use semantic understanding, not keyword matching. E.g. "Der Wagen ist komplett rostfrei" → `rust_flag: good`, "Unterboden wurde neu versiegelt" → `rust_flag: warning` (why re-seal if no rust?)
- For service history: "Scheckheft gepflegt" or "vollständiger Servicehistorie" → `service_flag: good`
- For each listing, set both flags in the data you pass to the canvas
- Be conservative: only flag `good` if there's an explicit positive claim; only flag `warning` if there's a real concern

### Step 5: Pick top 5 most reliable options

After classifying all listings, rank them holistically and select the **5 most reliable** options from today's crop. Consider:

- **Service history** (`service_flag: good`) is a strong positive
- **No body concerns** (`rust_flag` empty or `good`) preferred over `warning`
- **Lower mileage** for the year is better
- **Dealer vs private** — dealers with inspection claims (TÜV, Dekra) are more trustworthy
- **Description quality** — detailed, transparent descriptions (mentioning condition, history, known issues) signal an honest seller; vague one-liners or phone-number-only ads are less reliable
- **Price-to-value** — not cheapest, but reasonable for condition/mileage

For each of the top 5, set `"top_pick": true` in the listing data. Also add a short `"pick_reason"` string (1 sentence, in English) explaining why it was selected. All other listings get `"top_pick": false`.

### Step 6: Render results as a Cursor Canvas

Create a canvas at the standard canvases path with the scraped data embedded inline.

Use these components from `cursor/canvas`:
- `H1`: "Toyota Yaris 2005-2008 — Germany (Today)"
- `Grid` + `Stat`: total listings, price range (min-max), average mileage
- `Table`: columns — Thumbnail, Title, Price, Year, Mileage, Power, Location, Rust
- `Text` footer: scrape timestamp and number of proxies used

**Rust column**: Show the `rust_flag` value with visual indicators:
- `good` → green text or checkmark (e.g. "No rust")
- `warning` → orange/red text or warning icon (e.g. "Body concern")
- empty → grey dash or "—"

**Service column**: Show the `service_flag` value:
- `good` → green text (e.g. "Service book")
- empty → grey dash or "—"

**Top Picks section**: Above the full table, render a highlighted section with the 5 top picks. Show each pick's title (as a link), price, key stats, and the `pick_reason`. Use a visually distinct style (e.g. border, background, or badge) to make them stand out. In the main table, top picks should also have a visual indicator (e.g. star or highlight).

**Clickable rows**: The Title column must be a `<Link>` component wrapping the title text, pointing to the listing's `url` field. This opens the AutoScout24 listing in the browser.

**Thumbnails**: The canvas sandbox blocks external image URLs. The scraper downloads each thumbnail and outputs it as a `data:image/webp;base64,...` data URI. Each row's first column renders an `<img>` element with this embedded data URI, sized at 80x56px with `object-fit: cover` and border-radius 4px. If no thumbnail is available, show a placeholder div with "No image" text using `theme.fill.tertiary` background and `theme.text.tertiary` color.

## Listing Fields

Each listing object from the script contains:

| Field | Type | Example |
|-------|------|---------|
| `title` | string | "Toyota Yaris 1.0 VVT-i Sol" |
| `price` | string | "€ 3,200" |
| `year` | string | "06/2006" |
| `mileage` | string | "142,000 km" |
| `fuel` | string | "Gasoline" |
| `power` | string | "51 kW (69 hp)" |
| `seller` | string | "Autohaus Meyer" |
| `location` | string | "DE-10115 Berlin" |
| `url` | string | "https://www.autoscout24.com/offers/..." |
| `thumbnail` | string | "https://prod.pictures.autoscout24.net/..." |
| `description` | string | "Fahrzeug ist komplett rostfrei..." |
| `rust_flag` | string | `"good"` / `"warning"` / `""` (set by agent in Step 4) |
| `service_flag` | string | `"good"` / `""` (set by agent in Step 4) |
| `top_pick` | boolean | `true` if in top 5 most reliable (set by agent in Step 5) |
| `pick_reason` | string | Short reason for top pick selection (set by agent in Step 5) |

## Notes

- The script sorts by newest first (`sort=age&desc=1`) so today's listings appear at the top
- Only page 1 is fetched by default (20 listings). Pass `--pages N` to fetch more
- The script uses random User-Agent headers and 1-3s delays between requests
- Pass `--embed-thumbnails` to download images and convert to base64 data URIs (required for canvas display since the sandbox blocks external URLs)
- Pass `--fetch-descriptions` to fetch each listing's detail page and extract the vehicle description text
- The scraper only fetches raw descriptions — rust classification is performed by the agent (Step 4) using semantic LLM understanding of multilingual text
- If no listings are found for today specifically, all listings from page 1 are returned with a note
