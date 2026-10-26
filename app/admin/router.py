# -*- coding: utf-8 -*-
"""Private admin dashboard for registrations, plans and traffic."""

from __future__ import annotations

import csv
import html
import secrets
from datetime import datetime, timedelta, timezone
from io import StringIO
from string import Template
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Response, status
from fastapi.responses import HTMLResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.limits import get_plan_limits
from app.db import models
from app.db.session import get_db
from app.usage.service import sync_usage_limit

router = APIRouter(tags=["admin"])
basic_auth = HTTPBasic(realm="Data Cleaner Admin")
try:
    LOCAL_TZ = ZoneInfo("Europe/Madrid")
except Exception:  # pragma: no cover - fallback for systems without tzdata
    LOCAL_TZ = timezone.utc


def require_admin(credentials: HTTPBasicCredentials = Depends(basic_auth)) -> str:
    user_ok = secrets.compare_digest(credentials.username, settings.ADMIN_USER)
    password_ok = secrets.compare_digest(credentials.password, settings.ADMIN_PASSWORD)
    if not (user_ok and password_ok):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Credenciales incorrectas",
            headers={"WWW-Authenticate": 'Basic realm="Data Cleaner Admin"'},
        )
    return credentials.username


def _e(value) -> str:
    return html.escape("" if value is None else str(value), quote=True)


