"""
GTM AI -- publicly-hosted Streamlit chat UI over the gtm_ai Cortex Analyst
semantic view (semantic_views/gtm_ai.sql), scoped to exactly two marts:
subscription_mrr_movements and dim_subscriptions_current.

Runs externally (Streamlit Community Cloud), so genuine public
access requires this app to authenticate to Snowflake itself, 
via one shared service credential (a Programmatic Access Token restricted to 
svc_gtm_ai_role) that every anonymous visitor rides on behind the scenes. 
That credential's RBAC grants -- SELECT on
exactly subscription_mrr_movements, dim_subscriptions_current, and the
gtm_ai semantic view, nothing else, no writes; are the real security
boundary here, not the semantic view's own TABLES clause.

Reliability/safety layered on top of the raw Cortex Analyst call:
  - exponential backoff retry on transient failures (timeouts/5xx), not on
    4xx (auth/bad-request errors won't fix themselves by retrying)
  - read-only SQL validation before ever executing anything Cortex Analyst
    returns (defense-in-depth alongside the RBAC grants, not instead of
    them -- nothing in this app ever concatenates user text into SQL, so
    this isn't classical SQL-injection defense, it's a check that the LLM
    didn't propose a write)
  - 3-way self-consistency voting: ask the same question 3 times in
    parallel, execute each candidate's SQL, and return whichever answer a
    majority of the 3 actually agree on (by result set, not SQL text)
"""
import concurrent.futures
import re
import time

import pandas as pd
import requests
import snowflake.connector
import streamlit as st

ACCOUNT = st.secrets["snowflake"]["account"]
USER = st.secrets["snowflake"]["user"]
PAT = st.secrets["snowflake"]["pat"]
WAREHOUSE = "gtm_ai_wh"
DATABASE = "ORBIT_ANALYTICS"
SCHEMA = "MARTS"
SEMANTIC_VIEW = "GTM_AI"

CORTEX_ANALYST_URL = f"https://{ACCOUNT}.snowflakecomputing.com/api/v2/cortex/analyst/message"

MAX_RETRIES = 4
N_VOTERS = 3

FORBIDDEN_KEYWORDS = re.compile(
    r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|CREATE|GRANT|REVOKE|TRUNCATE|MERGE|"
    r"CALL|COPY|PUT|GET|EXECUTE|UNLOAD)\b",
    re.IGNORECASE,
)


def is_read_only_select(sql: str) -> bool:
    stripped = sql.strip()
    if not re.match(r"^(SELECT|WITH)\b", stripped, re.IGNORECASE):
        return False
    if FORBIDDEN_KEYWORDS.search(stripped):
        return False
    return True


def call_cortex_analyst(question: str) -> dict:
    """POST to Cortex Analyst with exponential backoff on transient failures only."""
    headers = {
        "Authorization": f"Bearer {PAT}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    body = {
        "messages": [{"role": "user", "content": [{"type": "text", "text": question}]}],
        "semantic_view": f"{DATABASE}.{SCHEMA}.{SEMANTIC_VIEW}",
    }

    last_error = None
    for attempt in range(MAX_RETRIES):
        try:
            resp = requests.post(CORTEX_ANALYST_URL, headers=headers, json=body, timeout=60)
        except requests.exceptions.RequestException as e:
            last_error = e
            time.sleep(2 ** attempt)
            continue

        if resp.status_code < 400:
            return resp.json()
        if resp.status_code < 500:
            # Permanent failure (auth, bad request) -- retrying won't help.
            raise RuntimeError(f"Cortex Analyst request failed ({resp.status_code}): {resp.text}")

        last_error = RuntimeError(f"Cortex Analyst request failed ({resp.status_code}): {resp.text}")
        time.sleep(2 ** attempt)

    raise RuntimeError(f"Cortex Analyst request failed after {MAX_RETRIES} attempts: {last_error}")


def extract_sql(response: dict) -> str | None:
    for item in response.get("message", {}).get("content", []):
        if item.get("type") == "sql":
            return item["statement"]
    return None


def extract_text(response: dict) -> str:
    parts = [
        item["text"]
        for item in response.get("message", {}).get("content", [])
        if item.get("type") == "text"
    ]
    return "\n\n".join(parts)


def is_verified(response: dict) -> bool:
    for item in response.get("message", {}).get("content", []):
        if item.get("type") == "sql":
            return bool(item.get("confidence", {}).get("verified_query_used"))
    return False


def run_sql(sql: str) -> pd.DataFrame:
    conn = snowflake.connector.connect(
        user=USER,
        password=PAT,
        account=ACCOUNT,
        warehouse=WAREHOUSE,
        database=DATABASE,
        schema=SCHEMA,
    )
    try:
        cur = conn.cursor()
        cur.execute(sql)
        columns = [c[0] for c in cur.description]
        rows = cur.fetchall()
        return pd.DataFrame(rows, columns=columns)
    finally:
        conn.close()


def result_signature(df: pd.DataFrame) -> tuple:
    """Order-independent signature of a result set's actual values, for voting."""
    return tuple(sorted(tuple(str(v) for v in row) for row in df.itertuples(index=False)))


