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
import hashlib
import secrets
import re
import psycopg
from psycopg.rows import dict_row

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field
from typing import Literal
from starlette.middleware.sessions import SessionMiddleware
from dotenv import load_dotenv
from matcher import rank_providers


ROOT = Path(__file__).parent
load_dotenv(ROOT / ".env")
APP_ENV = os.getenv("APP_ENV", "development")
DB_PATH = Path(os.getenv("DATABASE_PATH", str(ROOT / "business.db")))
SESSION_SECRET = os.getenv("SESSION_SECRET") or secrets.token_urlsafe(32)
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "")
DATABASE_URL = os.getenv("DATABASE_URL", "")
SITE_OPERATOR_NAME = os.getenv("SITE_OPERATOR_NAME", "Website owner (not set)")
PRIVACY_CONTACT_EMAIL = os.getenv("PRIVACY_CONTACT_EMAIL", "privacy contact not set")
REQUEST_RETENTION_DAYS = os.getenv("REQUEST_RETENTION_DAYS", "30")
DEMO_PROVIDERS_ENABLED = os.getenv(
    "DEMO_PROVIDERS_ENABLED", "true" if APP_ENV == "production" else "false"
).strip().lower() == "true"


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
    sample_type = "BOOLEAN NOT NULL DEFAULT FALSE" if DATABASE_URL else "INTEGER NOT NULL DEFAULT 0"
    rate_window_type = "BIGINT" if DATABASE_URL else "INTEGER"
    with connect_db() as db:
        if db.is_postgres:
            # Keep concurrent web workers from racing the startup schema checks.
            db.execute("SELECT pg_advisory_xact_lock(hashtext(?))", ("barak-valley-connect-schema",))
        db.execute(f"""CREATE TABLE IF NOT EXISTS accounts (
            id {provider_id}, email TEXT NOT NULL UNIQUE, password_hash TEXT NOT NULL,
            role TEXT NOT NULL CHECK(role IN ('customer', 'provider')),
            display_name TEXT NOT NULL, phone TEXT NOT NULL, created_at {created_at})""")
        db.execute(f"""CREATE TABLE IF NOT EXISTS service_categories (
            id {provider_id}, name TEXT NOT NULL UNIQUE, description TEXT NOT NULL DEFAULT '')""")
        db.execute(f"""CREATE TABLE IF NOT EXISTS providers (
            id {provider_id}, name TEXT NOT NULL, category TEXT NOT NULL,
            area TEXT NOT NULL, phone TEXT NOT NULL,
            description TEXT NOT NULL DEFAULT '', skills TEXT NOT NULL DEFAULT '',
            account_id {provider_ref} REFERENCES accounts(id),
            category_id {provider_ref} REFERENCES service_categories(id),
            is_sample {sample_type},
            availability TEXT NOT NULL DEFAULT 'Not specified'
                CHECK(availability IN ('Available', 'Busy', 'Unavailable', 'Not specified')))""")
        db.execute(f"""CREATE TABLE IF NOT EXISTS service_requests (
            id {request_id}, customer_name TEXT NOT NULL, customer_phone TEXT NOT NULL,
            service_id {provider_ref} NOT NULL REFERENCES providers(id), details TEXT NOT NULL,
            customer_id {provider_ref} REFERENCES accounts(id),
            status TEXT NOT NULL DEFAULT 'Pending'
                CHECK(status IN ('Pending', 'Accepted', 'Completed', 'Cancelled')),
            created_at {created_at})""")
        db.execute(f"""CREATE TABLE IF NOT EXISTS rate_limit_buckets (
            bucket_key TEXT NOT NULL, action TEXT NOT NULL,
            window_start {rate_window_type} NOT NULL, request_count INTEGER NOT NULL,
            PRIMARY KEY (bucket_key, action, window_start))""")
        db.execute("CREATE INDEX IF NOT EXISTS idx_rate_limit_buckets_window_start ON rate_limit_buckets(window_start)")

        # Add new nullable/profile fields safely to databases created by earlier versions.
        tables_and_columns = {
            "providers": {
                "description": "TEXT NOT NULL DEFAULT ''",
                "skills": "TEXT NOT NULL DEFAULT ''",
                "account_id": f"{provider_ref} REFERENCES accounts(id)",
                "category_id": f"{provider_ref} REFERENCES service_categories(id)",
                "is_sample": sample_type,
                "availability": "TEXT NOT NULL DEFAULT 'Not specified' CHECK(availability IN ('Available', 'Busy', 'Unavailable', 'Not specified'))",
            },
            "service_requests": {
                "customer_id": f"{provider_ref} REFERENCES accounts(id)",
            },
        }
        for table, columns in tables_and_columns.items():
            if db.is_postgres:
                existing = {row["column_name"] for row in db.execute(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_schema = current_schema() AND table_name = ?", (table,)
                ).fetchall()}
            else:
                existing = {row["name"] for row in db.execute(f"PRAGMA table_info({table})").fetchall()}
            for column, definition in columns.items():
                if column not in existing:
                    db.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")

        # Create indexes only after the additive migration has supplied their columns.
        db.execute("CREATE INDEX IF NOT EXISTS idx_providers_category ON providers(category)")
        db.execute("CREATE INDEX IF NOT EXISTS idx_providers_account_id ON providers(account_id)")
        db.execute(
            "CREATE INDEX IF NOT EXISTS idx_requests_customer_created "
            "ON service_requests(customer_id, created_at DESC, id DESC)"
        )
        db.execute(
            "CREATE INDEX IF NOT EXISTS idx_requests_provider_created "
            "ON service_requests(service_id, created_at DESC, id DESC)"
        )
        db.execute("CREATE INDEX IF NOT EXISTS idx_requests_created_at ON service_requests(created_at)")

        existing_categories = db.execute("SELECT DISTINCT category FROM providers").fetchall()
        for category_row in existing_categories:
            category_name = category_row["category"].strip()
            if not category_name:
                continue
            db.execute("INSERT INTO service_categories (name) VALUES (?) ON CONFLICT(name) DO NOTHING", (category_name,))
            category_id = db.execute("SELECT id FROM service_categories WHERE name = ?", (category_name,)).fetchone()["id"]
            db.execute("UPDATE providers SET category_id = ? WHERE category = ? AND category_id IS NULL", (category_id, category_name))
        count = db.execute("SELECT COUNT(*) AS total FROM providers").fetchone()["total"]
        if count == 0 and APP_ENV != "production" and not DATABASE_URL:
            db.executemany(
                "INSERT INTO providers (name, category, area, phone, is_sample, availability) VALUES (?, ?, ?, ?, ?, ?)",
                [
                    ("Riya's Home Repair", "Home repair", "Silchar", "0000000001", True, "Available"),
                    ("Green Leaf Garden Care", "Gardening", "Silchar", "0000000002", True, "Available"),
                    ("QuickFix Electricals", "Electrical", "Silchar", "0000000003", True, "Available"),
                ],
            )
        elif count == 0 and DEMO_PROVIDERS_ENABLED:
            db.executemany(
                """INSERT INTO providers
                   (name, category, area, phone, description, skills, is_sample, availability)
                   VALUES (?, ?, ?, ?, ?, ?, TRUE, ?)""",
                [
                    ("QuickFix Electrical Demo", "Electrical", "Silchar", "0000000001", "Synthetic demo profile for household electrical work, ceiling fans, lights and wiring.", "fan repair, wiring, switches, light fitting", "Available"),
                    ("Barak Plumbing Demo", "Plumbing", "Tarapur", "0000000002", "Synthetic demo profile for leaking pipes, taps, drains and bathroom or kitchen fittings.", "pipe fitting, tap repair, faucet leak, drain cleaning", "Available"),
                    ("Green Leaf Garden Demo", "Gardening", "Sonai Road", "0000000003", "Synthetic demo profile for lawn and garden care, trimming and planting.", "grass cutting, hedge trimming, pruning, planting", "Busy"),
                    ("TidyNest Cleaning Demo", "Cleaning", "Malugram", "0000000004", "Synthetic demo profile for home and small office cleaning.", "deep cleaning, dusting, mopping, vacuuming", "Available"),
                    ("Valley Woodcraft Demo", "Carpentry", "Silchar", "0000000005", "Synthetic demo profile for furniture, cabinets, doors and shelves.", "woodwork, cabinet repair, furniture assembly, shelving", "Unavailable"),
                    ("Neighbourhood Home Repair Demo", "Home repair", "Udharbond", "0000000006", "Synthetic demo profile for small household repairs and maintenance.", "door repair, wall patching, handyman services", "Available"),
                ],
            )
        # Seeded demo providers are inserted after the first migration pass.
        for category_row in db.execute("SELECT DISTINCT category FROM providers").fetchall():
            category_name = category_row["category"].strip()
            if category_name:
                category_id = ensure_category(db, category_name)
                db.execute(
                    "UPDATE providers SET category_id = ? WHERE category = ? AND category_id IS NULL",
                    (category_id, category_name),
                )