def _local_time(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(LOCAL_TZ)


def _user_rows(db: Session):
    users = db.query(models.User).order_by(models.User.created_at.desc()).all()
    rows = []
    for user in users:
        membership = (
            db.query(models.OrganizationMember)
            .filter(models.OrganizationMember.user_id == user.id)
            .order_by(models.OrganizationMember.created_at.asc())
            .first()
        )
        org = None
        usage = None
        if membership:
            org = (
                db.query(models.Organization)
                .filter(models.Organization.id == membership.organization_id)
                .first()
            )
            if org:
                usage = sync_usage_limit(db, org)

        plan = (org.plan if org else "free") or "free"
        limits = get_plan_limits(plan)
        is_free = plan.lower() == "free"
        used = int(usage.rows_used or 0) if usage else 0
        limit = int(usage.rows_limit) if usage else int(
            limits.get("uses_month", 10) if is_free else limits["rows_month"]
        )
        rows.append({
            "user": user,
            "org": org,
            "plan": plan,
            "usage": usage,
            "used": used,
            "limit": limit,
            "unit": "usos" if is_free else "filas",
            "subscription": bool(org and org.stripe_subscription_id),
        })
    return rows


def _visit_data(db: Session):
    now_local = datetime.now(timezone.utc).astimezone(LOCAL_TZ)
    today = now_local.date()
    since = datetime.now(timezone.utc) - timedelta(days=35)
    visits = (
        db.query(models.PageVisit)
        .filter(models.PageVisit.created_at >= since)
        .order_by(models.PageVisit.created_at.desc())
        .all()
    )

    daily = {}
    for offset in range(29, -1, -1):
        day = today - timedelta(days=offset)
        daily[day.isoformat()] = {"views": 0, "visitors": set()}

    for visit in visits:
        local = _local_time(visit.created_at)
        if local is None:
            continue
        key = local.date().isoformat()
        if key in daily:
            daily[key]["views"] += 1
            daily[key]["visitors"].add(visit.visitor_id)

    days = [
        {"day": day, "views": values["views"], "visitors": len(values["visitors"])}
        for day, values in daily.items()
    ]
    recent = visits[:100]
    today_data = daily.get(today.isoformat(), {"views": 0, "visitors": set()})
    last_7 = [item for item in days[-7:]]
    return {
        "days": days,
        "recent": recent,
        "today_views": today_data["views"],
        "today_visitors": len(today_data["visitors"]),
        "week_views": sum(item["views"] for item in last_7),
        "week_visitors": len({
            visit.visitor_id for visit in visits
            if (_local_time(visit.created_at) or now_local).date() >= today - timedelta(days=6)
        }),
        "month_visitors": len({
            visit.visitor_id for visit in visits
            if (_local_time(visit.created_at) or now_local).date() >= today - timedelta(days=29)
        }),
    }


def _page(db: Session) -> str:
    users = _user_rows(db)
    traffic = _visit_data(db)
    plans = {"free": 0, "basic": 0, "pro": 0}
    mrr = 0
    for row in users:
        plan = row["plan"].lower()
        plans[plan] = plans.get(plan, 0) + 1
        if row["subscription"]:
            mrr += {"basic": 29, "pro": 49}.get(plan, 0)

    max_views = max((item["views"] for item in traffic["days"]), default=0) or 1
    daily_rows = []
    for item in traffic["days"]:
        width = round(item["views"] / max_views * 100)
        date_label = item["day"][5:]
        daily_rows.append(
            '<tr><td>{}</td><td>{}</td><td>{}</td><td><div class="track"><i style="width:{}%"></i></div></td></tr>'.format(
                _e(date_label), item["views"], item["visitors"], width
            )
        )

    user_rows = []
    for row in users:
        user = row["user"]
        org = row["org"]
        created = _local_time(user.created_at)
        plan = row["plan"].lower()
        plan_class = "plan-" + plan if plan in ("free", "basic", "pro") else "plan-free"
        billing = "Suscripción registrada" if row["subscription"] else "Sin suscripción"
        user_rows.append(
            '<tr class="user-row"><td><strong>{}</strong><small>{}</small></td>'
            '<td><span class="pill {}">{}</span><small>{}</small></td>'
            '<td>{} / {} {}</td><td>{}</td><td>{}</td></tr>'.format(
                _e(user.full_name or "—"), _e(user.email), plan_class, _e(plan.title()),
                _e(billing), row["used"], row["limit"], _e(row["unit"]),
                _e(created.strftime("%d/%m/%Y %H:%M") if created else "—"),
                _e(org.name if org else "Sin organización"),
            )
        )

    visit_rows = []
    for visit in traffic["recent"]:
        created = _local_time(visit.created_at)
        ua = (visit.user_agent or "")[:160]
        referrer = visit.referrer or "Acceso directo / sin referente"
        visit_rows.append(
            '<tr><td>{}</td><td><code>{}</code></td><td>{}</td><td title="{}">{}</td><td><code>{}</code></td></tr>'.format(
                _e(created.strftime("%d/%m/%Y %H:%M:%S") if created else "—"),
                _e(visit.path), _e(referrer), _e(ua), _e(ua), _e(visit.visitor_id[:8]),
            )
        )

    total_users = len(users)
    return Template("""<!doctype html>
<html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex,nofollow"><title>Administración · Data Cleaner B2B</title>
<style>
:root{color-scheme:light;--ink:#142033;--muted:#64748b;--line:#e2e8f0;--green:#059669;--bg:#f5f7fb}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:14px/1.45 system-ui,-apple-system,Segoe UI,sans-serif}
header{background:#0f172a;color:white;padding:22px max(24px,calc((100vw - 1320px)/2));display:flex;justify-content:space-between;align-items:center;gap:20px}
header h1{font-size:20px;margin:0}header p{margin:3px 0 0;color:#cbd5e1;font-size:12px}.wrap{max-width:1320px;margin:26px auto;padding:0 20px}
.cards{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:14px}.card,section{background:white;border:1px solid var(--line);border-radius:13px;box-shadow:0 2px 8px #0f172a08}
.card{padding:17px}.label{font-size:12px;color:var(--muted)}.value{font-size:27px;font-weight:750;margin-top:5px;letter-spacing:-.03em}.hint{font-size:11px;color:var(--muted);margin-top:3px}
section{margin-top:20px;padding:20px}h2{font-size:16px;margin:0 0 4px}section>p{color:var(--muted);font-size:12px;margin:0 0 14px}
.section-head{display:flex;align-items:center;justify-content:space-between;gap:12px;margin-bottom:12px}.actions{display:flex;gap:8px;align-items:center}
a.btn{display:inline-block;border:1px solid var(--line);border-radius:8px;padding:7px 10px;color:#334155;text-decoration:none;font-size:12px;font-weight:650;background:#fff}
input{border:1px solid var(--line);padding:8px 10px;border-radius:8px;min-width:200px;font:inherit}table{border-collapse:collapse;width:100%;font-size:12px}th{text-align:left;color:var(--muted);font-size:11px;text-transform:uppercase;letter-spacing:.04em;background:#f8fafc}
th,td{padding:10px 9px;border-bottom:1px solid #edf1f5;vertical-align:top}tbody tr:last-child td{border-bottom:0}td small{display:block;color:var(--muted);margin-top:3px}.pill{display:inline-block;border-radius:999px;padding:3px 8px;font-size:10px;font-weight:750;text-transform:uppercase;letter-spacing:.03em}
.plan-free{background:#f1f5f9;color:#475569}.plan-basic{background:#dbeafe;color:#1d4ed8}.plan-pro{background:#d1fae5;color:#047857}.scroll{overflow:auto}.track{width:150px;height:8px;background:#f1f5f9;border-radius:10px;overflow:hidden}.track i{display:block;height:100%;background:#10b981;border-radius:10px;min-width:0}
code{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:11px;color:#334155}.muted{color:var(--muted)}.foot{color:var(--muted);font-size:11px;margin:16px 2px}
@media(max-width:900px){.cards{grid-template-columns:repeat(2,1fr)}header{padding:18px 20px}.wrap{margin-top:16px}section{padding:15px}}
@media(max-width:520px){.cards{grid-template-columns:1fr 1fr}.value{font-size:22px}.section-head{align-items:flex-start;flex-direction:column}.actions{width:100%;flex-wrap:wrap}input{min-width:0;flex:1}}
</style></head><body>
<header><div><h1>Data Cleaner B2B · Administración</h1><p>Usuarios, planes y analítica de visitas · zona horaria Europe/Madrid</p></div><a class="btn" href="/" style="color:white;border-color:#475569;background:#1e293b">Ver web</a></header>
<main class="wrap"><div class="cards">
<div class="card"><div class="label">Usuarios registrados</div><div class="value">$total_users</div><div class="hint">Free $free · Basic $basic · Pro $pro</div></div>
<div class="card"><div class="label">Ingresos mensuales estimados</div><div class="value">$mrr €</div><div class="hint">Basic 29 € · Pro 49 €, con suscripción registrada</div></div>
<div class="card"><div class="label">Visitas hoy</div><div class="value">$today_views</div><div class="hint">Personas únicas: $today_visitors</div></div>
<div class="card"><div class="label">Visitas últimos 7 días</div><div class="value">$week_views</div><div class="hint">Personas únicas: $week_visitors</div></div>
<div class="card"><div class="label">Visitas últimos 30 días</div><div class="value">$month_views</div><div class="hint">Personas únicas: $month_visitors</div></div>
</div>
<section><div class="section-head"><div><h2>Tráfico diario · últimos 30 días</h2><p>“Personas únicas” cuenta IDs aleatorios distintos por día; las visitas cuentan cada carga de página.</p></div></div><div class="scroll"><table><thead><tr><th>Fecha</th><th>Visitas</th><th>Personas únicas</th><th>Volumen</th></tr></thead><tbody>$daily_rows</tbody></table></div></section>
<section><div class="section-head"><div><h2>Cuentas y planes</h2><p>La suscripción se muestra cuando Stripe ha registrado una subscription ID en la organización.</p></div><div class="actions"><input id="user-filter" placeholder="Filtrar email, nombre o plan…" oninput="filterUsers()"><a class="btn" href="/admin/export/users.csv">Descargar CSV</a></div></div>
<div class="scroll"><table id="users-table"><thead><tr><th>Usuario</th><th>Plan / Stripe</th><th>Consumo del mes</th><th>Registro</th><th>Organización</th></tr></thead><tbody>$user_rows</tbody></table></div></section>
<section><div class="section-head"><div><h2>Últimas visitas</h2><p>Hasta 100 cargas recientes. No se guarda la dirección IP; el identificador de visitante es aleatorio.</p></div><a class="btn" href="/admin/export/visits.csv">Descargar CSV</a></div>
<div class="scroll"><table><thead><tr><th>Fecha y hora</th><th>Página</th><th>Referente</th><th>Navegador</th><th>ID</th></tr></thead><tbody>$visit_rows</tbody></table></div></section>
<p class="foot">El total de ingresos es una estimación según plan, no un informe contable. Panel privado · credenciales HTTP Basic.</p></main>
<script>function filterUsers(){const q=document.getElementById('user-filter').value.toLowerCase();document.querySelectorAll('.user-row').forEach(r=>r.style.display=r.textContent.toLowerCase().includes(q)?'':'none')}</script>
</body></html>""").substitute(
        total_users=total_users,
        free=plans.get("free", 0), basic=plans.get("basic", 0), pro=plans.get("pro", 0),
        mrr=mrr,
        today_views=traffic["today_views"], today_visitors=traffic["today_visitors"],
        week_views=traffic["week_views"], week_visitors=traffic["week_visitors"],
        month_views=sum(item["views"] for item in traffic["days"]),
        month_visitors=traffic["month_visitors"],
        daily_rows="".join(daily_rows), user_rows="".join(user_rows), visit_rows="".join(visit_rows),
    )


@router.get("/admin", response_class=HTMLResponse)
def admin_dashboard(
    _admin: str = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return HTMLResponse(_page(db), headers={"Cache-Control": "no-store", "X-Robots-Tag": "noindex, nofollow"})


@router.get("/admin/export/users.csv")
def export_users(
    _admin: str = Depends(require_admin),
    db: Session = Depends(get_db),
):
    output = StringIO()
    writer = csv.writer(output)
    writer.writerow(["email", "nombre", "plan", "uso_mes", "limite", "unidad", "registrado", "organizacion", "stripe_subscription"])
    for row in _user_rows(db):
        user, org = row["user"], row["org"]
        created = _local_time(user.created_at)
        writer.writerow([
            user.email, user.full_name or "", row["plan"], row["used"], row["limit"], row["unit"],
            created.isoformat() if created else "", org.name if org else "",
            org.stripe_subscription_id if org else "",
        ])
    content = "\ufeff" + output.getvalue()
    return Response(content, media_type="text/csv; charset=utf-8", headers={
        "Content-Disposition": 'attachment; filename="usuarios.csv"', "Cache-Control": "no-store"
    })


@router.get("/admin/export/visits.csv")
def export_visits(
    _admin: str = Depends(require_admin),
    db: Session = Depends(get_db),
):
    output = StringIO()
    writer = csv.writer(output)
    writer.writerow(["fecha_hora", "pagina", "referente", "navegador", "visitor_id"])
    visits = db.query(models.PageVisit).order_by(models.PageVisit.created_at.desc()).limit(10000).all()
    for visit in visits:
        created = _local_time(visit.created_at)
        writer.writerow([
            created.isoformat() if created else "", visit.path, visit.referrer or "",
            visit.user_agent or "", visit.visitor_id,
        ])
    content = "\ufeff" + output.getvalue()
    return Response(content, media_type="text/csv; charset=utf-8", headers={
        "Content-Disposition": 'attachment; filename="visitas.csv"', "Cache-Control": "no-store"
    })
