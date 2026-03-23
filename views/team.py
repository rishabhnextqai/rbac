"""Team Management — Admin only."""

import streamlit as st
from database import (
    list_users, create_user, update_user, delete_user,
    hash_password, get_user_by_email,
)
from ah_client import AgentHandlerClient


def render(ah_client: AgentHandlerClient, default_tool_pack_id: str):
    st.subheader("Team Management")
    st.caption("Invite members. Each gets their own Agent Handler identity and isolated credentials.")

    # ── Invite form (always visible) ──
    st.markdown("### Invite New Member")

    name = st.text_input("Full Name", placeholder="John Doe", key="invite_name")
    email = st.text_input("Email", placeholder="john@nextq.ai", key="invite_email")
    password = st.text_input("Temporary Password", type="password", key="invite_pw")
    col1, col2 = st.columns(2)
    role = col1.selectbox("Role", ["user", "admin"], key="invite_role")
    company = col2.text_input("Company", value="Next Quarter", key="invite_company")

    if st.button("Invite & Link to Agent Handler", type="primary"):
        if not name or not email or not password:
            st.error("All fields are required.")
        elif get_user_by_email(email):
            st.error(f"{email} is already registered.")
        else:
            with st.spinner("Creating user in Agent Handler..."):
                try:
                    ah_user_id = ah_client.create_or_find_registered_user(
                        origin_user_id=email,
                        origin_user_name=name,
                        shared_credential_group={
                            "origin_company_id": company or "default",
                            "origin_company_name": company or "Default",
                        },
                    )
                except Exception as e:
                    ah_user_id = ""
                    st.warning(f"AH linking issue: {e}")

            try:
                create_user(
                    email=email, name=name,
                    password_hash=hash_password(password),
                    role=role,
                    ah_registered_user_id=ah_user_id,
                    ah_tool_pack_id=default_tool_pack_id,
                    company=company,
                )
                st.success(f"✅ **{name}** invited! AH ID: `{ah_user_id[:20]}...`" if ah_user_id else f"⚠️ {name} created but AH link failed.")
            except Exception as e:
                st.error(f"Failed: {e}")

    # ── Team list ──
    st.divider()
    st.markdown("### Current Team")

    users = list_users()

    if not users:
        st.info("No team members yet.")
        return

    for user in users:
        is_current = user["id"] == st.session_state.user["id"]
        role_icon = "🛡️" if user["role"] == "admin" else "👤"
        linked = "✅" if user["ah_registered_user_id"] else "❌"

        with st.expander(f"{role_icon} **{user['name']}** ({user['email']}) — {linked} AH Linked"):
            st.markdown(f"**Role:** {user['role']} · **Company:** {user.get('company', '—')}")

            if user["ah_registered_user_id"]:
                st.code(f"AH User ID: {user['ah_registered_user_id']}")
            else:
                st.warning("Not linked to Agent Handler")

            if not is_current:
                col_a, col_b = st.columns(2)
                if col_a.button(f"Delete {user['name']}", key=f"del_{user['id']}"):
                    delete_user(user["id"])
                    st.rerun()
