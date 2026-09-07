from __future__ import annotations

import json
import logging
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from app.config import DASHBOARD_HOST, DASHBOARD_PORT
from dashboard.service import DashboardService

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)


HTML = r'''<!doctype html><html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Маркетплейсы</title><style>
:root{--bg:#0b1020;--panel:#151c30;--line:#29334d;--text:#eef3ff;--muted:#94a3bd;--a:#6ea8fe;--good:#38d39f;--bad:#ff6b7a}*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--text);font:14px system-ui}header{padding:24px 4vw;border-bottom:1px solid var(--line);display:flex;gap:20px;align-items:end;justify-content:space-between}h1{margin:0;font-size:25px}main{padding:24px 4vw}.filters{display:flex;gap:10px;flex-wrap:wrap}input,button{background:#11182a;color:var(--text);border:1px solid var(--line);border-radius:9px;padding:10px}button{background:var(--a);color:#061020;font-weight:700;cursor:pointer}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:14px;margin:18px 0}.card{background:var(--panel);border:1px solid var(--line);border-radius:14px;padding:17px}.card h3{margin:0 0 12px;color:var(--muted);font-size:12px;text-transform:uppercase}.big{font-size:25px;font-weight:750}.row{display:flex;justify-content:space-between;margin-top:8px;color:var(--muted)}.row b{color:var(--text)}section{background:var(--panel);border:1px solid var(--line);border-radius:14px;padding:18px;margin-top:16px}h2{margin:0 0 16px;font-size:17px}.bars{display:flex;align-items:end;gap:4px;height:190px;border-bottom:1px solid var(--line)}.bar{flex:1;min-width:3px;background:var(--a);border-radius:3px 3px 0 0;position:relative}.bar:hover:after{content:attr(data-tip);position:absolute;bottom:100%;left:0;background:#000;padding:5px;white-space:nowrap;z-index:2}.legend{color:var(--muted);margin-top:10px}.error{color:var(--bad)}@media(max-width:600px){header{align-items:start;flex-direction:column}}
</style></head><body><header><div><h1>МАРКЕТПЛЕЙСЫ</h1><div style="color:var(--muted)">WB · Ozon · Яндекс Маркет</div></div><div class="filters"><input id="from" type="date"><input id="to" type="date"><button onclick="load()">Обновить</button></div></header><main><div id="status"></div><div class="grid" id="markets"></div><div class="grid" id="secondary"></div><section><h2>Заказы по дням</h2><div class="bars" id="chart"></div><div class="legend">Высота столбца — суммарное число заказов трёх площадок</div></section></main><script>
const names={wb:'Wildberries',ozon:'Ozon',yandex_market:'Яндекс Маркет'};const rub=n=>new Intl.NumberFormat('ru-RU',{maximumFractionDigits:0}).format(Number(n||0))+' ₽';const num=n=>new Intl.NumberFormat('ru-RU').format(Number(n||0));
async function load(){let q=new URLSearchParams({from:from.value,to:to.value});status.textContent='Загрузка…';try{let d=await fetch('/api/summary?'+q);if(!d.ok)throw Error(await d.text());d=await d.json();from.value=d.period.from;to.value=d.period.to;let errors=[];markets.innerHTML=Object.entries(d.marketplaces).map(([k,v])=>{if(v.error)errors.push(names[k]+': '+v.error);let turnover=Number(v.revenue||0),spend=Number(d.ads[k]?.spend||0),adRevenue=Number(d.ads[k]?.revenue||0),s=d.supplies[k]||{};return `<div class="card"><h3>${names[k]}</h3><div class="big">${rub(turnover)}</div><div class="row"><span>Заказы</span><b>${num(v.orders)}</b></div><div class="row"><span>Отмены</span><b>${num(v.cancelled)}</b></div><div class="row"><span>Финансовый результат</span><b>${d.finance[k]?rub(d.finance[k].net):'—'}</b></div><div class="row"><span>Остаток</span><b>${num(d.stocks[k]?.units)} шт.</b></div><div class="row"><span>Реклама</span><b>${rub(spend)}</b></div><div class="row"><span>Выручка рекламы</span><b>${rub(adRevenue)}</b></div><div class="row"><span>ROAS</span><b>${spend?(adRevenue/spend).toFixed(2):'—'}</b></div><div class="row"><span>Поставки</span><b>${s.supplies===undefined?'—':num(s.supplies)}</b></div><div class="row"><span>Отправлено / принято</span><b>${s.sent===undefined?'—':num(s.sent)+' / '+num(s.accepted)}</b></div></div>`}).join('');let total=Object.values(d.marketplaces).reduce((a,x)=>a+Number(x.revenue||0),0),spend=Object.values(d.ads).reduce((a,x)=>a+Number(x.spend||0),0);secondary.innerHTML=`<div class="card"><h3>Общий оборот заказов</h3><div class="big">${rub(total)}</div></div><div class="card"><h3>Расход на рекламу</h3><div class="big">${rub(spend)}</div><div class="row"><span>ДРР</span><b>${total?(spend/total*100).toFixed(1):0}%</b></div></div><div class="card"><h3>Цены</h3><div class="big">${num(d.prices.active)}</div><div class="row"><span>В акциях</span><b>${num(d.prices.promotions)}</b></div><div class="row"><span>Ошибочных</span><b>${num(d.prices.invalid)}</b></div></div>`;let days={};d.series.forEach(x=>days[x.day]=(days[x.day]||0)+Number(x.orders));let max=Math.max(1,...Object.values(days));chart.innerHTML=Object.entries(days).map(([day,v])=>`<div class="bar" style="height:${Math.max(2,v/max*100)}%" data-tip="${day}: ${v}"></div>`).join('');status.innerHTML='Период '+d.period.from+' — '+d.period.to+(errors.length?'<p class="error">Часть данных недоступна: '+errors.join('; ')+'</p>':'')}catch(e){status.innerHTML='<p class="error">'+e.message+'</p>'}}
let now=new Date(),first=new Date(now.getFullYear(),now.getMonth(),1);to.value=now.toISOString().slice(0,10);from.value=first.toISOString().slice(0,10);load();</script></body></html>'''