def validate_production_settings() -> None:
    if APP_ENV != "production":
        return
    operator_name = SITE_OPERATOR_NAME.strip()
    privacy_email = PRIVACY_CONTACT_EMAIL.strip()
    placeholder_values = {"replace-before-public-launch", "change-me", "placeholder"}
    if (
        len(ADMIN_PASSWORD) < 16
        or len(SESSION_SECRET) < 32
        or not os.getenv("SESSION_SECRET")
        or not DATABASE_URL.startswith(("postgres://", "postgresql://"))
        or len(operator_name) < 2
        or operator_name.casefold() in placeholder_values
        or privacy_email.casefold() in placeholder_values | {"privacy contact not set"}
        or not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", privacy_email)
        or not REQUEST_RETENTION_DAYS.isdigit()
        or int(REQUEST_RETENTION_DAYS) < 1
    ):
        raise RuntimeError(
            "Production requires a database, owner and privacy contacts, positive retention, "
            "an admin password of at least 16 characters, and a session secret of at least 32 characters."
        )


@asynccontextmanager
async def lifespan(_: FastAPI):
    validate_production_settings()
    initialize_database()
    with connect_db() as db:
        cleanup_expired_requests(db)
    yield


app = FastAPI(
    title="Barak Valley Connect",
    description="Find a local service provider and send a service request.",
    version="1.0.0",
    lifespan=lifespan,
)
app.add_middleware(
    SessionMiddleware,
    secret_key=SESSION_SECRET,
    session_cookie="barak_valley_connect_session",
    same_site="strict",
    https_only=APP_ENV == "production",
    max_age=60 * 60 * 12,
)


