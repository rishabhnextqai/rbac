"""Team Management — Admin only. Invite, manage, link users."""

import streamlit as st
from database import (
    list_users, create_user, update_user, delete_user,
    hash_password, get_user_by_email,
)
from ah_client import AgentHandlerClient


def render(ah_client: AgentHandlerClient, default_tool_pack_id: str):
    st.markdown("### 👥 Team Management")
    st.caption("Invite members. Each gets their own Agent Handler identity with isolated credentials.")

    # ── Stats ──
    users = list_users()
    admins = [u for u in users if u["role"] == "admin"]
    members = [u for u in users if u["role"] == "user"]
    linked = [u for u in users if u.get("ah_registered_user_id")]

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total", len(users))
    c2.metric("Admins", len(admins))
    c3.metric("Users", len(members))
    c4.metric("AH Linked", len(linked))

    # ── Invite ──
    if "show_invite" not in st.session_state:
        st.session_state.show_invite = False

    if st.button("➕ Invite New Member", type="primary"):
        st.session_state.show_invite = not st.session_state.show_invite
        st.rerun()

    if st.session_state.show_invite:
        st.markdown("---")
        st.markdown("#### Invite New Member")
        st.info("Creates a local account AND registers them in Agent Handler with isolated credentials.", icon="ℹ️")

        name = st.text_input("Full Name", key="inv_name")
        email = st.text_input("Email", key="inv_email")
        password = st.text_input("Temporary Password", type="password", key="inv_pw")
        ic1, ic2 = st.columns(2)
        role = ic1.selectbox("Role", ["user", "admin"], key="inv_role")
        company = ic2.text_input("Company", value="Next Quarter", key="inv_company")

        bc1, bc2 = st.columns(2)
        if bc1.button("Create & Link", type="primary", use_container_width=True):
            if not name or not email or not password:
                st.error("All fields required")
            elif get_user_by_email(email):
                st.error(f"{email} already exists")
            else:
                with st.spinner("Creating in Agent Handler..."):
                    try:
                        ah_user_id = ah_client.create_or_find_registered_user(
                            origin_user_id=email, origin_user_name=name,
                            shared_credential_group={
                                "origin_company_id": company or "default",
                                "origin_company_name": company or "Default",
                            },
                        )
                    except Exception as e:
                        ah_user_id = ""
                        st.warning(f"AH issue: {e}")

                try:
                    create_user(
                        email=email, name=name,
                        password_hash=hash_password(password), role=role,
                        ah_registered_user_id=ah_user_id,
                        ah_tool_pack_id=default_tool_pack_id, company=company,
                    )
                    st.success(f"✅ **{name}** invited!" + (f" AH ID: `{ah_user_id[:16]}...`" if ah_user_id else ""))
                    st.session_state.show_invite = False
                    st.rerun()
                except Exception as e:
                    st.error(str(e))

        if bc2.button("Cancel", use_container_width=True):
            st.session_state.show_invite = False
            st.rerun()

    # ── Team list ──
    st.markdown("---")
    st.markdown("#### Current Team")

    if not users:
        st.info("No team members.")
        return

    for user in users:
        is_me = user["id"] == st.session_state.user["id"]
        role_icon = "🛡️" if user["role"] == "admin" else "👤"
        linked_badge = "✅" if user.get("ah_registered_user_id") else "❌"
        you_badge = " *(you)*" if is_me else ""

        with st.expander(f"{role_icon} **{user['name']}**{you_badge} ({user['email']}) — {linked_badge} AH"):
            mc1, mc2, mc3 = st.columns(3)
            mc1.markdown(f"**Role:** {user['role']}")
            mc2.markdown(f"**Company:** {user.get('company') or '—'}")
            mc3.markdown(f"**AH Linked:** {linked_badge}")

            if user.get("ah_registered_user_id"):
                st.code(f"AH User ID: {user['ah_registered_user_id']}")

            if not is_me:
                dc1, dc2 = st.columns(2)
                new_role = dc1.selectbox("Change role", ["user", "admin"],
                    index=0 if user["role"] == "user" else 1, key=f"r_{user['id']}")
                if dc1.button("Update", key=f"up_{user['id']}"):
                    update_user(user["id"], role=new_role)
                    st.success(f"Updated to {new_role}")
                    st.rerun()
                if dc2.button(f"🗑️ Remove", key=f"rm_{user['id']}"):
                    delete_user(user["id"])
                    st.success(f"Removed {user['name']}")
                    st.rerun()
