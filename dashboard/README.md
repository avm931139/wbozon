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

`DASHBOARD_DATABASE_URL` can point to a dedicated PostgreSQL role with `SELECT`
access. If omitted, `DATABASE_URL` is used. A separate read-only role is
recommended in production.

The API endpoints are `/health` and `/api/summary?from=YYYY-MM-DD&to=YYYY-MM-DD`.
The maximum selectable period is 730 days.
