"""A small local-business service marketplace API backed by SQLite."""

from contextlib import asynccontextmanager, contextmanager
from pathlib import Path
import sqlite3
import hmac
import os
import time
from html import escape
from io import StringIO
import csv
import psycopg
from psycopg.rows import dict_row

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from typing import Literal
from starlette.middleware.sessions import SessionMiddleware
from dotenv import load_dotenv


ROOT = Path(__file__).parent
load_dotenv(ROOT / ".env")
APP_ENV = os.getenv("APP_ENV", "development")
DB_PATH = Path(os.getenv("DATABASE_PATH", str(ROOT / "business.db")))
SESSION_SECRET = os.getenv("SESSION_SECRET", "local-development-session-key-change-this")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "local-demo-password" if APP_ENV != "production" else "")
DATABASE_URL = os.getenv("DATABASE_URL", "")
SITE_OPERATOR_NAME = os.getenv("SITE_OPERATOR_NAME", "Website owner (not set)")
PRIVACY_CONTACT_EMAIL = os.getenv("PRIVACY_CONTACT_EMAIL", "privacy contact not set")
REQUEST_RETENTION_DAYS = os.getenv("REQUEST_RETENTION_DAYS", "30")
LOGIN_ATTEMPTS: dict[str, list[float]] = {}
REQUEST_ATTEMPTS: dict[str, list[float]] = {}


class Database:
    """Small adapter that lets the same beginner SQL work with SQLite and Postgres."""

    def __init__(self, connection, is_postgres: bool):
        self.connection = connection
        self.is_postgres = is_postgres

    def execute(self, sql: str, params=()):
        if self.is_postgres:
            sql = sql.replace("?", "%s")
        return self.connection.execute(sql, params)

    def executemany(self, sql: str, rows):
        if self.is_postgres:
            sql = sql.replace("?", "%s")
        return self.connection.cursor().executemany(sql, rows)


@contextmanager
def connect_db():
    """Open, commit or roll back, and always close one database connection."""
    if DATABASE_URL:
        connection = psycopg.connect(DATABASE_URL, row_factory=dict_row, connect_timeout=10)
        db = Database(connection, is_postgres=True)
    else:
        connection = sqlite3.connect(DB_PATH)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 5000")
        db = Database(connection, is_postgres=False)
    try:
        yield db
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def initialize_database() -> None:
    """Create tables in the configured database and seed only local development."""
    if not DATABASE_URL:
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    provider_id = "BIGSERIAL PRIMARY KEY" if DATABASE_URL else "INTEGER PRIMARY KEY AUTOINCREMENT"
    request_id = "BIGSERIAL PRIMARY KEY" if DATABASE_URL else "INTEGER PRIMARY KEY AUTOINCREMENT"
    provider_ref = "BIGINT" if DATABASE_URL else "INTEGER"
    created_at = "TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP" if DATABASE_URL else "TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP"
    with connect_db() as db:
        db.execute(f"""CREATE TABLE IF NOT EXISTS providers (
            id {provider_id}, name TEXT NOT NULL, category TEXT NOT NULL,
            area TEXT NOT NULL, phone TEXT NOT NULL)""")
        db.execute(f"""CREATE TABLE IF NOT EXISTS service_requests (
            id {request_id}, customer_name TEXT NOT NULL, customer_phone TEXT NOT NULL,
            service_id {provider_ref} NOT NULL REFERENCES providers(id), details TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'Pending'
                CHECK(status IN ('Pending', 'Accepted', 'Completed', 'Cancelled')),
            created_at {created_at})""")
        count = db.execute("SELECT COUNT(*) AS total FROM providers").fetchone()["total"]
        if count == 0 and APP_ENV != "production" and not DATABASE_URL:
            db.executemany(
                "INSERT INTO providers (name, category, area, phone) VALUES (?, ?, ?, ?)",
                [
                    ("Riya's Home Repair", "Home repair", "Silchar", "9876500001"),
                    ("Green Leaf Garden Care", "Gardening", "Silchar", "9876500002"),
                    ("QuickFix Electricals", "Electrical", "Silchar", "9876500003"),
                ],
            )


@asynccontextmanager
async def lifespan(_: FastAPI):
    if APP_ENV == "production" and (
        len(ADMIN_PASSWORD) < 16
        or not os.getenv("SESSION_SECRET")
        or not DATABASE_URL.startswith(("postgres://", "postgresql://"))
        or SITE_OPERATOR_NAME == "Website owner (not set)"
        or PRIVACY_CONTACT_EMAIL == "privacy contact not set"
        or not REQUEST_RETENTION_DAYS.isdigit()
        or int(REQUEST_RETENTION_DAYS) < 1
    ):
        raise RuntimeError("Production requires database, owner, privacy, retention, password, and session settings.")
    initialize_database()
    with connect_db() as db:
        cleanup_expired_requests(db)
    yield


