# Use Cases

## Daily car shopping

> "Scrape AutoScout24 for Toyota Yaris listings today"

Run daily to check new listings. The LLM picks the top 5 most reliable options, so you can focus on the best deals without reading 20 German descriptions yourself.

## Rust screening for older cars

> "Find Toyota Yaris ads and flag any with body or rust concerns"

The LLM reads each seller's description in its original language and flags:
- **Body concern** — mentions of cosmetic damage, suspicious repaints, underbody re-sealing
- **No rust** — explicit claims of rust-free condition

This is especially useful for 15–20 year old cars where rust is the #1 hidden problem.

## Service history verification

> "Which listings have documented service history?"

The LLM detects mentions of:
- "Scheckheft gepflegt" (maintained service book)
- "lückenlose Historie" (complete history)
- "vollständige Servicehistorie" (full service history)
- Dealer inspection certifications (TÜV, Dekra)

Cars with documented service history are significantly more reliable purchases.

## Customizing the search

### Different car model

Edit `scripts/scrape.py` — change `BASE_URL` and `DEFAULT_PARAMS`:

```python
BASE_URL = "https://www.autoscout24.com/lst/volkswagen/golf"
DEFAULT_PARAMS = {
    "sort": "age",
    "desc": "1",
    "ustate": "N,U",
    "atype": "C",
    "cy": "D",
    "fregfrom": "2010",
    "fregto": "2015",
    "damaged_listing": "exclude",
}
```

### Different country

Change `cy` in `DEFAULT_PARAMS`:
- `D` = Germany
- `A` = Austria
- `NL` = Netherlands
- `F` = France
- `I` = Italy
- `B` = Belgium
- `E` = Spain
- `L` = Luxembourg

Multiple countries: `"cy": "D,A,NL"`

### More results

Pass `--pages 3` to scrape 60 listings (20 per page). Note: each page adds ~3s of delay plus detail page fetches add ~2s per listing.

### Price range filter

Add to `DEFAULT_PARAMS`:

```python
"pricefrom": "1000",
"priceto": "5000",
```

### Mileage filter

```python
"kmfrom": "0",
"kmto": "150000",
```

## Integration ideas

### Scheduled scraping

Run the scraper on a cron schedule and diff results against previous runs to detect new listings or price drops.

### Notification pipeline

Pipe the JSON output to a script that sends Slack/email alerts when a top-pick listing appears with good rust + service flags.

### Price tracking

Store daily results in a database to track price trends for specific models over time.

## LLM classification examples

### Rust flag: `good`
- "Der Wagen ist komplett rostfrei" → explicitly rust-free
- "Unterboden einwandfrei, kein Rost" → underbody perfect, no rust
- "Kaum Rost, nur minimale Gebrauchsspuren" → minimal rust, usage marks only

### Rust flag: `warning`
- "Unterboden neu versiegelt" → why re-seal if no rust?
- "Frisch lackiert" → suspicious full repaint could hide rust
- "Parkbeschädigung an der Tür" → cosmetic body damage
- "Hinterachse beschädigt" → structural concern

### Service flag: `good`
- "Scheckheft gepflegt, alle Inspektionen beim Toyota-Händler"
- "Lückenlose Historie mit Dekra-Zertifikat"
- "Full service history available, non-smoker vehicle"

### Top pick selection reasoning
The LLM weighs multiple factors together:
- A car with 58,000 km but broken AC is still a top pick (low mileage outweighs minor issue, and seller honesty is a positive signal)
- A car with service book BUT underbody re-sealed gets picked with a note about the trade-off
- The cheapest car isn't automatically a top pick if the description is vague or seller only provides a phone number
