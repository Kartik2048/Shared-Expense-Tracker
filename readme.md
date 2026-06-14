# Shared Expenses Tracker (Spreetail Engineering Assessment)

A full-stack, multi-currency shared expense tracker designed to ingest messy CSV data, validate edge cases, and correctly calculate exact user balances.

## Live Deployment
- **Backend API**: [Insert Your Vercel URL Here]
- **Frontend**: To view the application, download this repository and open `index.html` directly in any modern web browser.

## Tech Stack
- **Backend**: FastAPI (Python), SQLAlchemy, Authlib, PyJWT
- **Database**: MySQL (Aiven)
- **Frontend**: Vanilla JavaScript, HTML5, CSS3 (Glassmorphism Dark Theme)
- **Deployment**: Vercel (Serverless Python runtime)

## Local Setup Instructions
1. Clone the repository.
2. Create a virtual environment: `python -m venv venv` and activate it.
3. Install dependencies: `pip install -r requirements.txt`
4. Set up your `.env` file with `DATABASE_URL`, `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, and `JWT_SECRET`.
5. Run the server: `uvicorn app.main:app --reload`
6. Open `index.html` in your browser.

## Key Features
- **CSV Ingestion Pipeline**: Parses raw transaction files and flags formatting errors or mathematical anomalies.
- **Staging Area Dashboard**: A dedicated UI to review, discard, or force-approve flagged transactions.
- **Penny-Rounding Engine**: Resolves fractional cent discrepancies (e.g., splitting $100 among 3 people).
- **Time-Bound Memberships**: Validates if a user was actually living in the apartment when a shared bill was issued.