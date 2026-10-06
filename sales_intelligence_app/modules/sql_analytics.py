from decimal import Decimal
from textwrap import dedent

import pandas as pd
import streamlit as st

from db import run_query


def _sql(text):
    return dedent(text).strip()


# ---------------------------------------------------------------------------
# The 20 predefined questions, grouped by category
# ---------------------------------------------------------------------------
QUERY_GROUPS = {
    "Basic Queries": [
        ("Retrieve all records from the customer_sales table.",
         _sql("""
            SELECT *
            FROM customer_sales;
         """)),
        ("Retrieve all records from the branches table.",
         _sql("""
            SELECT *
            FROM branches;
         """)),
        ("Retrieve all records from the payment_splits table.",
         _sql("""
            SELECT *
            FROM payment_splits;
         """)),
        ("Display all sales with status = 'Open'.",
         _sql("""
            SELECT *
            FROM customer_sales
            WHERE status = 'Open';
         """)),
        ("Retrieve all sales belonging to the Chennai branch.",
         _sql("""
            SELECT cs.*
            FROM customer_sales cs
            JOIN branches b ON cs.branch_id = b.branch_id
            WHERE b.branch_name = 'Chennai';
         """)),
    ],
    "Aggregation Queries": [
        ("Calculate the total gross sales across all branches.",
         _sql("""
            SELECT SUM(gross_sales) AS total_gross_sales
            FROM customer_sales;
         """)),
        ("Calculate the total received amount across all sales.",
         _sql("""
            SELECT SUM(received_amount) AS total_received_amount
            FROM customer_sales;
         """)),
        ("Calculate the total pending amount across all sales.",
         _sql("""
            SELECT SUM(pending_amount) AS total_pending_amount
            FROM customer_sales;
         """)),
        ("Count the total number of sales per branch.",
         _sql("""
            SELECT b.branch_name,
                   COUNT(cs.sale_id) AS total_sales
            FROM branches b
            LEFT JOIN customer_sales cs ON b.branch_id = cs.branch_id
            GROUP BY b.branch_id, b.branch_name
            ORDER BY total_sales DESC;
         """)),
        ("Find the average gross sales amount.",
         _sql("""
            SELECT ROUND(AVG(gross_sales), 2) AS average_gross_sales
            FROM customer_sales;
         """)),
    ],
    "Join-Based Queries": [
        ("Retrieve sales details along with the branch name.",
         _sql("""
            SELECT cs.sale_id, cs.date, cs.name AS customer_name,
                   cs.product_name, cs.gross_sales, cs.received_amount,
                   cs.pending_amount, cs.status, b.branch_name
            FROM customer_sales cs
            JOIN branches b ON cs.branch_id = b.branch_id
            ORDER BY cs.sale_id;
         """)),
        ("Retrieve sales details along with total payment received (using payment_splits).",
         _sql("""
            SELECT cs.sale_id, cs.name AS customer_name, cs.product_name,
                   cs.gross_sales,
                   COALESCE(SUM(ps.amount_paid), 0) AS total_payment_received
            FROM customer_sales cs
            LEFT JOIN payment_splits ps ON cs.sale_id = ps.sale_id
            GROUP BY cs.sale_id, cs.name, cs.product_name, cs.gross_sales
            ORDER BY cs.sale_id;
         """)),
        ("Show branch-wise total gross sales (using JOIN & GROUP BY).",
         _sql("""
            SELECT b.branch_name,
                   SUM(cs.gross_sales) AS total_gross_sales
            FROM branches b
            JOIN customer_sales cs ON b.branch_id = cs.branch_id
            GROUP BY b.branch_id, b.branch_name
            ORDER BY total_gross_sales DESC;
         """)),
        ("Display sales along with payment method used.",
         _sql("""
            SELECT cs.sale_id, cs.name AS customer_name, cs.product_name,
                   ps.payment_date, ps.amount_paid, ps.payment_method
            FROM customer_sales cs
            JOIN payment_splits ps ON cs.sale_id = ps.sale_id
            ORDER BY cs.sale_id, ps.payment_date;
         """)),
        ("Retrieve sales along with branch admin name.",
         _sql("""
            SELECT cs.sale_id, cs.name AS customer_name, cs.product_name,
                   cs.gross_sales, b.branch_name, b.branch_admin_name
            FROM customer_sales cs
            JOIN branches b ON cs.branch_id = b.branch_id
            ORDER BY cs.sale_id;
         """)),
    ],
    "Financial Tracking Queries": [
        ("Find sales where the pending amount is greater than 5000.",
         _sql("""
            SELECT *
            FROM customer_sales
            WHERE pending_amount > 5000
            ORDER BY pending_amount DESC;
         """)),
        ("Retrieve top 3 highest gross sales.",
         _sql("""
            SELECT *
            FROM customer_sales
            ORDER BY gross_sales DESC
            LIMIT 3;
         """)),
        ("Find the branch with highest total gross sales.",
         _sql("""
            SELECT b.branch_name,
                   SUM(cs.gross_sales) AS total_gross_sales
            FROM branches b
            JOIN customer_sales cs ON b.branch_id = cs.branch_id
            GROUP BY b.branch_id, b.branch_name
            ORDER BY total_gross_sales DESC
            LIMIT 1;
         """)),
        ("Retrieve monthly sales summary (group by month & year).",
         _sql("""
            SELECT YEAR(date)      AS sales_year,
                   MONTH(date)     AS month_number,
                   MONTHNAME(date) AS month_name,
                   COUNT(*)             AS total_sales,
                   SUM(gross_sales)     AS total_gross,
                   SUM(received_amount) AS total_received,
                   SUM(pending_amount)  AS total_pending
            FROM customer_sales
            GROUP BY YEAR(date), MONTH(date), MONTHNAME(date)
            ORDER BY sales_year DESC, month_number DESC;
         """)),
        ("Calculate payment method-wise total collection (Cash / UPI / Card).",
         _sql("""
            SELECT payment_method,
                   SUM(amount_paid) AS total_collection
            FROM payment_splits
            GROUP BY payment_method
            ORDER BY total_collection DESC;
         """)),
    ],
}

