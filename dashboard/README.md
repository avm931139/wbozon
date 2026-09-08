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
- purchased Ozon items and their amount are reconstructed from financial
  `SaleCommission` accrual details, including returns in the selected financial
  period; WB and Yandex use their respective saved finance/operational sources;
- revenue is purchased-item amount plus saved compensation;
- marketplace expenses contain finance-ledger charges but not product cost;
- profit is revenue minus marketplace expenses and latest imported unit cost;
- stock value is current available quantity multiplied by that unit cost.

WB closed-period buyouts, revenue, expenses and cost of goods use detailed
realization rows. Revenue is retail sales at the agreed seller discount net of
returns plus compensation. Expenses are the difference between that revenue
and the reconstructed net payout, so marketplace commission and every saved
delivery, storage, penalty, deduction and acceptance charge are included once.
Operational sales remain the fallback when WB has not published finance rows
for the selected current period. Ozon revenue is net sales and
returns from posting accrual details plus `NON_ITEM` compensation; expenses are
the difference between that revenue and the complete daily net accrual. This
reproduces the Seller cabinet identity: sales and returns + compensation - all
charges = total accrual. Ozon advertising spend remains a Performance API
campaign metric, while attributed order amount is not labelled as accounting
revenue. Yandex Market calculations use the official payment ledger
(`united-netting`), where accruals are revenue and retentions are expenses.
Until this ledger is synchronized, Yandex finance is deliberately returned as
unavailable; order totals must not be presented as complete profit data.
