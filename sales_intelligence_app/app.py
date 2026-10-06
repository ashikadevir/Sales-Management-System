import streamlit as st
from auth import init_session, login_page, logout
from modules.kpi_dashboard import render_kpi_dashboard
from modules.add_sale import render_add_sale
#from modules.payment_splits import render_payment_splits
#from modules.sales_reports import render_sales_reports
from modules.sql_analytics import render_sql_analytics

# 1. Set Page Configuration
st.set_page_config(
    page_title="Sales Intelligence Hub",
    page_icon="💼",
    layout="wide"
)

# 2. Initialize Session Variables
init_session()

# 3. Handle Authentication View
if not st.session_state.get("logged_in"):
    login_page()
else:
    # 4. Render Sidebar User Profile Header
    st.sidebar.title(f"👤 {st.session_state.get('username')}")
    st.sidebar.caption(f"Role: **{st.session_state.get('user_role')}**")
    
    branch_id = st.session_state.get("branch_id")
    if branch_id:
        st.sidebar.caption(f"Assigned Branch ID: **{branch_id}**")
    else:
        st.sidebar.caption("Scope: **All Branches (Global)**")

    st.sidebar.markdown("---")

    # Logout Button
    if st.sidebar.button("🚪 Logout", use_container_width=True):
        logout()

    # 5. Sidebar Navigation Menu
    st.sidebar.header("Navigation")
    page = st.sidebar.radio(
        "Select Screen:",
        [
            "📊 Financial Dashboard & KPIs",
            "➕ Add New Sale",
            #"💸 Record Payment Split",
            #"📋 Sales & Pending Reports",
            "🔍 Predefined SQL Analytics"
        ]
    )

    # 6. Page Routing
    if page == "📊 Financial Dashboard & KPIs":
        render_kpi_dashboard()
    elif page == "➕ Add New Sale":
        render_add_sale()
    #elif page == "💸 Record Payment Split":
       # render_payment_splits()
    #elif page == "📋 Sales & Pending Reports":
      #  render_sales_reports()
    elif page == "🔍 Predefined SQL Analytics":
        render_sql_analytics()