@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    return response


app.mount("/static", StaticFiles(directory=ROOT / "static"), name="static")


class AppModel(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)


class ProviderInput(AppModel):
    name: str = Field(min_length=2, max_length=80)
    category: str = Field(min_length=2, max_length=50)
    area: str = Field(min_length=2, max_length=80)
    phone: str = Field(min_length=7, max_length=20)
    description: str = Field(default="", max_length=1000)
    skills: str = Field(default="", max_length=500)
    availability: Literal["Available", "Busy", "Unavailable", "Not specified"] = "Not specified"


class AccountRegistration(AppModel):
    email: str = Field(min_length=5, max_length=254)
    password: str = Field(min_length=10, max_length=128)
    role: Literal["customer", "provider"]
    display_name: str = Field(min_length=2, max_length=80)
    phone: str = Field(min_length=7, max_length=20)
    category: str | None = Field(default=None, min_length=2, max_length=50)
    area: str | None = Field(default=None, min_length=2, max_length=80)
    description: str = Field(default="", max_length=1000)
    skills: str = Field(default="", max_length=500)
    availability: Literal["Available", "Busy", "Unavailable", "Not specified"] = "Not specified"


class AccountLogin(AppModel):
    email: str = Field(min_length=5, max_length=254)
    password: str = Field(min_length=1, max_length=128)


class RequestInput(AppModel):
    customer_name: str = Field(min_length=2, max_length=80)
    customer_phone: str = Field(min_length=7, max_length=20)
    service_id: int = Field(gt=0)
    details: str = Field(min_length=5, max_length=500)
    privacy_consent: bool = False


class StatusInput(AppModel):
    status: Literal["Pending", "Accepted", "Completed", "Cancelled"]