app = FastAPI(
    title="Local Business Service Platform",
    description="Find a local service provider and send a service request.",
    version="1.0.0",
    lifespan=lifespan,
)
app.add_middleware(
    SessionMiddleware,
    secret_key=SESSION_SECRET,
    session_cookie="neighbourhood_session",
    same_site="strict",
    https_only=APP_ENV == "production",
    max_age=60 * 60 * 12,
)
app.mount("/static", StaticFiles(directory=ROOT / "static"), name="static")


class ProviderInput(BaseModel):
    name: str = Field(min_length=2, max_length=80)
    category: str = Field(min_length=2, max_length=50)
    area: str = Field(min_length=2, max_length=80)
    phone: str = Field(min_length=7, max_length=20)


class RequestInput(BaseModel):
    customer_name: str = Field(min_length=2, max_length=80)
    customer_phone: str = Field(min_length=7, max_length=20)
    service_id: int = Field(gt=0)
    details: str = Field(min_length=5, max_length=500)
    privacy_consent: bool = False


class StatusInput(BaseModel):
    status: Literal["Pending", "Accepted", "Completed", "Cancelled"]


class AdminLogin(BaseModel):
    password: str = Field(min_length=1, max_length=256)


def require_admin(request: Request):
    if not request.session.get("is_admin"):
        raise HTTPException(status_code=401, detail="Please sign in as the website owner.")


def cleanup_expired_requests(db: Database):
    """Remove old requests on startup and when a visitor or owner uses the site."""
    retention = int(REQUEST_RETENTION_DAYS)
    if db.is_postgres:
        db.execute(
            "DELETE FROM service_requests WHERE created_at < CURRENT_TIMESTAMP - (? * INTERVAL '1 day')",
            (retention,),
        )
    else:
        db.execute(
            "DELETE FROM service_requests WHERE created_at < datetime('now', '-' || ? || ' days')",
            (retention,),
        )


@app.get("/health", include_in_schema=False)
def health():
    with connect_db() as db:
        db.execute("SELECT 1").fetchone()
    return {"status": "ok"}


@app.get("/", include_in_schema=False)
def home():
    return FileResponse(ROOT / "static" / "index.html")


@app.get("/privacy", include_in_schema=False)
def privacy_notice():
    from fastapi.responses import HTMLResponse

    html = (ROOT / "static" / "privacy.html").read_text(encoding="utf-8")
    replacements = {
        "{{site_operator}}": escape(SITE_OPERATOR_NAME),
        "{{privacy_email}}": escape(PRIVACY_CONTACT_EMAIL),
        "{{retention_days}}": escape(REQUEST_RETENTION_DAYS),
    }
    for placeholder, value in replacements.items():
        html = html.replace(placeholder, value)
    return HTMLResponse(html)


@app.get("/api/auth/me")
def admin_session(request: Request):
    return {"is_admin": bool(request.session.get("is_admin"))}


@app.post("/api/auth/admin-login")
def admin_login(payload: AdminLogin, request: Request):
    client_ip = request.client.host if request.client else "unknown"
    now = time.monotonic()
    attempts = [attempt for attempt in LOGIN_ATTEMPTS.get(client_ip, []) if now - attempt < 900]
    LOGIN_ATTEMPTS[client_ip] = attempts
    if len(attempts) >= 5:
        raise HTTPException(status_code=429, detail="Too many attempts. Try again in 15 minutes.")
    if not hmac.compare_digest(payload.password, ADMIN_PASSWORD):
        attempts.append(now)
        LOGIN_ATTEMPTS[client_ip] = attempts
        raise HTTPException(status_code=401, detail="That password did not match.")
    LOGIN_ATTEMPTS.pop(client_ip, None)
    request.session.clear()
    request.session["is_admin"] = True
    return {"is_admin": True}


@app.post("/api/auth/admin-logout")
def admin_logout(request: Request):
    request.session.clear()
    return {"is_admin": False}


@app.get("/api/providers")
def list_providers(request: Request, category: str | None = None, area: str | None = None):
    """List providers, with optional exact category and area filters."""
    query = "SELECT * FROM providers WHERE 1=1"
    values: list[str] = []
    if category:
        query += " AND category = ?"
        values.append(category)
    if area:
        query += " AND area = ?"
        values.append(area)
    query += " ORDER BY name"
    with connect_db() as db:
        cleanup_expired_requests(db)
        rows = [dict(row) for row in db.execute(query, values).fetchall()]
        if request and not request.session.get("is_admin"):
            return [{key: value for key, value in row.items() if key != "phone"} for row in rows]
        return rows


@app.post("/api/providers", status_code=201)
def create_provider(provider: ProviderInput, _: None = Depends(require_admin)):
    with connect_db() as db:
        cursor = db.execute(
            "INSERT INTO providers (name, category, area, phone) VALUES (?, ?, ?, ?) RETURNING id",
            (provider.name, provider.category, provider.area, provider.phone),
        )
        provider_id = cursor.fetchone()["id"]
        return dict(db.execute("SELECT * FROM providers WHERE id = ?", (provider_id,)).fetchone())


