"""
NQ Agent Handler — Production Streamlit App
"""

import os
import streamlit as st

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from database import init_db, get_user_by_email, verify_password, seed_admin
from ah_client import AgentHandlerClient


def get_secret(key: str, default: str = "") -> str:
    try:
        return st.secrets[key]
    except Exception:
        return os.getenv(key, default)


AH_API_KEY = get_secret("AH_API_KEY")
AH_TOOL_PACK_ID = get_secret("AH_TOOL_PACK_ID")
OPENAI_API_KEY = get_secret("OPENAI_API_KEY")

# ── Init ──
init_db()
admin_email = get_secret("ADMIN_EMAIL", "admin@example.com")
admin_name = get_secret("ADMIN_NAME", "Admin")
_admin_user = get_user_by_email(admin_email)
if not _admin_user:
    _ah = AgentHandlerClient(AH_API_KEY, AH_TOOL_PACK_ID, "")
    _ah_id = _ah.create_or_find_registered_user(
        origin_user_id=admin_email, origin_user_name=admin_name,
        shared_credential_group={"origin_company_id": "Next Quarter", "origin_company_name": "Next Quarter"},
    )
else:
    _ah_id = _admin_user.get("ah_registered_user_id", "")
seed_admin(admin_email, admin_name, get_secret("ADMIN_PASSWORD", "admin123"),
           ah_tool_pack_id=AH_TOOL_PACK_ID, ah_registered_user_id=_ah_id)

# ── Page config ──
st.set_page_config(page_title="NQ Agent Handler", page_icon="⚡", layout="wide",
                   initial_sidebar_state="expanded")

# ── Custom CSS ──
st.markdown("""
<style>
    /* Hide Streamlit default elements */
    #MainMenu {visibility: hidden;}
    header {visibility: hidden;}
    footer {visibility: hidden;}
    .stDeployButton {display: none;}

    /* Sidebar */
    section[data-testid="stSidebar"] {
        background: linear-gradient(180deg, #0f172a 0%, #1e293b 100%);
        color: white;
    }
    section[data-testid="stSidebar"] .stMarkdown p,
    section[data-testid="stSidebar"] .stMarkdown h3,
    section[data-testid="stSidebar"] .stMarkdown span,
    section[data-testid="stSidebar"] label {
        color: #e2e8f0 !important;
    }
    section[data-testid="stSidebar"] .stRadio label span {
        color: #cbd5e1 !important;
        font-size: 14px;
    }
    section[data-testid="stSidebar"] hr {
        border-color: #334155;
    }
    section[data-testid="stSidebar"] .stCaption p {
        color: #64748b !important;
    }

    /* Chat messages */
    .stChatMessage {border-radius: 12px;}

    /* Cards */
    .metric-card {
        background: white;
        border: 1px solid #e2e8f0;
        border-radius: 12px;
        padding: 20px;
        text-align: center;
    }
    .metric-card h2 {margin: 0; color: #1e293b; font-size: 28px;}
    .metric-card p {margin: 4px 0 0; color: #64748b; font-size: 13px;}
</style>
""", unsafe_allow_html=True)

# ── Session defaults ──
for key, default in [("user", None), ("chat_messages", []), ("nav", "Playground")]:
    if key not in st.session_state:
        st.session_state[key] = default


def login_page():
    col1, col2, col3 = st.columns([1, 1.2, 1])
    with col2:
        st.markdown("")
        st.markdown("")
        st.markdown("""
        <div style="text-align:center; padding: 20px 0">
            <div style="font-size:48px; margin-bottom:8px">⚡</div>
            <h2 style="margin:0; color:#1e293b">NQ Agent Handler</h2>
            <p style="color:#94a3b8; font-size:14px; margin-top:4px">Sign in to continue</p>
        </div>
        """, unsafe_allow_html=True)

        with st.form("login"):
            email = st.text_input("Email", placeholder="you@company.com")
            password = st.text_input("Password", type="password")
            col_a, col_b = st.columns([1, 1])
            submitted = col_a.form_submit_button("Sign in", use_container_width=True, type="primary")

        if submitted:
            if not email or not password:
                st.error("Enter email and password")
            else:
                user = get_user_by_email(email)
                if user and verify_password(password, user["password_hash"]):
                    st.session_state.user = {
                        "id": user["id"], "email": user["email"],
                        "name": user["name"], "role": user["role"],
                        "company": user.get("company", ""),
                        "ah_registered_user_id": user.get("ah_registered_user_id", ""),
                        "ah_tool_pack_id": user.get("ah_tool_pack_id", "") or AH_TOOL_PACK_ID,
                    }
                    st.session_state.chat_messages = []
                    st.rerun()
                else:
                    st.error("Invalid email or password")

        st.caption("Contact your admin if you don't have an account.")


def main_app():
    user = st.session_state.user
    is_admin = user["role"] == "admin"

    # ── Sidebar ──
    with st.sidebar:
        st.markdown("### ⚡ NQ Agents")
        st.caption("Agent Handler Platform")
        st.markdown("")

        if is_admin:
            st.caption("ADMIN")
            nav_options = ["🎯 Playground", "🔌 Connectors", "📦 Tool Packs", "👥 Team"]
        else:
            nav_options = ["🎯 Playground"]

        for opt in nav_options:
            label = opt.split(" ", 1)[1]
            if st.button(opt, use_container_width=True, key=f"nav_{label}",
                        type="primary" if st.session_state.nav == label else "secondary"):
                st.session_state.nav = label
                st.rerun()

        st.markdown("---")
        initials = "".join(w[0] for w in user["name"].split()[:2]).upper()
        role_badge = "🛡️ Admin" if is_admin else "👤 User"
        st.markdown(f"**{user['name']}**")
        st.caption(f"{user['email']} · {role_badge}")

        if st.button("Sign out", use_container_width=True):
            for key in ["user", "chat_messages", "nav"]:
                st.session_state[key] = None if key == "user" else [] if key == "chat_messages" else "Playground"
            st.rerun()

    # ── Page routing ──
    page = st.session_state.nav

    if page == "Playground":
        from views.playground import render
        render(AH_API_KEY, OPENAI_API_KEY, AH_TOOL_PACK_ID)
    elif page == "Connectors" and is_admin:
        from views.connectors import render
        render(AgentHandlerClient(AH_API_KEY, AH_TOOL_PACK_ID, ""))
    elif page == "Tool Packs" and is_admin:
        from views.tool_packs import render
        render(AgentHandlerClient(AH_API_KEY, AH_TOOL_PACK_ID, ""))
    elif page == "Team" and is_admin:
        from views.team import render
        render(AgentHandlerClient(AH_API_KEY, AH_TOOL_PACK_ID, ""), AH_TOOL_PACK_ID)
    else:
        st.session_state.nav = "Playground"
        st.rerun()


if st.session_state.user is None:
    login_page()
else:
    main_app()