class AdminLogin(AppModel):
    password: str = Field(min_length=1, max_length=256)


class RecommendationInput(AppModel):
    description: str = Field(min_length=3, max_length=300)


def require_admin(request: Request):
    if not request.session.get("is_admin"):
        raise HTTPException(status_code=401, detail="Please sign in as the website owner.")


def hash_password(password: str, salt: bytes | None = None) -> str:
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 260_000)
    return f"{salt.hex()}:{digest.hex()}"


def verify_password(password: str, stored_hash: str) -> bool:
    try:
        salt_hex, digest_hex = stored_hash.split(":", 1)
        expected = bytes.fromhex(digest_hex)
        actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(salt_hex), 260_000)
        return hmac.compare_digest(actual, expected)
    except (ValueError, TypeError):
        return False


def public_account(row) -> dict:
    return {"id": row["id"], "email": row["email"], "role": row["role"],
            "display_name": row["display_name"], "phone": row["phone"]}


def require_account(request: Request, roles: tuple[str, ...] = ("customer", "provider")):
    account_id = request.session.get("account_id")
    if not account_id:
        raise HTTPException(status_code=401, detail="Please sign in to continue.")
    with connect_db() as db:
        row = db.execute("SELECT * FROM accounts WHERE id = ?", (account_id,)).fetchone()
    if not row or row["role"] not in roles:
        raise HTTPException(status_code=403, detail="Your account does not have access to this page.")
    return dict(row)


def ensure_category(db: Database, category_name: str) -> int:
    db.execute("INSERT INTO service_categories (name) VALUES (?) ON CONFLICT(name) DO NOTHING", (category_name,))
    return db.execute("SELECT id FROM service_categories WHERE name = ?", (category_name,)).fetchone()["id"]


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


def enforce_rate_limit(request: Request, *, action: str, limit: int, window_seconds: int, detail: str):
    """Atomically count a request in the configured database for cross-worker limits."""
    client_ip = request.client.host if request.client else "unknown"
    bucket_key = hmac.new(
        SESSION_SECRET.encode("utf-8"), client_ip.encode("utf-8"), hashlib.sha256
    ).hexdigest()
    now = int(time.time())
    window_start = now - (now % window_seconds)
    with connect_db() as db:
        db.execute("DELETE FROM rate_limit_buckets WHERE window_start < ?", (now - 86400,))
        if db.is_postgres:
            upsert_sql = """INSERT INTO rate_limit_buckets AS current_bucket
                (bucket_key, action, window_start, request_count)
                VALUES (?, ?, ?, 1)
                ON CONFLICT(bucket_key, action, window_start)
                DO UPDATE SET request_count = current_bucket.request_count + 1
                RETURNING current_bucket.request_count AS request_count"""
        else:
            upsert_sql = """INSERT INTO rate_limit_buckets
                (bucket_key, action, window_start, request_count)
                VALUES (?, ?, ?, 1)
                ON CONFLICT(bucket_key, action, window_start)
                DO UPDATE SET request_count = rate_limit_buckets.request_count + 1
                RETURNING request_count"""
        row = db.execute(upsert_sql, (bucket_key, action, window_start)).fetchone()
        request_count = row["request_count"]
    if request_count > limit:
        raise HTTPException(status_code=429, detail=detail)


@app.get("/health", include_in_schema=False)
def health():
    with connect_db() as db:
        db.execute("SELECT 1").fetchone()
    return {"status": "ok"}


@app.get("/", include_in_schema=False)
def home():
    return FileResponse(ROOT / "static" / "index.html")


@app.get("/providers/{provider_id}", include_in_schema=False)
def provider_profile_page(provider_id: int):
    return FileResponse(ROOT / "static" / "provider.html")


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
    account_id = request.session.get("account_id")
    account = None
    if account_id:
        with connect_db() as db:
            row = db.execute("SELECT * FROM accounts WHERE id = ?", (account_id,)).fetchone()
            if row:
                account = public_account(row)
            else:
                request.session.clear()
    return {"is_admin": bool(request.session.get("is_admin")), "account": account}


