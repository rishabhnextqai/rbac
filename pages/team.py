"""Team Management — Admin only. Invite users, link to AH, manage roles."""

import streamlit as st
from database import (
    list_users, create_user, update_user, delete_user,
    hash_password, get_user_by_email,
)
from ah_client import AgentHandlerClient


def render(ah_client: AgentHandlerClient, default_tool_pack_id: str):
    st.subheader("Team Management")
    st.caption("Invite members. Each gets their own Agent Handler identity and isolated credentials.")

    col1, col2 = st.columns([3, 1])
    with col2:
        show_invite = st.button("Invite Member", use_container_width=True)

    # List users
    users = list_users()

    if users:
        for user in users:
            is_current = user["id"] == st.session_state.user["id"]
            role_icon = "🛡️" if user["role"] == "admin" else "👤"
            linked = "✅" if user["ah_registered_user_id"] else "❌"

            with st.expander(f"{role_icon} **{user['name']}** ({user['email']}) — {linked} AH Linked"):
                col1, col2, col3 = st.columns(3)
                col1.markdown(f"**Role:** {user['role']}")
                col2.markdown(f"**Company:** {user.get('company', '—')}")
                col3.markdown(f"**AH Linked:** {linked}")

                if user["ah_registered_user_id"]:
                    st.code(f"AH User ID: {user['ah_registered_user_id']}")

                if user.get("ah_tool_pack_id"):
                    st.code(f"Tool Pack: {user['ah_tool_pack_id']}")

                # Edit role
                if not is_current:
                    col_a, col_b, col_c = st.columns(3)
                    new_role = col_a.selectbox(
                        "Role", ["user", "admin"],
                        index=0 if user["role"] == "user" else 1,
                        key=f"role_{user['id']}"
                    )
                    if col_b.button("Update Role", key=f"update_{user['id']}"):
                        update_user(user["id"], role=new_role)
                        st.success(f"Updated {user['name']} to {new_role}")
                        st.rerun()

                    if col_c.button("Remove", key=f"del_{user['id']}"):
                        delete_user(user["id"])
                        st.success(f"Removed {user['name']}")
                        st.rerun()
    else:
        st.info("No team members yet.")

    # Invite form
    if show_invite:
        st.divider()
        st.markdown("### Invite New Member")
        st.info(
            "This will create a local app account AND auto-register them in Agent Handler "
            "with their own isolated credential space."
        )

        with st.form("invite_user"):
            name = st.text_input("Full Name", placeholder="John Doe")
            email = st.text_input("Email", placeholder="john@nextq.ai")
            password = st.text_input("Temporary Password", type="password")
            col1, col2 = st.columns(2)
            role = col1.selectbox("Role", ["user", "admin"])
            company = col2.text_input("Company", value="Next Quarter")

            if st.form_submit_button("Invite & Link to Agent Handler"):
                if not name or not email or not password:
                    st.error("All fields required")
                elif get_user_by_email(email):
                    st.error("Email already registered")
                else:
                    # Create AH registered user
                    with st.spinner("Creating Agent Handler user..."):
                        ah_user_id = ah_client.create_or_find_registered_user(
                            origin_user_id=email,
                            origin_user_name=name,
                            shared_credential_group={
                                "origin_company_id": company or "default",
                                "origin_company_name": company or "Default",
                            },
                        )

                    # Create local user
                    user = create_user(
                        email=email, name=name,
                        password_hash=hash_password(password),
                        role=role,
                        ah_registered_user_id=ah_user_id,
                        ah_tool_pack_id=default_tool_pack_id,
                        company=company,
                    )

                    if ah_user_id:
                        st.success(f"✅ {name} invited and linked to Agent Handler ({ah_user_id[:12]}...)")
                    else:
                        st.warning(f"⚠️ {name} created locally but AH linking failed. Set AH User ID manually.")
                    st.rerun()
