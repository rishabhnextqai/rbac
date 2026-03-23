"""
NQ Agent Handler — Streamlit App
Role-based: Admin sees everything, Users see Playground only.
Per-user sessions: Each user's AH calls use THEIR registered_user_id.
"""

import os
import streamlit as st

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # dotenv not needed on Streamlit Cloud

from database import init_db, get_user_by_email, verify_password, seed_admin
from ah_client import AgentHandlerClient


def get_secret(key: str, default: str = "") -> str:
    """Get secret from Streamlit Cloud secrets or env vars."""
    try:
        return st.secrets[key]
    except Exception:
        return os.getenv(key, default)


# ── Config ──
AH_API_KEY = get_secret("AH_API_KEY")
AH_TOOL_PACK_ID = get_secret("AH_TOOL_PACK_ID")
OPENAI_API_KEY = get_secret("OPENAI_API_KEY")

# ── Init DB + seed admin ──
init_db()

# Auto-link admin to AH on first run
admin_email = get_secret("ADMIN_EMAIL", "admin@example.com")
admin_name = get_secret("ADMIN_NAME", "Admin")
_admin_user = get_user_by_email(admin_email)
if not _admin_user:
    # Create or find AH registered user for admin
    _ah_admin_client = AgentHandlerClient(AH_API_KEY, AH_TOOL_PACK_ID, "")
    _ah_admin_id = _ah_admin_client.create_or_find_registered_user(
        origin_user_id=admin_email,
        origin_user_name=admin_name,
        shared_credential_group={
            "origin_company_id": "nq-admin",
            "origin_company_name": "Next Quarter",
        },
    )
else:
    _ah_admin_id = _admin_user.get("ah_registered_user_id", "")

seed_admin(
    email=admin_email,
    name=admin_name,
    password=get_secret("ADMIN_PASSWORD", "admin123"),
    ah_tool_pack_id=AH_TOOL_PACK_ID,
    ah_registered_user_id=_ah_admin_id,
)

# ── Page config ──
st.set_page_config(page_title="NQ Agent Handler", page_icon="⚡", layout="wide")

# ── Session state defaults ──
if "user" not in st.session_state:
    st.session_state.user = None
if "chat_messages" not in st.session_state:
    st.session_state.chat_messages = []


def login_page():
    st.markdown("""
    <div style="display:flex;justify-content:center;margin-top:60px">
        <div style="text-align:center">
            <h1>⚡ NQ Agent Handler</h1>
            <p style="color:gray">Sign in to your account</p>
        </div>
    </div>
    """, unsafe_allow_html=True)

    col1, col2, col3 = st.columns([1, 1, 1])
    with col2:
        with st.form("login_form"):
            email = st.text_input("Email", placeholder="you@company.com")
            password = st.text_input("Password", type="password", placeholder="Enter your password")
            submitted = st.form_submit_button("Sign in", use_container_width=True)

            if submitted:
                if not email or not password:
                    st.error("Enter email and password")
                else:
                    user = get_user_by_email(email)
                    if user and verify_password(password, user["password_hash"]):
                        st.session_state.user = {
                            "id": user["id"],
                            "email": user["email"],
                            "name": user["name"],
                            "role": user["role"],
                            "company": user.get("company", ""),
                            "ah_registered_user_id": user.get("ah_registered_user_id", ""),
                            "ah_tool_pack_id": user.get("ah_tool_pack_id", "") or AH_TOOL_PACK_ID,
                        }
                        st.session_state.chat_messages = []
                        st.rerun()
                    else:
                        st.error("Invalid email or password")

        st.caption("Contact your admin if you don't have an account")


def main_app():
    user = st.session_state.user
    is_admin = user["role"] == "admin"

    # ── Sidebar ──
    with st.sidebar:
        st.markdown(f"### ⚡ NQ Agents")

        # Admin pages
        if is_admin:
            st.caption("ADMIN")
            page = st.radio(
                "Navigation",
                ["Playground", "Connectors", "Tool Packs", "Team"],
                label_visibility="collapsed",
            )
        else:
            st.caption("AGENT")
            page = "Playground"
            st.markdown("💬 **Playground**")

        st.divider()

        # User info
        role_icon = "🛡️" if is_admin else "👤"
        st.markdown(f"{role_icon} **{user['name']}**")
        st.caption(f"{user['email']} · {user['role']}")

        if st.button("Sign out", use_container_width=True):
            st.session_state.user = None
            st.session_state.chat_messages = []
            st.rerun()

    # ── Page routing ──
    if page == "Playground":
        from views.playground import render as render_playground
        render_playground(AH_API_KEY, OPENAI_API_KEY, AH_TOOL_PACK_ID)

    elif page == "Connectors" and is_admin:
        from views.connectors import render as render_connectors
        admin_client = AgentHandlerClient(AH_API_KEY, AH_TOOL_PACK_ID, "")
        render_connectors(admin_client)

    elif page == "Tool Packs" and is_admin:
        from views.tool_packs import render as render_tool_packs
        admin_client = AgentHandlerClient(AH_API_KEY, AH_TOOL_PACK_ID, "")
        render_tool_packs(admin_client)

    elif page == "Team" and is_admin:
        from views.team import render as render_team
        admin_client = AgentHandlerClient(AH_API_KEY, AH_TOOL_PACK_ID, "")
        render_team(admin_client, AH_TOOL_PACK_ID)


# ── Route ──
if st.session_state.user is None:
    login_page()
else:
    main_app()
