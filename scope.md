# Project Scope & Anomaly Log

## Database Schema (Relational)
The application utilizes a strict relational schema in MySQL to maintain data integrity:

1. **User**: `id`, `name`, `email`, `google_id`
2. **Group**: `id`, `name`
3. **GroupMember**: `id`, `group_id`, `user_id`, `joined_at` (Date), `left_at` (Nullable Date) - *Handles time-bound memberships.*
4. **Expense**: `id`, `group_id`, `description`, `amount`, `currency`, `exchange_rate_to_inr`, `date`, `paid_by_id`, `split_type`
5. **ExpenseSplit**: `id`, `expense_id`, `user_id`, `amount_owed`
6. **StagingExpense**: Mirrors the raw CSV columns, plus `status` ('pending', 'valid', 'flagged') and `anomaly_flags` (JSON).

## The Anomaly Log
During the CSV ingestion process, our validation engine intercepts the following edge cases and flags them for manual review in the UI:

1. **Disguised Settlements**: Descriptions like "Rohan paid Aisha back" are flagged with `SETTLEMENT_DISGUISED_AS_EXPENSE` to prevent users from accidentally charging the whole group for a personal debt repayment.
2. **Negative Amounts**: Amounts formatted as negative numbers (e.g., "Parasailing refund") are flagged with `NEGATIVE_AMOUNT_REFUND` to ensure refunds are handled correctly rather than added as new debts.
3. **Time-Bound Violations**: If a user attempts to split a bill with someone who has already moved out (e.g., Meera being charged for April groceries after moving out in March), the engine throws a `MEMBERSHIP_TIME_VIOLATION` error.
4. **Exact Duplicates**: Prevents double-charging by checking the staging table for identical rows (`EXACT_DUPLICATE_ROW`).