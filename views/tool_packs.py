"""Tool Packs page — Admin only."""

import streamlit as st
from ah_client import AgentHandlerClient


def render(ah_client: AgentHandlerClient):
    st.subheader("Tool Packs")
    st.caption("Bundle connectors and tools together.")

    col1, col2 = st.columns([3, 1])
    with col2:
        show_create = st.button("Create Tool Pack", use_container_width=True)

    with st.spinner("Loading..."):
        try:
            packs = ah_client.list_tool_packs()
        except Exception as e:
            st.error(f"Failed: {e}")
            return

    if not packs and not show_create:
        st.info("No tool packs yet. Create one to get started.")

    # List packs
    for pack in packs:
        total_tools = sum(len(c.get("tools", [])) for c in pack.get("connectors", []))
        with st.expander(f"**{pack['name']}** — {len(pack.get('connectors', []))} connectors, {total_tools} tools"):
            st.code(f"ID: {pack['id']}")
            st.markdown(pack.get("description", ""))

            for conn in pack.get("connectors", []):
                st.markdown(f"- **{conn['name']}** (`{conn['slug']}`) — {len(conn.get('tools', []))} tools")

            if st.button(f"Delete", key=f"del_pack_{pack['id']}"):
                try:
                    ah_client.delete_tool_pack(pack["id"])
                    st.success("Deleted!")
                    st.rerun()
                except Exception as e:
                    st.error(str(e))

    # Create form
    if show_create:
        st.divider()
        st.markdown("### Create New Tool Pack")

        with st.spinner("Loading connectors..."):
            try:
                all_connectors = ah_client.list_connectors()
            except Exception:
                all_connectors = []

        with st.form("create_pack"):
            name = st.text_input("Name", placeholder="e.g. Sales Intelligence Pack")
            description = st.text_area("Description", placeholder="What does this pack do?", height=60)

            st.markdown("**Select Connectors:**")
            selected = []
            for conn in all_connectors:
                if st.checkbox(f"{conn['name']} ({len(conn.get('tools', []))} tools)", key=f"sel_{conn['slug']}"):
                    scope = st.selectbox(
                        f"Auth scope for {conn['name']}",
                        ["INDIVIDUAL", "SHARED", "ORGANIZATION"],
                        key=f"scope_{conn['slug']}"
                    )
                    selected.append({
                        "connector_id": conn["id"],
                        "auth_scope": scope,
                        "tool_names": [t["name"] for t in conn.get("tools", [])],
                    })

            if st.form_submit_button("Create"):
                if not name or not selected:
                    st.error("Name and at least one connector required")
                else:
                    try:
                        result = ah_client.create_tool_pack(name, description, selected)
                        st.success(f"Created: {result['name']} ({result['id']})")
                        st.rerun()
                    except Exception as e:
                        st.error(str(e))
