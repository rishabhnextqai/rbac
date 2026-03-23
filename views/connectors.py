"""Connectors — Admin only. Search, browse, manage OAuth credentials."""

import streamlit as st
from ah_client import AgentHandlerClient


@st.cache_data(ttl=300, show_spinner=False)
def _load_connectors(_api_key: str) -> list[dict]:
    """Cache connectors for 5 min to avoid reloading 117 connectors on every interaction."""
    client = AgentHandlerClient(_api_key, "", "")
    return client.list_connectors()


def render(ah_client: AgentHandlerClient):
    st.markdown("### 🔌 Connectors")
    st.caption("Browse connectors and manage OAuth application credentials.")

    with st.spinner("Loading..."):
        try:
            connectors = _load_connectors(ah_client.api_key)
            credentials = ah_client.list_app_credentials()
        except Exception as e:
            st.error(f"Failed: {e}")
            return

    cred_map = {}
    for c in credentials:
        cred_map.setdefault(c["connector_slug"], []).append(c)

    # ── Stats ──
    c1, c2, c3 = st.columns(3)
    c1.metric("Total", len(connectors))
    c2.metric("Configured", len(cred_map))
    c3.metric("Need Setup", len(connectors) - len(cred_map))

    # ── Search ──
    col1, col2 = st.columns([3, 1])
    search = col1.text_input("🔍 Search connectors", placeholder="Gong, Slack, Outlook, Teams...", key="conn_search")
    all_cats = sorted(set(cat for c in connectors for cat in (c.get("categories") or [])))
    cat_filter = col2.selectbox("Category", ["All"] + all_cats, key="conn_cat")

    # ── Filter ──
    filtered = connectors
    if search:
        q = search.lower()
        filtered = [c for c in filtered if q in c["name"].lower() or q in c["slug"].lower()
                    or q in (c.get("description") or "").lower()]
    if cat_filter != "All":
        filtered = [c for c in filtered if cat_filter in (c.get("categories") or [])]

    # Sort: configured first, then alphabetical
    filtered.sort(key=lambda c: (0 if c["slug"] in cred_map else 1, c["name"]))

    # ── Only show results when searching (don't dump all 117) ──
    if not search and not cat_filter != "All":
        # Show configured connectors + prompt to search
        configured = [c for c in filtered if c["slug"] in cred_map]
        if configured:
            st.markdown(f"**Configured ({len(configured)})**")
            for conn in configured:
                _render_connector(conn, cred_map, ah_client)
        st.info(f"Search above to browse all {len(connectors)} connectors")
        return

    st.caption(f"Showing {min(len(filtered), 30)} of {len(filtered)} matches")

    for conn in filtered[:30]:
        _render_connector(conn, cred_map, ah_client)


def _render_connector(conn: dict, cred_map: dict, ah_client: AgentHandlerClient):
    slug = conn["slug"]
    has_creds = slug in cred_map
    tool_count = len(conn.get("tools") or [])
    cats = ", ".join(conn.get("categories") or [])

    with st.expander(f"{'✅' if has_creds else '⚪'} **{conn['name']}** — {tool_count} tools" + (f" · {cats}" if cats else "")):
        # Info row
        if conn.get("description"):
            st.markdown(conn["description"])
        st.code(f"Slug: {slug}  |  ID: {conn['id']}")

        if conn.get("auth_options"):
            methods = " · ".join(opt["type"] for opt in conn["auth_options"])
            st.caption(f"Auth: {methods}")

        # Tools
        if tool_count:
            with st.popover(f"📋 {tool_count} tools"):
                for t in conn.get("tools", []):
                    st.markdown(f"`{t['name']}` — {t.get('description', '')[:80]}")

        st.divider()

        # ── Existing credentials ──
        if has_creds:
            st.markdown("**Credentials:**")
            for cred in cred_map[slug]:
                cc1, cc2 = st.columns([5, 1])
                cc1.code(f"Client ID: {cred['client_id']}  |  {cred.get('created_at','')[:10]}")
                if cc2.button("🗑️", key=f"dc_{cred['id']}", help="Delete"):
                    try:
                        ah_client.delete_app_credential(cred["id"])
                        st.success("Deleted!")
                        st.rerun()
                    except Exception as e:
                        st.error(str(e))

        # ── Add credential ──
        st.markdown("**➕ Add Credential**")
        st.caption("OAuth callback URL: `https://ah.merge.dev/oauth/callback`")

        with st.form(key=f"cred_{slug}"):
            fc1, fc2 = st.columns(2)
            cid = fc1.text_input("Client ID", key=f"ci_{slug}")
            csec = fc2.text_input("Client Secret", type="password", key=f"cs_{slug}")
            scopes = st.text_area(
                "Scopes (one per line, blank = defaults)",
                key=f"sc_{slug}", height=60,
                help="Controls what data the token can access. E.g. Mail.Read, Calendars.ReadWrite"
            )

            if st.form_submit_button("Add Credential", type="primary"):
                if not cid or not csec:
                    st.error("Client ID and Secret required")
                else:
                    try:
                        ah_client.create_app_credential(
                            connector_slug=slug, client_id=cid, client_secret=csec,
                            scopes=scopes.strip() or None,
                        )
                        st.success(f"✅ Added for {conn['name']}!")
                        st.rerun()
                    except Exception as e:
                        st.error(str(e))
