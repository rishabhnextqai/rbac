"""Playground — Streaming chat with Agent Handler tools."""

import streamlit as st
import base64
from openai import OpenAI
from ah_client import AgentHandlerClient
from agent import run_agent


def _encode_token(token: str) -> str:
    return base64.urlsafe_b64encode(token.encode()).decode().rstrip("=")


def render(ah_api_key: str, openai_api_key: str, default_tool_pack_id: str):
    user = st.session_state.user

    if not user.get("ah_registered_user_id"):
        st.error("⚠️ Your account is not linked to Agent Handler. Contact your admin.")
        return

    # ── Header ──
    header_col1, header_col2, header_col3 = st.columns([2, 2, 1])
    with header_col1:
        st.markdown("### 🎯 Playground")

    # Tool Pack selector
    admin_client = AgentHandlerClient(ah_api_key, default_tool_pack_id, "")
    try:
        packs = admin_client.list_tool_packs()
    except Exception:
        packs = []

    pack_map = {p["name"]: p["id"] for p in packs}
    if not pack_map:
        st.warning("No Tool Packs available.")
        return

    with header_col2:
        default_idx = 0
        user_pack = user.get("ah_tool_pack_id") or default_tool_pack_id
        if user_pack in pack_map.values():
            default_idx = list(pack_map.values()).index(user_pack)
        selected_name = st.selectbox("Tool Pack", list(pack_map.keys()), index=default_idx, label_visibility="collapsed")
        selected_pack_id = pack_map[selected_name]

    with header_col3:
        if st.button("🗑️ Clear", use_container_width=True):
            st.session_state.chat_messages = []
            st.rerun()

    # Per-user client
    ah_client = AgentHandlerClient(ah_api_key, selected_pack_id, user["ah_registered_user_id"])

    # ── Tools panel ──
    with st.expander("🔧 Available Tools", expanded=False):
        try:
            tools = ah_client.list_tools()
            auth_tools = [t for t in tools if t["name"].startswith("authenticate_")]
            regular_tools = [t for t in tools if not t["name"].startswith("authenticate_")]

            c1, c2 = st.columns(2)
            c1.metric("Ready", len(regular_tools))
            c2.metric("Need Auth", len(auth_tools))

            if regular_tools:
                for t in regular_tools:
                    st.markdown(f"- `{t['name']}` — {t.get('description', '')[:100]}")
            if auth_tools:
                st.warning("These connectors need authentication (will prompt during chat):")
                st.markdown(", ".join(f"`{t['name'].replace('authenticate_','')}`" for t in auth_tools))
        except Exception as e:
            st.error(f"Failed to load tools: {e}")

    st.divider()

    # ── Chat history ──
    for msg in st.session_state.chat_messages:
        with st.chat_message(msg["role"]):
            if msg.get("content"):
                st.markdown(msg["content"])
            if msg.get("tool_calls"):
                for tc in msg["tool_calls"]:
                    with st.expander(f"🔧 {tc['name']}", expanded=False):
                        if tc.get("args"):
                            st.caption("Arguments")
                            st.json(tc["args"])
                        if tc.get("result"):
                            st.caption("Result")
                            st.json(tc["result"])
            if msg.get("auth"):
                conn = msg["auth"]["connector"]
                token = msg["auth"]["link_token"]
                st.info(f"🔑 **{conn.replace('_', ' ').title()}** needs authentication")
                st.link_button(
                    f"Connect {conn.replace('_', ' ').title()}",
                    f"https://ah-api.merge.dev/magic-link/{_encode_token(token)}/",
                )
                st.caption("After connecting, send your request again.")

    # ── Chat input ──
    if prompt := st.chat_input(f"Ask anything... ({selected_name} tools available)"):
        st.session_state.chat_messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        history = [{"role": m["role"], "content": m.get("content", "")}
                   for m in st.session_state.chat_messages[:-1]
                   if m["role"] in ("user", "assistant") and m.get("content")]

        status_box = st.empty()
        tool_calls = []
        auth_info = None

        def on_status(msg):
            status_box.caption(f"⏳ {msg}")

        def on_tool_call(name, args):
            tool_calls.append({"name": name, "args": args})
            status_box.caption(f"🔧 {name}...")

        def on_tool_result(name, result):
            for tc in tool_calls:
                if tc["name"] == name and "result" not in tc:
                    tc["result"] = result
                    break

        def on_auth_required(connector, link_token):
            nonlocal auth_info
            auth_info = {"connector": connector, "link_token": link_token}

        with st.chat_message("assistant"):
            response = st.write_stream(
                run_agent(
                    user_message=prompt, history=history,
                    ah_client=ah_client, openai_client=OpenAI(api_key=openai_api_key),
                    on_status=on_status, on_tool_call=on_tool_call,
                    on_tool_result=on_tool_result, on_auth_required=on_auth_required,
                )
            )

        status_box.empty()

        msg = {"role": "assistant", "content": response or ""}
        if tool_calls:
            msg["tool_calls"] = tool_calls
        if auth_info:
            msg["auth"] = auth_info
        st.session_state.chat_messages.append(msg)

        if auth_info:
            conn = auth_info["connector"]
            token = auth_info["link_token"]
            st.info(f"🔑 **{conn.replace('_', ' ').title()}** needs authentication")
            st.link_button(
                f"Connect {conn.replace('_', ' ').title()}",
                f"https://ah-api.merge.dev/magic-link/{_encode_token(token)}/",
            )

        st.rerun()
