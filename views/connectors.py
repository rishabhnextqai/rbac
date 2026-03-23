"""Connectors page — Admin only. Browse connectors, manage OAuth credentials."""

import streamlit as st
from ah_client import AgentHandlerClient


def render(ah_client: AgentHandlerClient):
    st.subheader("Connectors")
    st.caption("Browse connectors and manage OAuth application credentials.")

    # Load connectors and credentials
    with st.spinner("Loading..."):
        try:
            connectors = ah_client.list_connectors()
            credentials = ah_client.list_app_credentials()
        except Exception as e:
            st.error(f"Failed to load: {e}")
            return

    cred_by_slug = {}
    for c in credentials:
        cred_by_slug.setdefault(c["connector_slug"], []).append(c)

    # Search
    search = st.text_input("Search connectors", placeholder="e.g. Gong, Slack, Outlook...")
    filtered = [c for c in connectors if not search or search.lower() in c["name"].lower() or search.lower() in c["slug"].lower()]

    st.caption(f"{len(filtered)} connectors")

    # Connector grid
    for conn in filtered:
        slug = conn["slug"]
        has_creds = slug in cred_by_slug
        icon = "✅" if has_creds else "⚪"

        with st.expander(f"{icon} **{conn['name']}** (`{slug}`) — {len(conn.get('tools', []))} tools"):
            st.markdown(f"**ID:** `{conn['id']}`")
            if conn.get("description"):
                st.markdown(conn["description"])
            if conn.get("categories"):
                st.markdown(f"**Categories:** {', '.join(conn['categories'])}")

            # Auth options
            if conn.get("auth_options"):
                st.markdown("**Auth methods:**")
                for opt in conn["auth_options"]:
                    fields = ", ".join(s["human_readable_name"] for s in opt.get("secrets", []))
                    st.markdown(f"- {opt['type']}: {fields}")

            # Tools
            if conn.get("tools"):
                with st.popover(f"View {len(conn['tools'])} tools"):
                    for t in conn["tools"]:
                        st.markdown(f"- `{t['name']}` — {t.get('description', '')[:80]}")

            # Existing credentials
            st.divider()
            st.markdown("**Application Credentials:**")
            if has_creds:
                for cred in cred_by_slug[slug]:
                    col1, col2 = st.columns([4, 1])
                    col1.code(f"Client ID: {cred['client_id']}")
                    if col2.button("Delete", key=f"del_{cred['id']}"):
                        try:
                            ah_client.delete_app_credential(cred["id"])
                            st.success("Deleted!")
                            st.rerun()
                        except Exception as e:
                            st.error(str(e))
            else:
                st.caption("No credentials configured.")

            # Add credential form
            st.markdown("**Add Credential:**")
            st.info("OAuth callback URL: `https://ah.merge.dev/oauth/callback`")

            with st.form(key=f"add_cred_{slug}"):
                client_id = st.text_input("Client ID", key=f"cid_{slug}")
                client_secret = st.text_input("Client Secret", type="password", key=f"csec_{slug}")
                scopes = st.text_area("Scopes (one per line)", key=f"scopes_{slug}", height=80)
                external_id = st.text_input("External ID (optional)", key=f"eid_{slug}")

                if st.form_submit_button("Add Credential"):
                    if not client_id or not client_secret:
                        st.error("Client ID and Secret are required")
                    else:
                        try:
                            ah_client.create_app_credential(
                                connector_slug=slug,
                                client_id=client_id,
                                client_secret=client_secret,
                                external_id=external_id or None,
                                scopes=scopes or None,
                            )
                            st.success(f"Credential added for {conn['name']}!")
                            st.rerun()
                        except Exception as e:
                            st.error(str(e))
