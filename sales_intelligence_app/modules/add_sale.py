import re
from datetime import date
from decimal import Decimal

import streamlit as st

from db import run_query, execute_commit

NEW_PRODUCT = "➕ Add new product…"
PAYMENT_METHODS = ["Cash", "UPI", "Card", "Bank Transfer"]
SALE_STATUSES = ["Open", "Close"]

# Widget keys cleared after a sale is published (branch and date are kept
# so several sales can be entered in a row).
SALE_RESET_KEYS = [
    "sale_customer", "sale_mobile", "sale_product",
    "sale_new_product", "sale_gross", "sale_status",
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def inr(value):
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


def to_money(value):
    """Float from a number_input -> exact 2-decimal Decimal for MySQL."""
    return Decimal(str(value)).quantize(Decimal("0.01"))


def clean_mobile(raw):
    """Return a 10-digit Indian mobile number, or None if it isn't valid."""
    digits = re.sub(r"\D", "", raw or "")
    if len(digits) == 12 and digits.startswith("91"):
        digits = digits[2:]
    elif len(digits) == 11 and digits.startswith("0"):
        digits = digits[1:]
    return digits if re.fullmatch(r"[6-9]\d{9}", digits) else None


def show_flash(key):
    """Show a one-time message that was saved just before a rerun."""
    message = st.session_state.pop(key, None)
    if message:
        st.success(message)


# ---------------------------------------------------------------------------
# Tab 1: Add New Sales Entry
# ---------------------------------------------------------------------------
def _sales_entry_tab(is_admin, user_branch_id):
    # Clear the entry fields after a successful publish (must happen
    # before the widgets are created).
    if st.session_state.pop("reset_sale_form", False):
        for key in SALE_RESET_KEYS:
            st.session_state.pop(key, None)

    show_flash("flash_sale")
    st.subheader("New Sale Generation")

    if is_admin:
        branches = run_query(
            "SELECT branch_id, branch_name FROM branches ORDER BY branch_name"
        ) or []
        if not branches:
            st.error("No branches exist yet. Add a branch before recording sales.")
            return
        branch_map = {b["branch_name"]: b["branch_id"] for b in branches}
    else:
        row = run_query(
            "SELECT branch_name FROM branches WHERE branch_id = %s",
            (user_branch_id,),
            fetch_all=False,
        ) or {}
        locked_branch_name = row.get("branch_name", f"Branch {user_branch_id}")

    product_rows = run_query(
        "SELECT DISTINCT product_name FROM customer_sales "
        "WHERE product_name IS NOT NULL AND product_name <> '' "
        "ORDER BY product_name"
    ) or []
    product_options = [r["product_name"] for r in product_rows] + [NEW_PRODUCT]

    with st.form("add_sale_form"):
        if is_admin:
            branch_name = st.selectbox(
                "Select Target Branch", list(branch_map.keys()), key="sale_branch"
            )
            branch_id = branch_map[branch_name]
        else:
            st.selectbox("Select Target Branch", [locked_branch_name], disabled=True)
            branch_name = locked_branch_name
            branch_id = user_branch_id

        col1, col2 = st.columns(2)
        customer_name = col1.text_input("Customer Name", key="sale_customer")
        product_choice = col2.selectbox(
            "Select Course Name", product_options, key="sale_product"
        )

        col3, col4 = st.columns(2)
        mobile_raw = col3.text_input("Mobile Number", key="sale_mobile")
        sale_date = col4.date_input(
            "Joining Date", value=date.today(), format="YYYY/MM/DD", key="sale_date"
        )


        gross_sales = st.number_input(
            "Gross Sales Amount (₹)",
            min_value=0.0,
            value=0.0,
            step=100.0,
            format="%.2f",
            key="sale_gross",
        )

        status = st.selectbox(
            "Initial Order Status",
            SALE_STATUSES,
            key="sale_status",
            help="Use 'Open' while payment is still due. Payments can only be "
                 "logged against Open sales.",
        )

        submitted = st.form_submit_button("Publish Sale Entry", type="primary")

        if submitted:
            name = customer_name.strip()
            mobile = clean_mobile(mobile_raw)
            product = new_product.strip() if product_choice == NEW_PRODUCT else product_choice

            errors = []
            if not name:
                errors.append("Customer name is required.")
            if mobile is None:
                errors.append("Enter a valid 10-digit mobile number.")
            if not product:
                errors.append("Select a product, or type the new product name.")
            if gross_sales <= 0:
                errors.append("Gross sales amount must be greater than 0.")

            if errors:
                for message in errors:
                    st.error(message)
            else:
                try:
                    sale_id = execute_commit(
                        """
                        INSERT INTO customer_sales
                            (branch_id, date, name, mobile_number, product_name,
                             gross_sales, received_amount, status)
                        VALUES (%s, %s, %s, %s, %s, %s, 0.00, %s)
                        """,
                        (branch_id, sale_date, name, mobile, product,
                         to_money(gross_sales), status),
                    )
                except Exception as e:
                    st.error(f"Failed to publish sale: {e}")
                else:
                    st.session_state["flash_sale"] = (
                        f"Sale #{sale_id} published for {name} · {product} · "
                        f"{inr(gross_sales)} ({branch_name})"
                    )
                    st.session_state["reset_sale_form"] = True
                    st.rerun()


# ---------------------------------------------------------------------------
# Tab 2: Log Payment Split Details
# ---------------------------------------------------------------------------
def _payment_split_tab(is_admin, user_branch_id):
    show_flash("flash_payment")
    st.subheader("Post Payment Installment Split")

    sales_sql = """
        SELECT cs.sale_id, cs.name, cs.product_name, cs.gross_sales, cs.pending_amount
        FROM customer_sales cs
        WHERE cs.status = 'Open' AND cs.pending_amount >= 0.01
    """
    if is_admin:
        open_sales = run_query(sales_sql + " ORDER BY cs.sale_id DESC")
    else:
        open_sales = run_query(
            sales_sql + " AND cs.branch_id = %s ORDER BY cs.sale_id DESC",
            (user_branch_id,),
        )

    if not open_sales:
        st.info("No open sales with a pending balance were found.")
        return

    def sale_label(s):
        product = f" ({s['product_name']})" if s.get("product_name") else ""
        return f"ID {s['sale_id']} - {s['name']}{product} - {inr(s['pending_amount'])} Pending"

    sale_options = {sale_label(s): s for s in open_sales}
    selected = sale_options[
        st.selectbox("Select Target Active Sale ID Asset", list(sale_options.keys()))
    ]
    pending = Decimal(str(selected["pending_amount"]))

    # The form is keyed by sale so the amount resets when another sale is picked.
    with st.form(f"payment_form_{selected['sale_id']}"):
        payment_method = st.selectbox("Payment Collection Channel", PAYMENT_METHODS)

        amount_paid = st.number_input(
            "Collected Split Amount Balance (₹)",
            min_value=0.01,
            max_value=float(pending),
            value=0.01,
            format="%.2f",
        )

        payment_date = st.date_input(
            "Payment Date", value=date.today(), format="YYYY/MM/DD"
        )

        submitted = st.form_submit_button("Apply Payment Allocation", type="primary")

        if submitted:
            amount = to_money(amount_paid)
            if amount <= 0:
                st.error("Enter an amount greater than 0.")
                return

            # Re-check the live balance so a stale page can't overpay a sale.
            check_sql = (
                "SELECT pending_amount FROM customer_sales "
                "WHERE sale_id = %s AND status = 'Open'"
            )
            check_params = [selected["sale_id"]]
            if not is_admin:
                check_sql += " AND branch_id = %s"
                check_params.append(user_branch_id)
            current = run_query(check_sql, tuple(check_params), fetch_all=False)

            if not current:
                st.error("This sale is no longer open or is outside your branch.")
            elif amount > Decimal(str(current["pending_amount"])):
                st.error(
                    f"Amount exceeds the current pending balance of "
                    f"{inr(current['pending_amount'])}."
                )
            else:
                try:
                    # The MySQL AFTER INSERT trigger updates received/pending.
                    execute_commit(
                        """
                        INSERT INTO payment_splits
                            (sale_id, payment_date, amount_paid, payment_method)
                        VALUES (%s, %s, %s, %s)
                        """,
                        (selected["sale_id"], payment_date, amount, payment_method),
                    )
                except Exception as e:
                    st.error(f"Payment could not be recorded: {e}")
                else:
                    st.session_state["flash_payment"] = (
                        f"Payment of {inr(amount)} via {payment_method} applied to "
                        f"Sale #{selected['sale_id']} · {selected['name']}"
                    )
                    st.rerun()


# ---------------------------------------------------------------------------
# Page
# ---------------------------------------------------------------------------
def render_data_entry_workspace():
    st.title("📝 Operations Record Creator")

    role = st.session_state.get("user_role")
    user_branch_id = st.session_state.get("branch_id")
    is_admin = role == "Super Admin"

    if not is_admin and user_branch_id is None:
        st.error("Your account is not assigned to a branch. Please contact the administrator.")
        return

    tab_sale, tab_payment = st.tabs(["Add New Sales Entry", "Log Payment Split Details"])
    with tab_sale:
        _sales_entry_tab(is_admin, user_branch_id)
    with tab_payment:
        _payment_split_tab(is_admin, user_branch_id)


# Backwards-compatible name, in case app.py still imports the old function.
render_add_sale = render_data_entry_workspace
