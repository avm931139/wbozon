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

The UI is deliberately split into two pages:

- `/` is the operational dashboard. It uses order feeds, postings, order status,
  advertising statistics and current stock snapshots. It never replaces these
  values with finance-report rows and does not calculate accounting profit;
- `/pnl` is the closed finance view. It only exposes values reconstructed from
  the marketplace finance reports saved in PostgreSQL. If the selected period
  is not fully covered, the marketplace card stays unavailable instead of
  falling back to orders or advertising attribution.

The API endpoints are `/health`,
`/api/summary?from=YYYY-MM-DD&to=YYYY-MM-DD` for operations, and
`/api/pnl?from=YYYY-MM-DD&to=YYYY-MM-DD` for finance. The maximum selectable
period is 730 days.

The operational dashboard opens on the latest seven calendar days including
the current Moscow date. Its filter supports both an arbitrary date range and a
month picker; selecting a month immediately loads its first through last day.
For the current month, its end is capped at today; future dates are rejected by
the server so they cannot distort an equal-period comparison.
P&L opens on the previous full calendar month because closed marketplace
finance data is usually not available for the current day. Every period metric
is compared with the immediately preceding period of the same length. Labels
are bilingual Russian/Chinese.

The operational page is ordered for daily sales management:

1. a combined all-marketplace summary: ordered products, purchases,
   cancellations, advertising efficiency and available stock;
2. identical marketplace cards in the order sales, advertising, stock;
3. the daily ordered-product chart for detecting peaks and drops.

Quantity and money comparisons are displayed separately. Ordinary amounts use
percentage change against the immediately preceding equal-length period.
Cancellation rate and DRR are rates, so their changes are shown in percentage
points. Growth in orders, purchases and ROAS is positive; growth in cancellation
rate or DRR is negative. Advertising spend and stock change are neutral because
direction alone does not establish whether the change is good. When the current
day is included, the page explicitly warns that the incomplete day can make the
comparison look lower. Every visible KPI has a hover/focus explanation of its
meaning, formula, source limitation or snapshot semantics.

Operational marketplace cards use these definitions:

- ordered and cancelled product quantities are compared in the same unit;
- order count is shown separately because one order can contain several items;
- cancellation rate is cancelled items divided by ordered items;
- purchases are sale/delivery events registered during the selected dates and
  are not presented as a cohort conversion of orders created in those dates;
- stock value is current available quantity multiplied by that unit cost.

Order cards identify their operational sources: WB Order Feed plus FBO Orders,
Ozon Postings, and Yandex Market Orders API. Marketplace cabinet funnel exports
are cohort analytics and can be recalculated after order creation, so they are
used for reconciliation rather than silently mixed into the realtime series.
The marketplace share is calculated independently for units and money. Average
product price is order amount divided by ordered units; daily average includes
all calendar days in the selected range. Monthly projection is the average
daily order amount in the selected part of the end month multiplied by that
month's calendar-day count. It is an operational run-rate, not revenue or a
sales plan.

P&L cards use these definitions:

- WB uses only detailed realization report rows and is available only when
  synchronized reports cover every date in the requested period;
- Ozon uses the daily accrual ledger and posting-level `SaleCommission` rows;
- Yandex Market uses only the official `united-netting` payment report;
- revenue is positive financial accruals including saved compensation;
- marketplace expenses are all financial retentions and charges, excluding
  product cost;
- net payout before cost is revenue minus marketplace expenses;
- profit is net payout minus the imported product cost associated with the sold
  units found in that same marketplace finance report.

The finance calculation internally retains WB's two modes for compatibility,
but the P&L endpoint accepts only the exact mode. If detailed realization reports cover
the complete selected period, the card uses exact closed-period buyouts,
revenue, expenses and cost of goods. If the period is not yet covered, the card
title says `предварительный расчёт / 初步估算`: orders and purchases come from the
hourly Sales Funnel history, while cancellations retain the realtime Order Feed
source. Preliminary revenue equals the Sales Funnel purchase amount; expenses
and profit remain unavailable until the financial report closes. Revenue in the
exact mode is retail sales at the agreed seller discount net of
returns plus compensation. Expenses are the difference between that revenue
and the reconstructed net payout, so marketplace commission and every saved
delivery, storage, penalty and acceptance charge are included once. Technical
`deduction` and `rebill_logistic_cost` detail fields are not subtracted again:
WB has already reflected their effect in the payable financial operations.
Operational sales remain a fallback only until the first Sales Funnel sync.
Product cost is shown without a redundant `100% coverage` label; a warning is
shown only when one or more purchased items have no imported cost. Ozon revenue is net sales and
returns from posting accrual details plus `NON_ITEM` compensation; expenses are
the difference between that revenue and the complete daily net accrual. This
reproduces the Seller cabinet identity: sales and returns + compensation - all
charges = total accrual. Ozon advertising spend remains a Performance API
campaign metric, while attributed order amount is not labelled as accounting
revenue. Yandex Market calculations use the official payment ledger
(`united-netting`), where accruals are revenue and retentions are expenses.
Until this ledger is synchronized, Yandex finance is deliberately returned as
unavailable; order totals and advertising attribution are never presented as
P&L revenue. Yandex product cost is matched from positive `Начисление`
and negative `Возврат` product rows of the same united-netting report.
