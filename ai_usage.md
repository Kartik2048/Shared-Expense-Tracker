# AI Usage Documentation

**Primary AI Tools Used**: Gemini 3.1 Pro and Gemini 3.5 Flash

**General Usage Strategy**: 
The AI was used as a pair-programming partner to rapidly generate boilerplate FastAPI routers, vanilla JavaScript UI components, and complex regex pattern matchers. I acted as the architect, defining strict step-by-step implementation plans, while the AI executed the syntax.

## 3 Specific Cases Where the AI Failed

**Failure 1: Violating Product Constraints via Auto-Promotion**
- **The Issue**: When generating the ingestion pipeline, the AI wrote logic that automatically pushed "valid" rows from the staging table directly into the production database, bypassing the user interface.
- **The Fix**: This violated a core product constraint (that the user must manually approve imports). I intervened, halted the code generation, and rewrote the state machine to decouple validation from promotion, forcing all records to wait in the staging table until the user clicked "Approve."

**Failure 2: String Parsing Hallucination**
- **The Issue**: During CSV parsing, the AI failed to split the `raw_split_with` column. It passed `"Aisha;Rohan;Priya;Meera"` to the database query as one single, massive username, resulting in continuous `USER_NOT_FOUND` errors.
- **The Fix**: I prompted the AI to rewrite the validation engine, explicitly instructing it to split the string by the semicolon delimiter and strip whitespace before validating individual users.

**Failure 3: Brittle Regex on Split Details**
- **The Issue**: When generating the `POST /approve` endpoint, the AI assumed the `split_details` string would be formatted with colons (e.g., `Rohan:700`). The actual CSV data used spaces (`Rohan 700`). This caused the backend to crash with a 500 server error when calculating custom splits.
- **The Fix**: I identified the parsing error in the server logs and instructed the AI to rewrite the extraction logic using a more robust regex that could handle spaces, missing colons, and percentage symbols dynamically.