# Number the questions 1-20 in order (the groups above are only for
# organising the code; the page shows one single list).
QUESTIONS = {}       # label -> (number, sql)
_number = 0
for _items in QUERY_GROUPS.values():
    for _text, _query in _items:
        _number += 1
        QUESTIONS[f"{_number}. {_text}"] = (_number, _query)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def inr_full(value):
    """Amount with Indian digit grouping, e.g. ₹3,67,68,000.00"""
    value = float(value)
    sign = "-" if value < 0 else ""
    whole, decimals = f"{abs(value):.2f}".split(".")
    if len(whole) > 3:
        head, tail = whole[:-3], whole[-3:]
        parts = []
        while len(head) > 2:
            parts.insert(0, head[-2:])
            head = head[:-2]
        if head:
            parts.insert(0, head)
        whole = ",".join(parts + [tail])
    return f"{sign}₹{whole}.{decimals}"


def _show_result(number, rows):
    if not rows:
        st.info("Query returned no records.")
        return

    df_raw = pd.DataFrame(rows)

    # A single number (the SUM / AVG questions) is shown as a large value.
    if df_raw.shape == (1, 1):
        value = df_raw.iat[0, 0]
        title = str(df_raw.columns[0]).replace("_", " ").title()
        if value is None:
            st.info("The query returned NULL (there is no data to calculate from).")
            return
        elif isinstance(value, (int, float, Decimal)):
            st.metric(title, inr_full(value))
            return
        # anything else falls through to the normal table

    # Decimal columns -> float so the table sorts and aligns as numbers.
    df_view = df_raw.copy()
    for col in df_view.columns:
        if df_view[col].map(lambda v: isinstance(v, Decimal)).any():
            df_view[col] = df_view[col].astype(float)

    st.caption(f"{len(df_view)} row(s) returned")
    st.dataframe(df_view, hide_index=True)
    st.download_button(
        "⬇️ Download as CSV",
        data=df_raw.to_csv(index=False).encode("utf-8"),
        file_name=f"query_{number}_result.csv",
        mime="text/csv",
    )


# ---------------------------------------------------------------------------
# Page
# ---------------------------------------------------------------------------
def render_sql_analytics():
    st.title("🔍 Predefined SQL Analytics Engine")

    # These queries read every branch's data, so keep them admin-only.
    if st.session_state.get("user_role") != "Super Admin":
        st.warning("The SQL Analytics Engine covers all branches and is available to Super Admin only.")
        return

    label = st.selectbox("Select Analytical Question", list(QUESTIONS.keys()))
    number, query = QUESTIONS[label]

    st.subheader("Generated SQL Query:")
    st.code(query, language="sql")

    if st.button("Run Analytics Query", type="primary"):
        try:
            rows = run_query(query)
        except Exception as e:
            st.session_state.pop("sql_result", None)
            st.error(f"Query failed: {e}")
        else:
            st.session_state["sql_result"] = {"label": label, "rows": rows or []}

    # Results are kept in session state so they survive reruns
    # (for example when the CSV download button is clicked).
    result = st.session_state.get("sql_result")
    if result and result["label"] == label:
        _show_result(number, result["rows"])
