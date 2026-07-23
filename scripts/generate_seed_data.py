"""
Generates synthetic raw CSV data for the Orbit SaaS subscription analytics
demo project.

Unlike a normal seed generator, the output here is deliberately designed to
be mutated later by scripts/simulate_time_passing.py: raw_subscriptions and
raw_product_events are built so that dbt snapshot (SCD2) and an incremental
model both have something meaningful to do on a second run.

REFERENCE_DATE is a fixed fictional "today" for the initial dataset (not
datetime.now()) so the seed output stays reproducible across runs. Anything
simulate_time_passing.py adds later uses the real wall-clock time, which
lands safely after REFERENCE_DATE.

Run with: python scripts/generate_seed_data.py
Output lands in seeds/*.csv, ready for `dbt seed`.
"""
import csv
import random
from datetime import date, datetime, timedelta
from pathlib import Path

random.seed(42)  # deterministic output so the repo is reproducible

SEEDS_DIR = Path(__file__).resolve().parent.parent / "seeds"
REFERENCE_DATE = date(2026, 7, 1)  # fixed "today" for the initial seed batch

N_USERS = 150

FIRST_NAMES = [
    "Ava", "Liam", "Noah", "Emma", "Oliver", "Sophia", "Elijah", "Isabella",
    "Mateo", "Mia", "Lucas", "Amelia", "Levi", "Harper", "Ezra", "Evelyn",
    "Jack", "Luna", "Leo", "Nora", "Kai", "Zoe", "Miles", "Ivy", "Theo",
]
LAST_NAMES = [
    "Nguyen", "Garcia", "Smith", "Johnson", "Patel", "Kim", "Muller",
    "Rossi", "Dubois", "Andersson", "Silva", "Kowalski", "Haile", "Osei",
    "Tanaka", "Alvarez", "Novak", "Petrov", "Chen", "Larsen",
]
COUNTRIES = [
    "United States", "Canada", "United Kingdom", "Germany", "Australia",
    "Brazil", "Japan", "France", "South Africa", "Sweden",
]

# (plan_tier, base_mrr) — enterprise gets some price variance below
PLAN_TIERS_WEIGHTED = (
    [("starter", 29.00)] * 50 + [("pro", 99.00)] * 35 + [("enterprise", 299.00)] * 15
)
SUBSCRIPTION_STATUSES_WEIGHTED = (
    ["trial"] * 15 + ["active"] * 65 + ["past_due"] * 10 + ["canceled"] * 10
)
EVENT_TYPES_WEIGHTED = (
    ["login"] * 35 + ["page_view"] * 30 + ["feature_used"] * 20
    + ["export_report"] * 8 + ["invite_sent"] * 5 + ["upgrade_clicked"] * 2
)
INVOICE_STATUSES_WEIGHTED = ["paid"] * 88 + ["failed"] * 8 + ["refunded"] * 4


def random_datetime_between(start: datetime, end: datetime) -> datetime:
    delta_seconds = int((end - start).total_seconds())
    return start + timedelta(seconds=random.randint(0, max(delta_seconds, 0)))


def make_users():
    rows = []
    for i in range(1, N_USERS + 1):
        first, last = random.choice(FIRST_NAMES), random.choice(LAST_NAMES)
        signup_date = REFERENCE_DATE - timedelta(days=random.randint(30, 540))
        rows.append({
            "user_id": i,
            "name": f"{first} {last}",
            "email": f"{first.lower()}.{last.lower()}{i}@example.com",
            "signup_date": signup_date.isoformat(),
            "country": random.choice(COUNTRIES),
        })
    return rows


def make_subscriptions(users):
    rows = []
    for user in users:
        plan_tier, base_mrr = random.choice(PLAN_TIERS_WEIGHTED)
        mrr_amount = base_mrr
        if plan_tier == "enterprise":
            mrr_amount = round(random.uniform(249.00, 349.00), 2)

        status = random.choice(SUBSCRIPTION_STATUSES_WEIGHTED)
        signup_date = date.fromisoformat(user["signup_date"])
        created_at = datetime.combine(signup_date, datetime.min.time()) + timedelta(
            hours=random.randint(0, 47)
        )
        # No mutation has happened yet at seed time, so updated_at == created_at.
        # simulate_time_passing.py is what advances this later.
        updated_at = created_at

        rows.append({
            "subscription_id": user["user_id"],  # 1:1 with users for this demo
            "user_id": user["user_id"],
            "plan_tier": plan_tier,
            "status": status,
            "mrr_amount": mrr_amount,
            "created_at": created_at.isoformat(sep=" "),
            "updated_at": updated_at.isoformat(sep=" "),
        })
    return rows


def make_product_events(users, subscriptions):
    active_user_ids = [
        s["user_id"] for s in subscriptions if s["status"] in ("trial", "active", "past_due")
    ]
    window_end = datetime.combine(REFERENCE_DATE, datetime.min.time())
    window_start = window_end - timedelta(days=30)

    rows = []
    event_id = 1
    for user_id in active_user_ids:
        n_events = random.randint(5, 40)
        for _ in range(n_events):
            rows.append({
                "event_id": event_id,
                "user_id": user_id,
                "event_type": random.choice(EVENT_TYPES_WEIGHTED),
                "event_timestamp": random_datetime_between(window_start, window_end).isoformat(sep=" "),
            })
            event_id += 1
    rows.sort(key=lambda r: r["event_timestamp"])
    return rows


def make_invoices(subscriptions):
    rows = []
    invoice_id = 1
    for sub in subscriptions:
        if sub["status"] == "trial":
            continue  # trials haven't been billed yet
        created_at = datetime.fromisoformat(sub["created_at"])
        months_active = max(
            1, (REFERENCE_DATE.year - created_at.year) * 12 + (REFERENCE_DATE.month - created_at.month)
        )
        for m in range(months_active):
            invoice_date = (created_at + timedelta(days=30 * m)).date()
            if invoice_date > REFERENCE_DATE:
                break
            rows.append({
                "invoice_id": invoice_id,
                "subscription_id": sub["subscription_id"],
                "amount": sub["mrr_amount"],
                "invoice_date": invoice_date.isoformat(),
                "status": random.choice(INVOICE_STATUSES_WEIGHTED),
            })
            invoice_id += 1
    return rows


def write_csv(rows, filename):
    SEEDS_DIR.mkdir(exist_ok=True)
    path = SEEDS_DIR / filename
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)
    print(f"wrote {len(rows):>5} rows -> {path}")


if __name__ == "__main__":
    users = make_users()
    subscriptions = make_subscriptions(users)
    product_events = make_product_events(users, subscriptions)
    invoices = make_invoices(subscriptions)

    write_csv(users, "raw_users.csv")
    write_csv(subscriptions, "raw_subscriptions.csv")
    write_csv(product_events, "raw_product_events.csv")
    write_csv(invoices, "raw_invoices.csv")
