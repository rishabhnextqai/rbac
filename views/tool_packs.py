"""Tool Packs — Admin only. Create, view, delete."""

import streamlit as st
from ah_client import AgentHandlerClient


def render(ah_client: AgentHandlerClient):
    st.markdown("### 📦 Tool Packs")
    st.caption("Bundle connectors and tools. Assign to users via the Team page.")

    if "show_create_pack" not in st.session_state:
        st.session_state.show_create_pack = False

    col1, col2 = st.columns([3, 1])
    with col2:
        if st.button("➕ Create Tool Pack", use_container_width=True, type="primary"):
            st.session_state.show_create_pack = not st.session_state.show_create_pack
            st.rerun()

    # ── Existing packs ──
    with st.spinner("Loading..."):
        try:
            packs = ah_client.list_tool_packs()
        except Exception as e:
            st.error(f"Failed: {e}")
            return

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
                        tool_names = ", ".join(f"`{t['name']}`" for t in tools[:5])
                        more = f" +{len(tools)-5} more" if len(tools) > 5 else ""
                        st.caption(f"{tool_names}{more}")

                if st.button(f"🗑️ Delete Pack", key=f"delp_{pack['id']}"):
                    try:
                        ah_client.delete_tool_pack(pack["id"])
                        st.success("Deleted!")
                        st.rerun()
                    except Exception as e:
                        st.error(str(e))
    elif not st.session_state.show_create_pack:
        st.info("No tool packs yet. Create one to get started.")

    # ── Create form ──
    if st.session_state.show_create_pack:
        st.divider()
        st.markdown("### Create New Tool Pack")

        with st.spinner("Loading connectors..."):
            try:
                all_connectors = ah_client.list_connectors()
            except Exception:
                all_connectors = []
                st.error("Failed to load connectors")

        name = st.text_input("Pack Name", placeholder="e.g. Sales Intelligence Pack")
        description = st.text_area("Description", height=60)

        st.markdown("**Select Connectors & Auth Scope:**")
        st.caption("INDIVIDUAL = each user authenticates themselves. SHARED = one person authenticates for the whole company.")

        selected = []
        for conn in all_connectors:
            tools = conn.get("tools", [])
            if st.checkbox(f"{conn['name']} ({len(tools)} tools)", key=f"sel_{conn['slug']}"):
                scope = st.selectbox(
                    f"Auth scope for {conn['name']}",
                    ["INDIVIDUAL", "SHARED"],
                    key=f"scope_{conn['slug']}",
                    help="INDIVIDUAL: each user authenticates. SHARED: one auth shared per company."
                )
                selected.append({
                    "connector_id": conn["id"],
                    "auth_scope": scope,
                    "tool_names": [t["name"] for t in tools],
                })

        col_a, col_b = st.columns(2)
        if col_a.button("Create Tool Pack", type="primary", use_container_width=True):
            if not name or not selected:
                st.error("Name and at least one connector required")
            else:
                with st.spinner("Creating..."):
                    try:
                        result = ah_client.create_tool_pack(name, description, selected)
                        st.success(f"✅ Created **{result['name']}**")
                        st.session_state.show_create_pack = False
                        st.rerun()
                    except Exception as e:
                        st.error(str(e))
        if col_b.button("Cancel", use_container_width=True):
            st.session_state.show_create_pack = False
            st.rerun()
