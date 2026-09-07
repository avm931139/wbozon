# Private marketplace dashboard

The dashboard is a separate read-only process. It reads synchronized PostgreSQL
data and never calls marketplace APIs. By design it can only bind to loopback:

```bash
python -m dashboard
curl http://127.0.0.1:17843/health
```

Production access is restricted to the existing OpenVPN network:

```text
browser -> OpenVPN -> https://10.8.0.1:28443 -> Nginx -> 127.0.0.1:17843
```

The Nginx listener is bound only to `10.8.0.1`, requires TLS and HTTP Basic
authentication, and is not exposed on the public VPS address. Files are in
`deploy/nginx/wbozon-dashboard.conf` and
`deploy/systemd/wbozon-dashboard.service`.

On the production VPS, installation is one interactive command (the script asks
for the dashboard password and does not print or store it in the repository):

```bash
sudo bash deploy/install-dashboard.sh anton
```

`DASHBOARD_DATABASE_URL` can point to a dedicated PostgreSQL role with `SELECT`
access. If omitted, `DATABASE_URL` is used. A separate read-only role is
recommended in production.

The API endpoints are `/health` and `/api/summary?from=YYYY-MM-DD&to=YYYY-MM-DD`.
The maximum selectable period is 730 days.

The dashboard opens on the current Moscow date. Every period metric is compared
with the immediately preceding period of the same length (today with yesterday,
seven days with the preceding seven days). Labels are bilingual Russian/Chinese.

Marketplace cards use these definitions:

- orders and cancellations show units, product amount and cancellation rate;
- purchased items are WB `sale` operations or Ozon/Yandex orders from the
  selected cohort whose current status is delivered;
- revenue is purchased-item amount plus saved compensation;
- marketplace expenses contain finance-ledger charges but not product cost;
- profit is revenue minus marketplace expenses and latest imported unit cost;
- stock value is current available quantity multiplied by that unit cost.

WB calculations use detailed realization rows. Ozon calculations use daily
finance accruals. Yandex Market calculations use the official payment ledger
(`united-netting`), where accruals are revenue and retentions are expenses.
Until this ledger is synchronized, Yandex finance is deliberately returned as
unavailable; order totals must not be presented as complete profit data.
