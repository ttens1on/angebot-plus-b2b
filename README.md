# AngebotPlus B2B — Smart Offer & PDF Generator

Interactive demo B2B SaaS tool for German Handwerk/B2B offer ("Angebot") creation with a live split-screen A4 preview, MwSt/DIN 5008-style calculation, SQLite persistence, and server-side PDF export.

## Stack
- **Backend:** FastAPI + SQLite (`sqlite3`, stdlib) + ReportLab (PDF)
- **Frontend:** HTML5 + Tailwind CSS (CDN) + vanilla JS (no build step)

## Run locally

```bash
python -m venv .venv
.venv\Scripts\activate        # Windows
# source .venv/bin/activate   # macOS/Linux

pip install -r requirements.txt
uvicorn main:app --reload
```

Open http://localhost:8000

The SQLite database file `offers.db` is created automatically on first run in the project root.

## Deploy

A `Procfile` is included for platforms like Heroku/Render:

```
web: uvicorn main:app --host 0.0.0.0 --port $PORT
```

## API overview

| Method | Path                          | Purpose                                      |
|--------|--------------------------------|-----------------------------------------------|
| GET    | `/api/offers/next-number`     | Suggest next `ANG-{year}-{seq}` offer number  |
| POST   | `/api/calculate`              | Server-side totals calculation                |
| POST   | `/api/offers`                 | Save an offer                                 |
| GET    | `/api/offers`                 | List saved offers (history)                   |
| GET    | `/api/offers/{id}`            | Get one saved offer                           |
| DELETE | `/api/offers/{id}`            | Delete a saved offer                          |
| GET    | `/api/offers/{id}/pdf`        | Download PDF for a saved offer                |
| POST   | `/api/offers/generate-pdf`    | Save + generate + download PDF in one call    |
