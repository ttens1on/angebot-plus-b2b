"""
AngebotPlus B2B - Smart Offer & PDF Generator for Handwerk & B2B Services
FastAPI backend: calculation, SQLite persistence, ReportLab PDF generation.
"""
import io
import json
import sqlite3
from contextlib import contextmanager
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import List, Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from pdf_generator import generate_offer_pdf

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "offers.db"
STATIC_DIR = BASE_DIR / "static"

app = FastAPI(title="AngebotPlus B2B API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# --------------------------------------------------------------------------
# Database
# --------------------------------------------------------------------------
@contextmanager
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


DOC_TYPE_PREFIXES = {"angebot": "ANG", "rechnung": "RE", "auftragsbestaetigung": "AB"}


def init_db():
    with get_db() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS offers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                document_type TEXT NOT NULL DEFAULT 'angebot',
                offer_number TEXT UNIQUE NOT NULL,
                offer_date TEXT NOT NULL,
                validity_days INTEGER NOT NULL,
                provider_name TEXT NOT NULL,
                provider_address TEXT NOT NULL,
                provider_tax_id TEXT,
                provider_iban TEXT,
                provider_email TEXT,
                client_name TEXT NOT NULL,
                client_company TEXT,
                client_address TEXT NOT NULL,
                items_json TEXT NOT NULL,
                vat_rate REAL NOT NULL,
                discount_percent REAL NOT NULL DEFAULT 0,
                subtotal_net REAL NOT NULL,
                discount_amount REAL NOT NULL,
                net_after_discount REAL NOT NULL,
                vat_amount REAL NOT NULL,
                gross_total REAL NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        try:
            conn.execute("ALTER TABLE offers ADD COLUMN document_type TEXT NOT NULL DEFAULT 'angebot'")
        except sqlite3.OperationalError:
            pass


# --------------------------------------------------------------------------
# Schemas
# --------------------------------------------------------------------------
class LineItem(BaseModel):
    description: str
    quantity: float
    unit: str = "Stk"
    unit_price: float


class Provider(BaseModel):
    name: str
    address: str
    tax_id: str = ""
    iban: str = ""
    email: str = ""


class Client(BaseModel):
    name: str
    company: str = ""
    address: str


class OfferIn(BaseModel):
    document_type: str = "angebot"
    offer_number: str
    offer_date: str
    validity_days: int = 30
    provider: Provider
    client: Client
    items: List[LineItem] = Field(default_factory=list)
    vat_rate: float = 19
    discount_percent: float = 0


class CalculateIn(BaseModel):
    items: List[LineItem] = Field(default_factory=list)
    vat_rate: float = 19
    discount_percent: float = 0


# --------------------------------------------------------------------------
# Calculation helpers
# --------------------------------------------------------------------------
def calculate_totals(items: List[LineItem], discount_percent: float, vat_rate: float) -> dict:
    subtotal_net = sum(i.quantity * i.unit_price for i in items)
    discount_amount = subtotal_net * (discount_percent / 100)
    net_after_discount = subtotal_net - discount_amount
    vat_amount = net_after_discount * (vat_rate / 100)
    gross_total = net_after_discount + vat_amount
    return {
        "subtotal_net": round(subtotal_net, 2),
        "discount_amount": round(discount_amount, 2),
        "net_after_discount": round(net_after_discount, 2),
        "vat_amount": round(vat_amount, 2),
        "gross_total": round(gross_total, 2),
    }


def row_to_offer_dict(row: sqlite3.Row) -> dict:
    d = dict(row)
    d["items"] = json.loads(d.pop("items_json"))
    d["provider"] = {
        "name": d.pop("provider_name"),
        "address": d.pop("provider_address"),
        "tax_id": d.pop("provider_tax_id") or "",
        "iban": d.pop("provider_iban") or "",
        "email": d.pop("provider_email") or "",
    }
    d["client"] = {
        "name": d.pop("client_name"),
        "company": d.pop("client_company") or "",
        "address": d.pop("client_address"),
    }
    return d


# --------------------------------------------------------------------------
# Startup
# --------------------------------------------------------------------------
@app.on_event("startup")
def on_startup():
    init_db()


# --------------------------------------------------------------------------
# API: calculation
# --------------------------------------------------------------------------
@app.post("/api/calculate")
def calculate(payload: CalculateIn):
    return calculate_totals(payload.items, payload.discount_percent, payload.vat_rate)


# --------------------------------------------------------------------------
# API: next offer number
# --------------------------------------------------------------------------
@app.get("/api/offers/next-number")
def next_offer_number(document_type: str = "angebot"):
    year = date.today().year
    prefix_code = DOC_TYPE_PREFIXES.get(document_type, "ANG")
    prefix = f"{prefix_code}-{year}-"
    with get_db() as conn:
        cur = conn.execute(
            "SELECT COUNT(*) AS n FROM offers WHERE offer_number LIKE ?",
            (f"{prefix}%",),
        )
        count = cur.fetchone()["n"]
    return {"offer_number": f"{prefix}{count + 1:03d}"}


# --------------------------------------------------------------------------
# API: offers CRUD (create + list + get)
# --------------------------------------------------------------------------
@app.post("/api/offers")
def create_offer(payload: OfferIn):
    if not payload.items:
        raise HTTPException(status_code=400, detail="Mindestens eine Position ist erforderlich.")

    totals = calculate_totals(payload.items, payload.discount_percent, payload.vat_rate)
    created_at = datetime.utcnow().isoformat()

    with get_db() as conn:
        try:
            cur = conn.execute(
                """
                INSERT INTO offers (
                    document_type,
                    offer_number, offer_date, validity_days,
                    provider_name, provider_address, provider_tax_id, provider_iban, provider_email,
                    client_name, client_company, client_address,
                    items_json, vat_rate, discount_percent,
                    subtotal_net, discount_amount, net_after_discount, vat_amount, gross_total,
                    created_at
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    payload.document_type,
                    payload.offer_number,
                    payload.offer_date,
                    payload.validity_days,
                    payload.provider.name,
                    payload.provider.address,
                    payload.provider.tax_id,
                    payload.provider.iban,
                    payload.provider.email,
                    payload.client.name,
                    payload.client.company,
                    payload.client.address,
                    json.dumps([i.model_dump() for i in payload.items]),
                    payload.vat_rate,
                    payload.discount_percent,
                    totals["subtotal_net"],
                    totals["discount_amount"],
                    totals["net_after_discount"],
                    totals["vat_amount"],
                    totals["gross_total"],
                    created_at,
                ),
            )
        except sqlite3.IntegrityError:
            raise HTTPException(status_code=409, detail="Angebotsnummer existiert bereits.")
        offer_id = cur.lastrowid
        row = conn.execute("SELECT * FROM offers WHERE id = ?", (offer_id,)).fetchone()

    return row_to_offer_dict(row)


@app.get("/api/offers")
def list_offers():
    with get_db() as conn:
        rows = conn.execute(
            "SELECT id, document_type, offer_number, offer_date, client_name, client_company, gross_total, created_at "
            "FROM offers ORDER BY id DESC"
        ).fetchall()
    return [dict(r) for r in rows]


@app.get("/api/offers/{offer_id}")
def get_offer(offer_id: int):
    with get_db() as conn:
        row = conn.execute("SELECT * FROM offers WHERE id = ?", (offer_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Angebot nicht gefunden.")
    return row_to_offer_dict(row)


@app.delete("/api/offers/{offer_id}")
def delete_offer(offer_id: int):
    with get_db() as conn:
        cur = conn.execute("DELETE FROM offers WHERE id = ?", (offer_id,))
    if cur.rowcount == 0:
        raise HTTPException(status_code=404, detail="Angebot nicht gefunden.")
    return {"status": "deleted"}


# --------------------------------------------------------------------------
# API: PDF generation
# --------------------------------------------------------------------------
@app.get("/api/offers/{offer_id}/pdf")
def offer_pdf(offer_id: int):
    with get_db() as conn:
        row = conn.execute("SELECT * FROM offers WHERE id = ?", (offer_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Angebot nicht gefunden.")

    offer = row_to_offer_dict(row)
    pdf_bytes = generate_offer_pdf(offer)
    filename = f"{offer['offer_number']}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.post("/api/offers/generate-pdf")
def create_offer_and_pdf(payload: OfferIn):
    """Save the offer to the database and return the generated PDF in one call."""
    saved = create_offer(payload)
    pdf_bytes = generate_offer_pdf(saved)
    filename = f"{saved['offer_number']}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "X-Offer-Id": str(saved["id"]),
        },
    )


# --------------------------------------------------------------------------
# Static frontend (mounted last so it never shadows the /api/* routes above)
# --------------------------------------------------------------------------
app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
