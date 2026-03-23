"""Tool Packs — Admin only. Create, view, delete with searchable connector picker."""

import streamlit as st
from ah_client import AgentHandlerClient


def render(ah_client: AgentHandlerClient):
    st.markdown("### 📦 Tool Packs")
    st.caption("Bundle connectors and tools. Assign to users via the Team page.")

    # Session state for creation flow
    if "creating_pack" not in st.session_state:
        st.session_state.creating_pack = False
    if "selected_connectors" not in st.session_state:
        st.session_state.selected_connectors = {}  # slug → {connector_id, name, auth_scope, tool_names, total_tools}

    # ── Existing packs ──
    with st.spinner("Loading..."):
        try:
            packs = ah_client.list_tool_packs()
        except Exception as e:
            st.error(f"Failed: {e}")
            return

    col1, col2 = st.columns([3, 1])
    with col1:
        st.metric("Tool Packs", len(packs))
    with col2:
        if st.button("➕ Create New", use_container_width=True, type="primary"):
            st.session_state.creating_pack = True
            st.session_state.selected_connectors = {}
            st.rerun()

    if packs:
        for pack in packs:
            connectors = pack.get("connectors", [])
            total_tools = sum(len(c.get("tools", [])) for c in connectors)

            with st.expander(f"**{pack['name']}** — {len(connectors)} connectors · {total_tools} tools"):
                st.code(pack["id"])
                if pack.get("description"):
                    st.markdown(pack["description"])

                for conn in connectors:
                    tools = conn.get("tools", [])
                    st.markdown(f"**{conn['name']}** (`{conn['slug']}`) — {len(tools)} tools")
                    if tools:
                        names = ", ".join(f"`{t['name']}`" for t in tools[:5])
                        more = f" +{len(tools)-5} more" if len(tools) > 5 else ""
                        st.caption(f"{names}{more}")

                if st.button("🗑️ Delete", key=f"dp_{pack['id']}"):
                    try:
                        ah_client.delete_tool_pack(pack["id"])
                        st.success("Deleted!")
                        st.rerun()
                    except Exception as e:
                        st.error(str(e))
    elif not st.session_state.creating_pack:
        st.info("No tool packs yet. Create one to get started.")

    # ── Create Tool Pack ──
    if not st.session_state.creating_pack:
        return

    st.divider()
    st.markdown("### Create New Tool Pack")

    pack_name = st.text_input("Pack Name", placeholder="e.g. Sales Intelligence Pack", key="pack_name")
    pack_desc = st.text_area("Description", height=60, key="pack_desc")

    st.markdown("---")

    # ── Searchable Connector Picker ──
    st.markdown("#### Add Connectors")

    with st.spinner("Loading connectors..."):
        try:
            all_connectors = ah_client.list_connectors()
        except Exception:
            all_connectors = []
            st.error("Failed to load connectors")
            return

    # Search
    search = st.text_input("🔍 Search connectors", placeholder="Gong, Slack, Outlook, Teams...", key="pack_search")

    filtered = all_connectors
    if search:
        q = search.lower()
        filtered = [c for c in filtered if q in c["name"].lower() or q in c["slug"].lower()
                    or q in (c.get("description") or "").lower()]

    # Show search results (max 20 to keep UI snappy)
    if search:
        st.caption(f"{len(filtered)} matches")

    display = filtered[:20] if search else []

    if search and not display:
        st.warning("No connectors match your search")

    for conn in display:
        slug = conn["slug"]
        already_added = slug in st.session_state.selected_connectors
        tools = conn.get("tools", [])
        cats = ", ".join(conn.get("categories") or [])

        col_info, col_btn = st.columns([4, 1])
        with col_info:
            st.markdown(f"**{conn['name']}** — {len(tools)} tools" + (f" · {cats}" if cats else ""))
        with col_btn:
            if already_added:
                st.success("Added ✓")
            else:
                if st.button(f"Add", key=f"add_{slug}", use_container_width=True):
                    st.session_state.selected_connectors[slug] = {
                        "connector_id": conn["id"],
                        "name": conn["name"],
                        "auth_scope": "INDIVIDUAL",
                        "tool_names": [t["name"] for t in tools],
                        "total_tools": len(tools),
                    }
                    st.rerun()

    # ── Selected Connectors ──
    selected = st.session_state.selected_connectors
    if selected:
        st.markdown("---")
        st.markdown(f"#### Selected Connectors ({len(selected)})")

        for slug, info in list(selected.items()):
            sc1, sc2, sc3 = st.columns([3, 2, 1])
            with sc1:
                st.markdown(f"**{info['name']}** — {info['total_tools']} tools")
            with sc2:
                new_scope = st.selectbox(
                    "Scope", ["INDIVIDUAL", "SHARED"],
                    index=0 if info["auth_scope"] == "INDIVIDUAL" else 1,
                    key=f"scope_{slug}",
                    label_visibility="collapsed",
                    help="INDIVIDUAL: each user authenticates. SHARED: one auth shared per company."
                )
                selected[slug]["auth_scope"] = new_scope
            with sc3:
                if st.button("Remove", key=f"rm_{slug}"):
                    del st.session_state.selected_connectors[slug]
                    st.rerun()

    st.markdown("---")

    # ── Create / Cancel ──
    bc1, bc2 = st.columns(2)
    if bc1.button("Create Tool Pack", type="primary", use_container_width=True):
        if not pack_name:
            st.error("Pack name is required")
        elif not selected:
            st.error("Add at least one connector")
        else:
            connectors_payload = [
                {
                    "connector_id": info["connector_id"],
                    "auth_scope": info["auth_scope"],
                    "tool_names": info["tool_names"],
                }
                for info in selected.values()
            ]
            with st.spinner("Creating..."):
                try:
                    result = ah_client.create_tool_pack(pack_name, pack_desc, connectors_payload)
                    st.success(f"✅ Created **{result['name']}** with {len(connectors_payload)} connectors!")
                    st.session_state.creating_pack = False
                    st.session_state.selected_connectors = {}
                    st.rerun()
                except Exception as e:
                    st.error(f"Failed: {e}")

    if bc2.button("Cancel", use_container_width=True):
        st.session_state.creating_pack = False
        st.session_state.selected_connectors = {}
        st.rerun()