@app.put("/api/providers/{provider_id}")
def update_provider(provider_id: int, provider: ProviderInput, _: None = Depends(require_admin)):
    with connect_db() as db:
        cursor = db.execute(
            "UPDATE providers SET name = ?, category = ?, area = ?, phone = ? WHERE id = ?",
            (provider.name, provider.category, provider.area, provider.phone, provider_id),
        )
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="Provider not found")
        return dict(db.execute("SELECT * FROM providers WHERE id = ?", (provider_id,)).fetchone())


@app.delete("/api/providers/{provider_id}", status_code=204)
def delete_provider(provider_id: int, _: None = Depends(require_admin)):
    with connect_db() as db:
        try:
            cursor = db.execute("DELETE FROM providers WHERE id = ?", (provider_id,))
        except (sqlite3.IntegrityError, psycopg.errors.ForeignKeyViolation) as error:
            raise HTTPException(
                status_code=409,
                detail="This provider has service request history and cannot be removed.",
            ) from error
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="Provider not found")


@app.post("/api/requests", status_code=201)
def create_request(payload: RequestInput, request: Request):
    if not payload.privacy_consent:
        raise HTTPException(status_code=400, detail="Please agree to the privacy notice before sending a request.")
    client_ip = request.client.host if request.client else "unknown"
    now = time.monotonic()
    attempts = [attempt for attempt in REQUEST_ATTEMPTS.get(client_ip, []) if now - attempt < 3600]
    if len(attempts) >= 5:
        raise HTTPException(status_code=429, detail="Too many requests from this connection. Please try again later.")
    with connect_db() as db:
        cleanup_expired_requests(db)
        provider = db.execute("SELECT id FROM providers WHERE id = ?", (payload.service_id,)).fetchone()
        if provider is None:
            raise HTTPException(status_code=404, detail="Provider not found")
        db.execute(
            """INSERT INTO service_requests
               (customer_name, customer_phone, service_id, details)
               VALUES (?, ?, ?, ?)""",
            (payload.customer_name, payload.customer_phone, payload.service_id, payload.details),
        )
        attempts.append(now)
        REQUEST_ATTEMPTS[client_ip] = attempts
        return {"message": "Your request was received. The website owner can review it in the management area."}


@app.get("/api/requests")
def list_requests(_: None = Depends(require_admin)):
    with connect_db() as db:
        cleanup_expired_requests(db)
        rows = db.execute(
            """SELECT r.*, p.name AS provider_name, p.category
               FROM service_requests r JOIN providers p ON p.id = r.service_id
               ORDER BY r.created_at DESC, r.id DESC"""
        ).fetchall()
        return [dict(row) for row in rows]


@app.patch("/api/requests/{request_id}/status")
def update_request_status(request_id: int, update: StatusInput, _: None = Depends(require_admin)):
    allowed = {"Pending", "Accepted", "Completed", "Cancelled"}
    if update.status not in allowed:
        raise HTTPException(status_code=400, detail=f"Status must be one of: {', '.join(sorted(allowed))}")
    with connect_db() as db:
        cursor = db.execute(
            "UPDATE service_requests SET status = ? WHERE id = ?", (update.status, request_id)
        )
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="Service request not found")
        row = db.execute(
            """SELECT r.*, p.name AS provider_name, p.category
               FROM service_requests r JOIN providers p ON p.id = r.service_id
               WHERE r.id = ?""",
            (request_id,),
        ).fetchone()
        return dict(row)


@app.get("/api/summary")
def summary(_: None = Depends(require_admin)):
    with connect_db() as db:
        return {
            "providers": db.execute("SELECT COUNT(*) AS total FROM providers").fetchone()["total"],
            "requests": db.execute("SELECT COUNT(*) AS total FROM service_requests").fetchone()["total"],
            "pending": db.execute(
                "SELECT COUNT(*) AS total FROM service_requests WHERE status = 'Pending'"
            ).fetchone()["total"],
            "completed": db.execute(
                "SELECT COUNT(*) AS total FROM service_requests WHERE status = 'Completed'"
            ).fetchone()["total"],
        }


@app.get("/api/admin/requests.csv")
def export_requests(_: None = Depends(require_admin)):
    """Let the owner keep a private manual backup of the free database data."""
    with connect_db() as db:
        cleanup_expired_requests(db)
        rows = db.execute(
            """SELECT r.id, r.created_at, r.customer_name, r.customer_phone,
                      p.name AS provider_name, p.category, r.details, r.status
               FROM service_requests r JOIN providers p ON p.id = r.service_id
               ORDER BY r.created_at DESC, r.id DESC"""
        ).fetchall()
        buffer = StringIO()
        fields = ["id", "created_at", "customer_name", "customer_phone", "provider_name", "category", "details", "status"]
        writer = csv.DictWriter(buffer, fieldnames=fields)
        writer.writeheader()
        writer.writerows(dict(row) for row in rows)
    return StreamingResponse(
        iter([buffer.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=private-service-requests.csv"},
    )


@app.delete("/api/requests/{request_id}", status_code=204)
def delete_request(request_id: int, _: None = Depends(require_admin)):
    with connect_db() as db:
        cursor = db.execute("DELETE FROM service_requests WHERE id = ?", (request_id,))
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="Service request not found")

