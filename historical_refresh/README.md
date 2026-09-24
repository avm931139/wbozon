# Historical refresh

The worker reloads mutable financial and advertising history and then rebuilds
`fact_sales`, source lineage, product barcodes and daily product economics for
each selected marketplace. Existing raw rows are updated/replaced by stable API
keys; nothing is deleted merely because it is outside the requested period.

Full one-time backfill from the configured marketplace history floors:

```bash
python -m historical_refresh --mode full --marketplace all
```

Daily production refresh of the last `HISTORY_REFRESH_LOOKBACK_DAYS` (120 by
default):

```bash
python -m historical_refresh --mode rolling --marketplace all
```

An explicit range is supported with `--date-from` and `--date-to`. Yandex
Market advertising is additionally capped by `YANDEX_MARKET_AD_HISTORY_DAYS`,
because the cabinet plan exposes only that rolling window. Ozon advertising is
skipped, without failing finance, when Performance API credentials are absent.
Yandex historical requests use `YANDEX_MARKET_HISTORY_REQUEST_PAUSE_SECONDS`
and exponential 429 backoff configured by `YANDEX_MARKET_RATE_LIMIT_*`.

The Ozon historical mode deliberately reloads details for already stored
postings. This is required to capture late returns and corrections that the
ordinary three-day incremental overlap cannot see.

WB finance and Ozon daily accruals are fetched in 31-day chunks. The chunking
does not shorten history; it prevents a full-year API response from exhausting
memory on a small VPS.
