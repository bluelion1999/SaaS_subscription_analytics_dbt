"""
Simulates a real source system evolving between dbt runs: a handful of
raw_subscriptions rows change state (the input to the SCD2 snapshot) and a
new batch of raw_product_events lands (the input to the incremental model).

Unlike generate_seed_data.py, this writes directly to Snowflake instead of
seeds/*.csv + `dbt seed` -- `dbt seed` replaces a table wholesale, which
can't represent "some rows changed, others didn't." That partial-change
shape is exactly what dbt snapshot and incremental models exist to handle,
so this script has to produce it directly against the warehouse.

Selections are randomized (no fixed seed) on purpose: each run should look
like an organic tick of time passing, not a reproducible fixture.

Run with: python scripts/simulate_time_passing.py
Then:     dbt snapshot   (captures the subscription changes as new SCD2 rows)
          dbt run        (incremental model picks up only the new events)
"""
import os
import random
from pathlib import Path

import snowflake.connector

ENV_PATH = Path(__file__).resolve().parent.parent / ".env"

PLAN_MRR = {"starter": 29.00, "pro": 99.00, "enterprise": 299.00}
UPGRADE_PATH = {"starter": "pro", "pro": "enterprise"}
DOWNGRADE_PATH = {"enterprise": "pro", "pro": "starter"}

EVENT_TYPES_WEIGHTED = (
    ["login"] * 35 + ["page_view"] * 30 + ["feature_used"] * 20
    + ["export_report"] * 8 + ["invite_sent"] * 5 + ["upgrade_clicked"] * 2
)


def load_env(path=ENV_PATH):
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k, v)


def connect():
    load_env()
    return snowflake.connector.connect(
        account=os.environ["SNOWFLAKE_ACCOUNT"],
        user=os.environ["SNOWFLAKE_USER"],
        password=os.environ["SNOWFLAKE_PASSWORD"],
        role="orbit_dbt_role",
        warehouse="orbit_wh",
        database="orbit_analytics",
        schema="raw",
    )


def fetch_ids_by_status(cur, status, limit):
    cur.execute(
        "select subscription_id from raw_subscriptions where status = %s "
        "order by random() limit %s",
        (status, limit),
    )
    return [row[0] for row in cur.fetchall()]


def update_status(cur, subscription_ids, new_status):
    if not subscription_ids:
        return
    ids = ",".join(str(i) for i in subscription_ids)
    cur.execute(
        f"update raw_subscriptions set status = %s, updated_at = current_timestamp() "
        f"where subscription_id in ({ids})",
        (new_status,),
    )


def change_plan_tier(cur, subscription_ids, path):
    for sub_id in subscription_ids:
        cur.execute("select plan_tier from raw_subscriptions where subscription_id = %s", (sub_id,))
        row = cur.fetchone()
        if not row:
            continue
        new_tier = path.get(row[0])
        if new_tier:
            cur.execute(
                "update raw_subscriptions set plan_tier = %s, mrr_amount = %s, updated_at = current_timestamp() "
                "where subscription_id = %s",
                (new_tier, PLAN_MRR[new_tier], sub_id),
            )


def mutate_subscriptions(cur):
    trial_ids = fetch_ids_by_status(cur, "trial", 5)
    active_ids = fetch_ids_by_status(cur, "active", 30)
    past_due_ids = fetch_ids_by_status(cur, "past_due", 10)

    to_activate = trial_ids
    to_past_due = active_ids[5:10]
    to_upgrade = active_ids[10:15]
    to_downgrade = active_ids[15:19]
    to_cancel = past_due_ids[:5]
    to_recover = past_due_ids[5:10]

    update_status(cur, to_activate, "active")
    update_status(cur, to_past_due, "past_due")
    update_status(cur, to_cancel, "canceled")
    update_status(cur, to_recover, "active")
    change_plan_tier(cur, to_upgrade, UPGRADE_PATH)
    change_plan_tier(cur, to_downgrade, DOWNGRADE_PATH)

    print(
        f"trial->active: {len(to_activate)} | active->past_due: {len(to_past_due)} | "
        f"past_due->canceled: {len(to_cancel)} | past_due->active: {len(to_recover)} | "
        f"upgraded: {len(to_upgrade)} | downgraded: {len(to_downgrade)}"
    )


def insert_new_events(cur, n_events=300):
    cur.execute("select coalesce(max(event_id), 0) from raw_product_events")
    max_id = cur.fetchone()[0]

    cur.execute(
        "select user_id from raw_subscriptions where status in ('trial', 'active', 'past_due')"
    )
    eligible_user_ids = [row[0] for row in cur.fetchall()]

    rows = [
        (max_id + i + 1, random.choice(eligible_user_ids), random.choice(EVENT_TYPES_WEIGHTED))
        for i in range(n_events)
    ]
    cur.executemany(
        "insert into raw_product_events (event_id, user_id, event_type, event_timestamp) "
        "values (%s, %s, %s, current_timestamp())",
        rows,
    )
    print(f"inserted {len(rows)} new product events starting at event_id {max_id + 1}")


if __name__ == "__main__":
    conn = connect()
    cur = conn.cursor()
    try:
        mutate_subscriptions(cur)
        insert_new_events(cur)
        conn.commit()
        print("done -- run `dbt snapshot` and `dbt run` to see the effects")
    finally:
        cur.close()
        conn.close()