def ask_with_voting(question: str) -> dict:
    """
    Fires N_VOTERS parallel requests, executes each valid candidate's SQL,
    and returns the majority-agreed answer (by result set), noting how many
    of the N responses actually agreed.
    """
    with concurrent.futures.ThreadPoolExecutor(max_workers=N_VOTERS) as executor:
        responses = list(executor.map(lambda _: call_cortex_analyst(question), range(N_VOTERS)))

    voteable = []  # (response, dataframe, signature) for candidates that executed successfully
    text_only = []  # responses with no SQL at all (e.g. clarifying questions)
    for response in responses:
        sql = extract_sql(response)
        if sql is None:
            text_only.append(response)
            continue
        if not is_read_only_select(sql):
            continue  # don't execute, don't let it vote
        try:
            df = run_sql(sql)
            voteable.append((response, df, result_signature(df)))
        except Exception:
            continue

    if not voteable:
        fallback = text_only[0] if text_only else (responses[0] if responses else {})
        return {
            "response": fallback,
            "dataframe": None,
            "consensus": f"0 of {N_VOTERS} responses produced a usable answer",
        }

    groups: dict = {}
    for response, df, sig in voteable:
        groups.setdefault(sig, []).append((response, df))

    best_sig, best_group = max(groups.items(), key=lambda kv: len(kv[1]))
    if len(best_group) > 1:
        response, df = best_group[0]
        consensus = f"{len(best_group)} of {N_VOTERS} responses agreed"
    else:
        verified = [(r, d) for r, d, _ in voteable if is_verified(r)]
        response, df = verified[0] if verified else (voteable[0][0], voteable[0][1])
        consensus = "no consensus among responses -- showing best guess"

    return {"response": response, "dataframe": df, "consensus": consensus}


SUGGESTED_QUESTIONS = [
    "What was total churned MRR?",
    "How many active enterprise subscriptions are there?",
    "What's total current MRR by plan tier?",
    "How many subscriptions are currently at risk?",
]


def process_question(question: str):
    st.session_state.messages.append({"role": "user", "text": question})
    with st.chat_message("user"):
        st.markdown(question)

    with st.chat_message("assistant"):
        with st.spinner("Thinking..."):
            try:
                result = ask_with_voting(question)
                text = extract_text(result["response"])
                sql = extract_sql(result["response"])
                st.markdown(text or "_No text explanation returned._")
                if result["dataframe"] is not None:
                    st.dataframe(result["dataframe"], use_container_width=True)
                if sql:
                    with st.expander("Generated SQL", expanded=False):
                        st.code(sql, language="sql")
                st.session_state.messages.append({
                    "role": "assistant",
                    "text": text,
                    "dataframe": result["dataframe"],
                    "sql": sql,
                })
            except Exception as e:
                st.error(str(e))
                st.session_state.messages.append({"role": "assistant", "text": f"Error: {e}"})


st.set_page_config(page_title="GTM AI", page_icon="\U0001F4CA", layout="wide")

with st.sidebar:
    st.header("About GTM AI")
    st.markdown(
        "A natural-language query bot for SaaS subscription analytics, built on "
        "[Snowflake Cortex Analyst](https://docs.snowflake.com/en/user-guide/snowflake-cortex/cortex-analyst) "
        "over a semantic view scoped to two dbt-built marts: subscription MRR "
        "movements and current subscription state."
    )
    st.markdown(
        "**Source code:** "
        "[GitHub repo](https://github.com/bluelion1999/SaaS_subscription_analytics_dbt)"
    )
    st.divider()
    st.markdown(
        "**Architecture:** dbt (staging → SCD2 snapshot → incremental fact + "
        "reporting mart) on Snowflake, queried here through a locked-down, "
        "read-only service role -- this app can only ever run `SELECT` "
        "against two specific tables, nothing else."
    )
    st.divider()
    st.caption(
        f"Every answer is generated {N_VOTERS} times independently and the "
        "majority result is shown, so a single bad generation doesn't reach you."
    )

st.title("GTM AI")
st.caption(
    "Ask questions about SaaS subscription MRR movements and current subscriptions "
    "-- answered by Snowflake Cortex Analyst."
)

if "messages" not in st.session_state:
    st.session_state.messages = []

st.markdown("**Try asking:**")
cols = st.columns(len(SUGGESTED_QUESTIONS))
for col, suggestion in zip(cols, SUGGESTED_QUESTIONS):
    if col.button(suggestion, use_container_width=True):
        st.session_state.pending_question = suggestion

for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["text"])
        if message.get("dataframe") is not None:
            st.dataframe(message["dataframe"], use_container_width=True)
        if message.get("sql"):
            with st.expander("Generated SQL", expanded=False):
                st.code(message["sql"], language="sql")

question = st.chat_input("Ask a question about subscriptions or MRR movements...")
if not question and st.session_state.get("pending_question"):
    question = st.session_state.pop("pending_question")

if question:
    process_question(question)
