# Architectural & Engineering Decisions

**Decision 1: Implementing a "Staging Area" for CSV Ingestion**
- **Options Considered**: Direct insert to production tables (failing the whole batch on error) vs. Staging Table architecture.
- **Why**: Financial data is unforgiving. Dumping messy CSV data directly into the `Expense` table risks corrupting user balances. By writing the CSV to a temporary `StagingExpense` table first, the system acts as a firewall. It allows the validation engine to run asynchronously and gives the end-user a UI to review anomalies, correct math, or discard junk rows before anything touches the production ledger.

**Decision 2: The Penny-Rounding Algorithm**
- **Options Considered**: Float math vs. Decimal rounding to 2 places.
- **Why**: When splitting $100 among 3 people, standard math yields $33.33 each, leaving $0.01 unaccounted for. This creates database drift. I implemented a strict mathematical algorithm during the "Approve" action: it rounds individual shares to 2 decimal places, calculates the total sum of those rounded shares, and applies the exact remainder difference ($0.01) to the first splitter in the array. This guarantees that `SUM(ExpenseSplit) == Expense.amount`.

**Decision 3: Mock Login Context vs. Google OAuth**
- **Options Considered**: Starting with a simple user dropdown vs. building full Auth.
- **Why**: Given the 48-hour constraint, the core complexity of this assignment was the data ingestion, anomaly detection, and rounding algorithms. I initially prioritized a Session Context Setter (a dropdown) to mock the logged-in user so I could build the required Balance API endpoints. Once the core engine was 100% verified, I invested the remaining time into retrofitting Google OAuth2 and JWTs to make the application production-ready.

**Decision 4: Deploying Python via Vercel Serverless**
- **Options Considered**: Standard containerized host (Render) vs. Serverless Functions (Vercel).
- **Why**: Used Vercel via a custom `vercel.json` configuration. While this introduces a slight "cold start" delay when the API wakes up, it provides immediate CI/CD, SSL, and zero-maintenance hosting, which is ideal for a rapid MVP.