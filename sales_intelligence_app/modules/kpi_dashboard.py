from datetime import date, datetime, timedelta

import altair as alt
import pandas as pd
import streamlit as st

from db import run_query

ALL = "All"
PRODUCT_LABEL = "Course Name"   # label for the product filter and table column
MAX_TABLE_ROWS = 5000
COLOR_RECEIVED = "#2E9E6B"
COLOR_PENDING = "#F28C28"
COLOR_BAR = "#3B82F6"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def to_float(value):
    """MySQL SUM() returns Decimal (or None). Charts and maths need floats."""
    return float(value) if value is not None else 0.0


def as_date(value):
    """Normalise a DATE/DATETIME value from MySQL to a plain date."""
    if isinstance(value, datetime):
        return value.date()
    return value


def inr_full(value):
    """Exact amount with Indian digit grouping, e.g. ₹3,67,68,000.00"""
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


def inr_compact(value):
    """Short amount that fits in a metric card, e.g. ₹3.68 Cr / ₹19.03 L"""
    sign = "-" if value < 0 else ""
    a = abs(value)
    if a >= 1e7:
        return f"{sign}₹{a / 1e7:.2f} Cr"
    if a >= 1e5:
        return f"{sign}₹{a / 1e5:.2f} L"
    if a >= 1e3:
        return f"{sign}₹{a / 1e3:.1f} K"
    return f"{sign}₹{a:,.0f}"


def kpi_card(column, label, value):
    """Metric card: short value on top, exact figure underneath."""
    column.metric(label, inr_compact(value))
    column.caption(inr_full(value))


# ---------------------------------------------------------------------------
# Sales records table (page filters + its own Status / Search / Sort filters)
# ---------------------------------------------------------------------------
TABLE_SORTS = {
    "Newest first": "cs.date DESC, cs.sale_id DESC",
    "Oldest first": "cs.date ASC, cs.sale_id ASC",
    "Highest gross sales": "cs.gross_sales DESC",
    "Highest pending amount": "cs.pending_amount DESC",
}


def render_sales_table(conds, params, branch_options=None, locked_branch=None,
                       product_options=None, locked_product=None):
    """Records table. It follows the page filters (branch, course, dates)
    and adds Branch, Course, Status, Search and Sort filters of its own.

    branch_options / product_options: choices for the multi-selects, shown
        only while the matching page filter is on "All".
    locked_branch / locked_product: value shown (disabled) when the page
        filter or the user's account already fixes it.
    """
    st.subheader("📋 Sales Records")

    r1c1, r1c2, r1c3 = st.columns(3)
    r2c1, r2c2 = st.columns([2, 1])

    # Branch filter
    chosen_branch_ids = []
    if branch_options:
        chosen_branches = r1c1.multiselect(
            "Branch", list(branch_options.keys()), placeholder="All branches"
        )
        chosen_branch_ids = [branch_options[n] for n in chosen_branches]
    else:
        r1c1.multiselect(
            "Branch", [locked_branch], default=[locked_branch], disabled=True
        )

    # Course filter
    chosen_products = []
    if product_options:
        chosen_products = r1c2.multiselect(
            PRODUCT_LABEL, product_options, placeholder="All"
        )
    else:
        r1c2.multiselect(
            PRODUCT_LABEL, [locked_product], default=[locked_product], disabled=True
        )

    status_filter = r1c3.selectbox("Status", [ALL, "Open", "Close"], key="kpi_tbl_status")
    search = r2c1.text_input(
        "Search customer name or mobile number", key="kpi_tbl_search"
    ).strip()
    sort_label = r2c2.selectbox("Sort by", list(TABLE_SORTS.keys()), key="kpi_tbl_sort")

    table_conds = list(conds)
    table_params = list(params)

    if chosen_branch_ids:
        placeholders = ", ".join(["%s"] * len(chosen_branch_ids))
        table_conds.append(f"cs.branch_id IN ({placeholders})")
        table_params += chosen_branch_ids

    if chosen_products:
        placeholders = ", ".join(["%s"] * len(chosen_products))
        table_conds.append(f"cs.product_name IN ({placeholders})")
        table_params += chosen_products

    if status_filter != ALL:
        table_conds.append("cs.status = %s")
        table_params.append(status_filter)

    if search:
        # Escape LIKE wildcards so "50%" or "a_b" are searched literally.
        escaped = (
            search.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        )
        like = f"%{escaped}%"
        table_conds.append("(cs.name LIKE %s OR cs.mobile_number LIKE %s)")
        table_params += [like, like]

    records = run_query(
        f"""
        SELECT cs.sale_id, cs.date, cs.name AS customer_name, cs.mobile_number,
               cs.product_name, b.branch_name, cs.gross_sales,
               cs.received_amount, cs.pending_amount, cs.status
        FROM customer_sales cs
        LEFT JOIN branches b ON cs.branch_id = b.branch_id
        WHERE {" AND ".join(table_conds)}
        ORDER BY {TABLE_SORTS[sort_label]}
        LIMIT {MAX_TABLE_ROWS + 1}
        """,
        tuple(table_params),
    ) or []

    if not records:
        st.info("No sales records match these filters.")
        return

    truncated = len(records) > MAX_TABLE_ROWS
    df_rec = pd.DataFrame(records[:MAX_TABLE_ROWS])
    for col in ("gross_sales", "received_amount", "pending_amount"):
        df_rec[col] = df_rec[col].astype(float)
    df_rec["date"] = pd.to_datetime(df_rec["date"])

    if truncated:
        st.caption(
            f"Showing the first {MAX_TABLE_ROWS:,} matching records - "
            "narrow the filters to see the rest."
        )
    else:
        st.caption(
            f"{len(df_rec):,} record(s) · "
            f"Gross {inr_compact(df_rec['gross_sales'].sum())} · "
            f"Received {inr_compact(df_rec['received_amount'].sum())} · "
            f"Pending {inr_compact(df_rec['pending_amount'].sum())}"
        )

    st.dataframe(
        df_rec,
        hide_index=True,
        height=420,
        column_config={
            "sale_id": st.column_config.NumberColumn("Sale ID", format="%d"),
            "date": st.column_config.DateColumn("Date", format="DD MMM YYYY"),
            "customer_name": st.column_config.TextColumn("Customer"),
            "mobile_number": st.column_config.TextColumn("Mobile"),
            "product_name": st.column_config.TextColumn(PRODUCT_LABEL),
            "branch_name": st.column_config.TextColumn("Branch"),
            "gross_sales": st.column_config.NumberColumn("Gross Sales", format="₹%.2f"),
            "received_amount": st.column_config.NumberColumn("Received", format="₹%.2f"),
            "pending_amount": st.column_config.NumberColumn("Pending", format="₹%.2f"),
            "status": st.column_config.TextColumn("Status"),
        },
    )
    st.download_button(
        "⬇️ Download as CSV",
        data=df_rec.to_csv(index=False).encode("utf-8"),
        file_name="sales_records.csv",
        mime="text/csv",
    )