@app.post("/api/auth/admin-login")
def admin_login(payload: AdminLogin, request: Request):
    enforce_rate_limit(request, action="admin_login", limit=10, window_seconds=900,
                       detail="Too many attempts. Try again in 15 minutes.")
    if not hmac.compare_digest(payload.password, ADMIN_PASSWORD):
        raise HTTPException(status_code=401, detail="That password did not match.")
    request.session.clear()
    request.session["is_admin"] = True
    return {"is_admin": True}


@app.post("/api/auth/admin-logout")
def admin_logout(request: Request):
    request.session.clear()
    return {"is_admin": False}


@app.post("/api/auth/register", status_code=201)
def register_account(payload: AccountRegistration, request: Request):
    email = payload.email.strip().lower()
    if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email):
        raise HTTPException(status_code=422, detail="Enter a valid email address.")
    if payload.role == "provider" and (not payload.category or not payload.area):
        raise HTTPException(status_code=422, detail="Provider accounts need a service category and area.")
    enforce_rate_limit(request, action="account_register", limit=5, window_seconds=3600,
                       detail="Too many account registrations. Try again later.")
    with connect_db() as db:
        if db.execute("SELECT id FROM accounts WHERE email = ?", (email,)).fetchone():
            raise HTTPException(status_code=409, detail="An account with that email already exists.")
        cursor = db.execute(
            "INSERT INTO accounts (email, password_hash, role, display_name, phone) VALUES (?, ?, ?, ?, ?) RETURNING id",
            (email, hash_password(payload.password), payload.role, payload.display_name.strip(), payload.phone.strip()),
        )
        account_id = cursor.fetchone()["id"]
        if payload.role == "provider":
            category = payload.category.strip()
            db.execute("INSERT INTO service_categories (name) VALUES (?) ON CONFLICT(name) DO NOTHING", (category,))
            category_id = db.execute("SELECT id FROM service_categories WHERE name = ?", (category,)).fetchone()["id"]
            db.execute(
                """INSERT INTO providers
                   (name, category, area, phone, description, skills, account_id, category_id, availability)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (payload.display_name.strip(), category, payload.area.strip(), payload.phone.strip(),
                 payload.description.strip(), payload.skills.strip(), account_id, category_id, payload.availability),
            )
        account = public_account(db.execute("SELECT * FROM accounts WHERE id = ?", (account_id,)).fetchone())
    request.session.clear()
    request.session["account_id"] = account_id
    return {"account": account}


@app.post("/api/auth/login")
def account_login(payload: AccountLogin, request: Request):
    email = payload.email.strip().lower()
    enforce_rate_limit(request, action="account_login", limit=10, window_seconds=900,
                       detail="Too many sign-in attempts. Try again in 15 minutes.")
    with connect_db() as db:
        row = db.execute("SELECT * FROM accounts WHERE email = ?", (email,)).fetchone()
    if not row or not verify_password(payload.password, row["password_hash"]):
        raise HTTPException(status_code=401, detail="Email or password did not match.")
    request.session.clear()
    request.session["account_id"] = row["id"]
    return {"account": public_account(row)}


@app.post("/api/auth/logout")
def account_logout(request: Request):
    request.session.clear()
    return {"account": None, "is_admin": False}


@app.get("/api/providers")
def list_providers(
    request: Request,
    category: str | None = Query(default=None, max_length=50),
    area: str | None = Query(default=None, max_length=80),
    q: str | None = Query(default=None, max_length=120),
):
    """List providers with category, area, and text filters."""
    query = "SELECT * FROM providers WHERE 1=1"
    values: list[str] = []
    if category:
        query += " AND category = ?"
        values.append(category)
    if area:
        query += " AND area = ?"
        values.append(area)
    if q:
        searchable_text = "LOWER(name || ' ' || category || ' ' || area || ' ' || description || ' ' || skills)"
        for term in q.strip().lower().split()[:8]:
            query += f" AND {searchable_text} LIKE ?"
            values.append(f"%{term}%")
    query += " ORDER BY name"
    with connect_db() as db:
        rows = [dict(row) for row in db.execute(query, values).fetchall()]
        is_owner = bool(request.session.get("is_admin"))
        return [provider_response(row, include_phone=is_owner) for row in rows]


def provider_response(row: dict, include_phone: bool = False) -> dict:
    fields = ["id", "name", "category", "area", "description", "skills", "category_id", "is_sample", "availability"]
    if include_phone:
        fields.append("phone")
    return {field: row[field] for field in fields if field in row}


@app.get("/api/categories")
def list_categories():
    with connect_db() as db:
        rows = db.execute(
            """SELECT DISTINCT c.id, c.name, c.description
               FROM service_categories c JOIN providers p ON p.category_id = c.id
               ORDER BY c.name"""
        ).fetchall()
        return [dict(row) for row in rows]


@app.get("/api/providers/{provider_id}")
def get_provider(provider_id: int, request: Request):
    with connect_db() as db:
        row = db.execute("SELECT * FROM providers WHERE id = ?", (provider_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Provider not found.")
        account_id = request.session.get("account_id")
        can_view_phone = bool(request.session.get("is_admin")) or bool(account_id and account_id == row["account_id"])
        return provider_response(dict(row), include_phone=can_view_phone)


@app.post("/api/recommendations")
def recommend_providers(payload: RecommendationInput, request: Request):
    """Explain how current provider listings fit a short natural-language requirement."""
    enforce_rate_limit(request, action="recommendations", limit=60, window_seconds=900,
                       detail="Too many searches. Please try again in a few minutes.")
    with connect_db() as db:
        rows = [dict(row) for row in db.execute(
            "SELECT id, name, category, area, description, skills, availability, is_sample FROM providers ORDER BY name"
        ).fetchall()]

    if not rows:
        from query_understanding import understand_requirement

        return {
            "matches": [],
            "analysis": understand_requirement(payload.description, []),
            "message": "There are no provider listings to match yet.",
        }

    matches = rank_providers(payload.description, rows)
    from query_understanding import understand_requirement

    analysis = understand_requirement(payload.description, rows)
    message = "Ranked using your service details, requested area, and each listing’s stated availability. Scores describe listing fit, not provider quality." if matches else "I couldn't find a relevant provider in the current listings. Try another description or browse all services."
    return {"matches": matches, "analysis": analysis, "message": message}


@app.post("/api/providers", status_code=201)
def create_provider(provider: ProviderInput, _: None = Depends(require_admin)):
    with connect_db() as db:
        category_id = ensure_category(db, provider.category.strip())
        cursor = db.execute(
            """INSERT INTO providers
               (name, category, area, phone, description, skills, category_id, availability)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?) RETURNING id""",
            (provider.name.strip(), provider.category.strip(), provider.area.strip(), provider.phone.strip(),
             provider.description.strip(), provider.skills.strip(), category_id, provider.availability),
        )
        provider_id = cursor.fetchone()["id"]
        return dict(db.execute("SELECT * FROM providers WHERE id = ?", (provider_id,)).fetchone())


@app.put("/api/providers/{provider_id}")
def update_provider(provider_id: int, provider: ProviderInput, _: None = Depends(require_admin)):
    with connect_db() as db:
        category_id = ensure_category(db, provider.category.strip())
        cursor = db.execute(
            """UPDATE providers SET name = ?, category = ?, area = ?, phone = ?,
               description = ?, skills = ?, category_id = ?, availability = ? WHERE id = ?""",
            (provider.name.strip(), provider.category.strip(), provider.area.strip(), provider.phone.strip(),
             provider.description.strip(), provider.skills.strip(), category_id, provider.availability, provider_id),
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


@app.get("/api/provider/profile")
def get_my_provider_profile(request: Request):
    account = require_account(request, ("provider",))
    with connect_db() as db:
        row = db.execute("SELECT * FROM providers WHERE account_id = ?", (account["id"],)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Provider profile not found.")
        return provider_response(dict(row), include_phone=True)


@app.put("/api/provider/profile")
def update_my_provider_profile(provider: ProviderInput, request: Request):
    account = require_account(request, ("provider",))
    with connect_db() as db:
        existing = db.execute("SELECT id FROM providers WHERE account_id = ?", (account["id"],)).fetchone()
        if not existing:
            raise HTTPException(status_code=404, detail="Provider profile not found.")
        category_id = ensure_category(db, provider.category.strip())
        db.execute(
            """UPDATE providers SET name = ?, category = ?, area = ?, phone = ?,
               description = ?, skills = ?, category_id = ?, availability = ? WHERE id = ?""",
            (provider.name.strip(), provider.category.strip(), provider.area.strip(), provider.phone.strip(),
             provider.description.strip(), provider.skills.strip(), category_id, provider.availability, existing["id"]),
        )
        return provider_response(dict(db.execute("SELECT * FROM providers WHERE id = ?", (existing["id"],)).fetchone()), include_phone=True)


@app.post("/api/requests", status_code=201)
def create_request(payload: RequestInput, request: Request):
    if not payload.privacy_consent:
        raise HTTPException(status_code=400, detail="Please agree to the privacy notice before sending a request.")
    enforce_rate_limit(request, action="service_request", limit=5, window_seconds=3600,
                       detail="Too many requests from this connection. Please try again later.")
    customer_id = None
    account_id = request.session.get("account_id")
    if account_id:
        with connect_db() as db:
            account = db.execute("SELECT * FROM accounts WHERE id = ?", (account_id,)).fetchone()
        if not account:
            raise HTTPException(status_code=401, detail="Please sign in again before submitting your request.")
        if account["role"] == "customer":
            customer_id = account["id"]
            customer_name = account["display_name"]
            customer_phone = account["phone"]
        else:
            customer_name = payload.customer_name
            customer_phone = payload.customer_phone
    else:
        customer_name = payload.customer_name
        customer_phone = payload.customer_phone
    with connect_db() as db:
        cleanup_expired_requests(db)
        provider = db.execute("SELECT id, is_sample FROM providers WHERE id = ?", (payload.service_id,)).fetchone()
        if provider is None:
            raise HTTPException(status_code=404, detail="Provider not found")
        if APP_ENV == "production" and provider["is_sample"]:
            raise HTTPException(status_code=409, detail="Synthetic demonstration listings cannot receive real service requests.")
        db.execute(
            """INSERT INTO service_requests
               (customer_name, customer_phone, service_id, details, customer_id)
               VALUES (?, ?, ?, ?, ?)""",
            (customer_name, customer_phone, payload.service_id, payload.details, customer_id),
        )
        return {"message": "Your request was received. The website owner can review it in the management area."}


@app.get("/api/my/requests")
def list_my_requests(request: Request):
    account = require_account(request, ("customer",))
    with connect_db() as db:
        rows = db.execute(
            """SELECT r.id, r.details, r.status, r.created_at,
                      p.name AS provider_name, p.category, p.area
               FROM service_requests r JOIN providers p ON p.id = r.service_id
               WHERE r.customer_id = ? ORDER BY r.created_at DESC, r.id DESC""",
            (account["id"],),
        ).fetchall()
        return [dict(row) for row in rows]


@app.get("/api/provider/requests")
def list_provider_requests(request: Request):
    account = require_account(request, ("provider",))
    with connect_db() as db:
        provider = db.execute("SELECT id FROM providers WHERE account_id = ?", (account["id"],)).fetchone()
        if not provider:
            raise HTTPException(status_code=404, detail="Provider profile not found.")
        rows = db.execute(
            """SELECT id, customer_name, customer_phone, details, status, created_at
               FROM service_requests WHERE service_id = ? ORDER BY created_at DESC, id DESC""",
            (provider["id"],),
        ).fetchall()
        return [dict(row) for row in rows]


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
        writer.writerows({field: spreadsheet_safe_value(row[field]) for field in fields} for row in rows)
    return StreamingResponse(
        iter([buffer.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=private-service-requests.csv"},
    )


def spreadsheet_safe_value(value):
    """Prevent CSV text values from being interpreted as spreadsheet formulas."""
    if isinstance(value, str) and value.lstrip("\ufeff \t\r\n")[:1] in {"=", "+", "-", "@"}:
        return "'" + value
    return value


@app.delete("/api/requests/{request_id}", status_code=204)
def delete_request(request_id: int, _: None = Depends(require_admin)):
    with connect_db() as db:
        cursor = db.execute("DELETE FROM service_requests WHERE id = ?", (request_id,))
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="Service request not found")

