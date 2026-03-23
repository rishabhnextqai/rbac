"""Connectors — Admin only. Browse, search, manage OAuth credentials."""

import streamlit as st
from ah_client import AgentHandlerClient


def render(ah_client: AgentHandlerClient):
    st.markdown("### 🔌 Connectors")
    st.caption("Browse connectors and manage OAuth application credentials.")

    with st.spinner("Loading connectors..."):
        try:
            connectors = ah_client.list_connectors()
            credentials = ah_client.list_app_credentials()
        except Exception as e:
            st.error(f"Failed: {e}")
            return

    cred_map = {}
    for c in credentials:
        cred_map.setdefault(c["connector_slug"], []).append(c)

    # ── Stats ──
    c1, c2, c3 = st.columns(3)
    c1.metric("Total Connectors", len(connectors))
    c2.metric("Configured", len(cred_map))
    c3.metric("Unconfigured", len(connectors) - len(cred_map))

    # ── Search + Filter ──
    col1, col2 = st.columns([3, 1])
    search = col1.text_input("🔍 Search", placeholder="Gong, Slack, Outlook...", label_visibility="collapsed")
    all_cats = sorted(set(cat for c in connectors for cat in (c.get("categories") or [])))
    cat_filter = col2.selectbox("Category", ["All"] + all_cats, label_visibility="collapsed")

    filtered = connectors
    if search:
        q = search.lower()
        filtered = [c for c in filtered if q in c["name"].lower() or q in c["slug"].lower()]
    if cat_filter != "All":
        filtered = [c for c in filtered if cat_filter in (c.get("categories") or [])]

    # Sort: configured first
    filtered.sort(key=lambda c: (0 if c["slug"] in cred_map else 1, c["name"]))

    st.caption(f"Showing {len(filtered)} connectors")

    for conn in filtered:
        slug = conn["slug"]
        has_creds = slug in cred_map
        badge = "✅ Configured" if has_creds else ""
        tool_count = len(conn.get("tools") or [])

        with st.expander(f"{'✅' if has_creds else '⚪'} **{conn['name']}** — {tool_count} tools"):
            # Info
            info_col1, info_col2 = st.columns([2, 1])
            with info_col1:
                if conn.get("description"):
                    st.markdown(conn["description"])
                st.code(f"Slug: {slug}  |  ID: {conn['id']}")
            with info_col2:
                if conn.get("categories"):
                    for cat in conn["categories"]:
                        st.markdown(f"<span style='background:#eff6ff;color:#3b82f6;padding:2px 8px;border-radius:10px;font-size:12px'>{cat}</span>", unsafe_allow_html=True)
                if conn.get("auth_options"):
                    for opt in conn["auth_options"]:
                        st.caption(f"Auth: {opt['type']}")

            # Tools
            if tool_count:
                with st.popover(f"📋 View {tool_count} tools"):
                    for t in conn.get("tools", []):
                        st.markdown(f"`{t['name']}` — {t.get('description', '')[:80]}")

            st.divider()

            # ── Existing credentials ──
            if has_creds:
                st.markdown("**Current Credentials:**")
                for cred in cred_map[slug]:
                    cc1, cc2 = st.columns([5, 1])
                    cc1.code(f"Client ID: {cred['client_id']}  |  Created: {cred.get('created_at','')[:10]}")
                    if cc2.button("🗑️", key=f"del_{cred['id']}", help="Delete credential"):
                        try:
                            ah_client.delete_app_credential(cred["id"])
                            st.success("Deleted!")
                            st.rerun()
                        except Exception as e:
                            st.error(str(e))
            else:
                st.caption("No credentials configured.")

            # ── Add credential ──
            st.markdown("**➕ Add Credential:**")
            st.info("📋 OAuth callback URL: `https://ah.merge.dev/oauth/callback`", icon="📋")

            with st.form(key=f"cred_{slug}"):
                fc1, fc2 = st.columns(2)
                client_id = fc1.text_input("Client ID", key=f"cid_{slug}")
                client_secret = fc2.text_input("Client Secret", type="password", key=f"cs_{slug}")
                scopes = st.text_area(
                    "Scopes (one per line, leave blank for defaults)",
                    key=f"sc_{slug}", height=80,
                    help="OAuth scopes control what data the token can access. E.g., Mail.Read, Calendars.ReadWrite"
                )
                fc3, fc4 = st.columns(2)
                external_id = fc3.text_input("External ID (optional)", key=f"eid_{slug}")

                if st.form_submit_button("Add Credential", type="primary"):
                    if not client_id or not client_secret:
                        st.error("Client ID and Secret required")
                    else:
                        try:
                            ah_client.create_app_credential(
                                connector_slug=slug, client_id=client_id,
                                client_secret=client_secret,
                                external_id=external_id or None,
                                scopes=scopes.strip() or None,
                            )
                            st.success(f"✅ Credential added for {conn['name']}!")
                            st.rerun()
                        except Exception as e:
                            st.error(str(e))