class Handler(BaseHTTPRequestHandler):
    service = DashboardService()
    def do_GET(self):
        parsed = urlparse(self.path)
        try:
            if parsed.path == "/health": self._send(200, b'{"status":"ok"}', "application/json")
            elif parsed.path == "/api/summary":
                query = parse_qs(parsed.query); payload = self.service.summary((query.get("from") or [None])[0], (query.get("to") or [None])[0])
                self._send(200, json.dumps(payload, ensure_ascii=False, default=str).encode(), "application/json")
            elif parsed.path == "/": self._send(200, HTML.encode(), "text/html; charset=utf-8")
            else: self._send(404, b"not found", "text/plain")
        except (ValueError, TypeError) as exc: self._send(400, str(exc).encode(), "text/plain; charset=utf-8")
        except Exception:
            logger.exception("Dashboard request failed: %s", self.path)
            self._send(500, b"internal error", "text/plain")
    def _send(self, status, content, content_type):
        self.send_response(status); self.send_header("Content-Type", content_type); self.send_header("Content-Length", str(len(content))); self.send_header("Cache-Control", "no-store"); self.send_header("X-Content-Type-Options", "nosniff"); self.send_header("X-Frame-Options", "DENY"); self.end_headers(); self.wfile.write(content)
    def log_message(self, fmt, *args): return


if __name__ == "__main__":
    if DASHBOARD_HOST not in {"127.0.0.1", "::1"}: raise RuntimeError("DASHBOARD_HOST must remain loopback-only")
    ThreadingHTTPServer((DASHBOARD_HOST, DASHBOARD_PORT), Handler).serve_forever()