# ---------------------------------------------------------------------------
# Page
# ---------------------------------------------------------------------------
def render_kpi_dashboard():
    st.title("📊 Financial Dashboard & KPIs")

    role = st.session_state.get("user_role")
    user_branch_id = st.session_state.get("branch_id")
    is_admin = role == "Super Admin"

    if not is_admin and user_branch_id is None:
        st.error("Your account is not assigned to a branch. Please contact the administrator.")
        return

    # ---- Default date range = first to last sale this user can see --------
    if is_admin:
        bounds = run_query(
            "SELECT MIN(cs.date) AS min_date, MAX(cs.date) AS max_date FROM customer_sales cs",
            fetch_all=False,
        )
    else:
        bounds = run_query(
            "SELECT MIN(cs.date) AS min_date, MAX(cs.date) AS max_date "
            "FROM customer_sales cs WHERE cs.branch_id = %s",
            (user_branch_id,),
            fetch_all=False,
        )
    bounds = bounds or {}
    min_date = as_date(bounds.get("min_date")) or date.today()
    max_date = as_date(bounds.get("max_date")) or date.today()

    # ---- Filter controls --------------------------------------------------
    st.subheader("🔍 Filter Controls")
    f1, f2, f3, f4 = st.columns(4)

    # Branch Name
    if is_admin:
        branches = run_query(
            "SELECT branch_id, branch_name FROM branches ORDER BY branch_name"
        ) or []
        branch_options = {ALL: None}
        branch_options.update({b["branch_name"]: b["branch_id"] for b in branches})
        branch_label = f1.selectbox("Branch Name", list(branch_options.keys()))
        target_branch_id = branch_options[branch_label]
    else:
        row = run_query(
            "SELECT branch_name FROM branches WHERE branch_id = %s",
            (user_branch_id,),
            fetch_all=False,
        ) or {}
        branch_label = row.get("branch_name", f"Branch {user_branch_id}")
        f1.selectbox("Branch Name", [branch_label], disabled=True)
        target_branch_id = user_branch_id

    # Product / Course filter (only items sold in the selected branch scope)
    if target_branch_id is not None:
        product_rows = run_query(
            "SELECT DISTINCT cs.product_name FROM customer_sales cs "
            "WHERE cs.branch_id = %s AND cs.product_name IS NOT NULL "
            "ORDER BY cs.product_name",
            (target_branch_id,),
        )
    else:
        product_rows = run_query(
            "SELECT DISTINCT cs.product_name FROM customer_sales cs "
            "WHERE cs.product_name IS NOT NULL ORDER BY cs.product_name"
        )
    product_label = f2.selectbox(
        PRODUCT_LABEL, [ALL] + [r["product_name"] for r in (product_rows or [])]
    )

    # Date range
    start_date = f3.date_input("Start Date", value=min_date, format="YYYY/MM/DD")
    end_date = f4.date_input("End Date", value=max_date, format="YYYY/MM/DD")

    if start_date > end_date:
        st.error("Start Date must be on or before End Date.")
        return

    st.caption(
        f"Showing **{branch_label}** · **{product_label}** · "
        f"{start_date:%d %b %Y} – {end_date:%d %b %Y} (dates filter the sale date)"
    )

    # ---- Build the WHERE clause from the filters --------------------------
    # End date is inclusive: compare against the start of the following day.
    base_conds = ["cs.date >= %s", "cs.date < %s"]
    base_params = [start_date, end_date + timedelta(days=1)]
    if product_label != ALL:
        base_conds.append("cs.product_name = %s")
        base_params.append(product_label)

    conds = list(base_conds)
    params = list(base_params)
    if target_branch_id is not None:
        conds.append("cs.branch_id = %s")
        params.append(target_branch_id)

    where = "WHERE " + " AND ".join(conds)
    params = tuple(params)

    st.markdown("---")

    # ---- Summary numbers --------------------------------------------------
    summary = run_query(
        f"""
        SELECT COALESCE(SUM(cs.gross_sales), 0)     AS total_gross,
               COALESCE(SUM(cs.received_amount), 0) AS total_received,
               COALESCE(SUM(cs.pending_amount), 0)  AS total_pending,
               COUNT(*)                             AS total_sales,
               COALESCE(SUM(cs.status = 'Open'), 0) AS open_sales
        FROM customer_sales cs
        {where}
        """,
        params,
        fetch_all=False,
    ) or {}

    gross = to_float(summary.get("total_gross"))
    received = to_float(summary.get("total_received"))
    pending = to_float(summary.get("total_pending"))
    total_sales = int(summary.get("total_sales") or 0)
    open_sales = int(summary.get("open_sales") or 0)
    closed_sales = total_sales - open_sales
    collection_pct = (received / gross * 100) if gross > 0 else 0.0
    avg_sale = (gross / total_sales) if total_sales else 0.0

    st.subheader("💵 Financial Summary")

    if total_sales == 0:
        st.info("No sales match the selected filters.")
        return

    c1, c2, c3, c4 = st.columns(4)
    kpi_card(c1, "Gross Sales", gross)
    kpi_card(c2, "Received Amount", received)
    kpi_card(c3, "Pending Amount", pending)
    c4.metric("Collection Rate", f"{collection_pct:.1f}%")
    c4.progress(min(collection_pct / 100, 1.0))

    c5, c6, c7, c8 = st.columns(4)
    c5.metric("Total Sales", f"{total_sales:,}")
    c6.metric("Open Sales", f"{open_sales:,}")
    c7.metric("Closed Sales", f"{closed_sales:,}")
    kpi_card(c8, "Average Sale Value", avg_sale)

    # ---- Sales records table (page filters + its own filters) -------------
    st.markdown("---")
    # Super Admin with the page filter on "All" gets a Branch multi-select;
    # otherwise the branch is already fixed, so it is shown locked.
    table_branches = None
    if is_admin and target_branch_id is None:
        table_branches = {n: i for n, i in branch_options.items() if i is not None}
    table_products = None
    if product_label == ALL:
        table_products = [r["product_name"] for r in (product_rows or [])]
    render_sales_table(
        conds, params, table_branches, branch_label, table_products, product_label
    )

    st.markdown("---")

    # ---- Row of charts ----------------------------------------------------
    left, right = st.columns([3, 2])

    # Payment channel breakdown
    with left:
        st.subheader("💳 Payment Channel Breakdown")
        payments = run_query(
            f"""
            SELECT ps.payment_method,
                   COALESCE(SUM(ps.amount_paid), 0) AS total_amount
            FROM payment_splits ps
            JOIN customer_sales cs ON ps.sale_id = cs.sale_id
            {where}
            GROUP BY ps.payment_method
            """,
            params,
        )

        if payments:
            df_pay = pd.DataFrame(payments)
            df_pay["total_amount"] = df_pay["total_amount"].astype(float)
            total_paid = df_pay["total_amount"].sum()
            df_pay["amount_lakh"] = df_pay["total_amount"] / 1e5
            df_pay["share"] = (df_pay["total_amount"] / total_paid * 100) if total_paid else 0.0
            df_pay["label"] = df_pay["total_amount"].apply(inr_compact)
            order = df_pay.sort_values("total_amount", ascending=False)["payment_method"].tolist()
            y_max = max(df_pay["amount_lakh"].max() * 1.2, 1.0)

            base = alt.Chart(df_pay).encode(
                x=alt.X("payment_method:N", sort=order, title=None,
                        axis=alt.Axis(labelAngle=0)),
                y=alt.Y("amount_lakh:Q", title="Collected (₹ Lakh)",
                        scale=alt.Scale(domain=[0, y_max])),
            )
            bars = base.mark_bar(
                cornerRadiusTopLeft=5, cornerRadiusTopRight=5, color=COLOR_BAR
            ).encode(
                tooltip=[
                    alt.Tooltip("payment_method:N", title="Method"),
                    alt.Tooltip("label:N", title="Collected"),
                    alt.Tooltip("share:Q", title="Share (%)", format=".1f"),
                ]
            )
            labels = base.mark_text(dy=-8, fontWeight="bold").encode(text="label:N")
            st.altair_chart((bars + labels).properties(height=340))
        else:
            st.info("No payments recorded for these filters.")

    # Received vs pending split
    with right:
        st.subheader("🎯 Collection Status")
        if received + pending > 0:
            df_split = pd.DataFrame(
                {"status": ["Received", "Pending"], "amount": [received, pending]}
            )
            df_split["label"] = df_split["amount"].apply(inr_compact)
            donut = (
                alt.Chart(df_split)
                .mark_arc(innerRadius=70, outerRadius=130)
                .encode(
                    theta=alt.Theta("amount:Q"),
                    color=alt.Color(
                        "status:N",
                        scale=alt.Scale(
                            domain=["Received", "Pending"],
                            range=[COLOR_RECEIVED, COLOR_PENDING],
                        ),
                        legend=alt.Legend(title=None, orient="bottom"),
                    ),
                    tooltip=[
                        alt.Tooltip("status:N", title="Status"),
                        alt.Tooltip("label:N", title="Amount"),
                    ],
                )
                .properties(height=340)
            )
            st.altair_chart(donut)
        else:
            st.info("Nothing received or pending for these filters.")

    # ---- Branch comparison (Super Admin, all branches only) ---------------
    if is_admin and target_branch_id is None:
        st.markdown("---")
        st.subheader("🏢 Branch-wise Collections")

        # Date/product filters go in the JOIN so branches with no matching
        # sales still appear (with zero) instead of vanishing.
        rows = run_query(
            f"""
            SELECT b.branch_name,
                   COALESCE(SUM(cs.received_amount), 0) AS received,
                   COALESCE(SUM(cs.pending_amount), 0)  AS pending
            FROM branches b
            LEFT JOIN customer_sales cs
                   ON cs.branch_id = b.branch_id AND {" AND ".join(base_conds)}
            GROUP BY b.branch_id, b.branch_name
            """,
            tuple(base_params),
        )

        if rows:
            df_b = pd.DataFrame(rows)
            for col in ("received", "pending"):
                df_b[col] = df_b[col].astype(float)
            df_b["total"] = df_b["received"] + df_b["pending"]
            df_b = df_b.sort_values("total", ascending=False)
            order = df_b["branch_name"].tolist()

            long_df = df_b.melt(
                id_vars=["branch_name"],
                value_vars=["received", "pending"],
                var_name="type",
                value_name="amount",
            )
            long_df["type"] = long_df["type"].str.capitalize()
            long_df["amount_lakh"] = long_df["amount"] / 1e5
            long_df["label"] = long_df["amount"].apply(inr_compact)

            branch_chart = (
                alt.Chart(long_df)
                .mark_bar()
                .encode(
                    y=alt.Y("branch_name:N", sort=order, title=None),
                    x=alt.X("amount_lakh:Q", title="Amount (₹ Lakh)", stack="zero"),
                    color=alt.Color(
                        "type:N",
                        scale=alt.Scale(
                            domain=["Received", "Pending"],
                            range=[COLOR_RECEIVED, COLOR_PENDING],
                        ),
                        legend=alt.Legend(title=None, orient="bottom"),
                    ),
                    tooltip=[
                        alt.Tooltip("branch_name:N", title="Branch"),
                        alt.Tooltip("type:N", title="Type"),
                        alt.Tooltip("label:N", title="Amount"),
                    ],
                )
                .properties(height=max(220, 48 * len(order)))
            )
            st.altair_chart(branch_chart)

            with st.expander("View exact branch figures"):
                pct = (
                    df_b["received"] / df_b["total"].replace(0, float("nan")) * 100
                ).round(1).fillna(0.0)
                table = pd.DataFrame(
                    {
                        "Branch": df_b["branch_name"],
                        "Gross": df_b["total"].apply(inr_full),
                        "Received": df_b["received"].apply(inr_full),
                        "Pending": df_b["pending"].apply(inr_full),
                        "Collection %": pct,
                    }
                )
                st.dataframe(table, hide_index=True)
        else:
            st.info("No branches found.")
