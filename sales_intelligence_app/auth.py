import streamlit as st
from db import run_query

def init_session():
    """Initializes session state variables on app startup."""
    if "logged_in" not in st.session_state:
        st.session_state["logged_in"] = False
    if "username" not in st.session_state:
        st.session_state["username"] = ""
    if "user_role" not in st.session_state:
        st.session_state["user_role"] = ""
    if "branch_id" not in st.session_state:
        st.session_state["branch_id"] = None
    if "user_id" not in st.session_state:
        st.session_state["user_id"] = None

def login_page():
    """Renders the system login screen and validates credentials."""
    st.title("🛡️ Sales Intelligence Hub")
    st.subheader("System Login")

    with st.form("login_form"):
        username = st.text_input("Username")
        password = st.text_input("Password", type="password")
        submitted = st.form_submit_button("Login")

        if submitted:
            if not username or not password:
                st.error("Please enter both username and password.")
                return

            # Query database for matching credentials
            user = run_query(
                "SELECT * FROM users WHERE username = %s AND password = %s",
                (username, password),
                fetch_all=False
            )

            if user:
                st.session_state["logged_in"] = True
                st.session_state["user_id"] = user["user_id"]
                st.session_state["username"] = user["username"]
                st.session_state["user_role"] = user["role"]
                st.session_state["branch_id"] = user["branch_id"]
                st.success(f"Welcome, {user['username']} ({user['role']})!")
                st.rerun()
            else:
                st.error("Invalid username or password.")

def logout():
    """Clears user session data and logs out."""
    st.session_state["logged_in"] = False
    st.session_state["username"] = ""
    st.session_state["user_role"] = ""
    st.session_state["branch_id"] = None
    st.session_state["user_id"] = None
    st.rerun()