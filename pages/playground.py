"""Playground — Chat with streaming. Available to ALL authenticated users."""

import streamlit as st
import json
from openai import OpenAI
from ah_client import AgentHandlerClient
from agent import run_agent


def render(ah_api_key: str, openai_api_key: str, default_tool_pack_id: str):
    user = st.session_state.user

    if not user.get("ah_registered_user_id"):
        st.error("Your account is not linked to Agent Handler. Ask your admin to set up your account.")
        return

    # Tool Pack selector
    col1, col2 = st.columns([3, 1])
    with col1:
        st.caption(f"Logged in as **{user['name']}** ({user['email']})")
    with col2:
        if st.button("Clear Chat", use_container_width=True):
            st.session_state.chat_messages = []
            st.rerun()

    # Get tool packs for selector
    admin_client = AgentHandlerClient(ah_api_key, default_tool_pack_id, "")
    try:
        packs = admin_client.list_tool_packs()
    except Exception:
        packs = []

    pack_options = {p["name"]: p["id"] for p in packs}
    if not pack_options:
        st.warning("No Tool Packs available. Ask your admin to create one.")
        return

    selected_pack_name = st.selectbox(
        "Tool Pack",
        list(pack_options.keys()),
        index=list(pack_options.values()).index(user.get("ah_tool_pack_id") or default_tool_pack_id)
        if (user.get("ah_tool_pack_id") or default_tool_pack_id) in pack_options.values() else 0,
    )
    selected_pack_id = pack_options[selected_pack_name]

    # Per-user AH client
    ah_client = AgentHandlerClient(ah_api_key, selected_pack_id, user["ah_registered_user_id"])

    # Show available tools in expander
    with st.expander(f"Available Tools", expanded=False):
        try:
            tools = ah_client.list_tools()
            auth_tools = [t for t in tools if t["name"].startswith("authenticate_")]
            regular_tools = [t for t in tools if not t["name"].startswith("authenticate_")]
            if regular_tools:
                st.success(f"{len(regular_tools)} tools ready")
                for t in regular_tools:
                    st.markdown(f"- `{t['name']}` — {t.get('description', '')[:80]}")
            if auth_tools:
                st.warning(f"{len(auth_tools)} connectors need authentication")
                for t in auth_tools:
                    st.markdown(f"- `{t['name']}`")
        except Exception as e:
            st.error(f"Failed to load tools: {e}")

    st.divider()

    # Chat history
    if "chat_messages" not in st.session_state:
        st.session_state.chat_messages = []

    for msg in st.session_state.chat_messages:
        with st.chat_message(msg["role"]):
            if msg.get("tool_calls"):
                for tc in msg["tool_calls"]:
                    with st.expander(f"Tool: {tc['name']}", expanded=False):
                        st.json(tc.get("args", {}))
                        if tc.get("result"):
                            st.json(tc["result"])
            if msg.get("auth"):
                st.info(f"Authentication required for **{msg['auth']['connector']}**")
                link_token = msg["auth"]["link_token"]
                st.code(f"Link Token: {link_token}", language=None)
                st.link_button(
                    f"Connect {msg['auth']['connector'].title()}",
                    f"https://ah-api.merge.dev/magic-link/{_encode_link_token(link_token)}/",
                )
            st.markdown(msg.get("content", ""))

    # Chat input
    if prompt := st.chat_input("Ask anything... (tools from your Tool Pack are available)"):
        st.session_state.chat_messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        # Build history
        history = [{"role": m["role"], "content": m.get("content", "")}
                   for m in st.session_state.chat_messages[:-1]
                   if m["role"] in ("user", "assistant") and m.get("content")]

        # Status container
        status_container = st.empty()
        tool_calls_collected = []
        auth_info = None

        def on_status(msg):
            status_container.caption(f"⏳ {msg}")

        def on_tool_call(name, args):
            tool_calls_collected.append({"name": name, "args": args})
            status_container.caption(f"🔧 Calling {name}...")

        def on_tool_result(name, result):
            for tc in tool_calls_collected:
                if tc["name"] == name and "result" not in tc:
                    tc["result"] = result
                    break

        def on_auth_required(connector, link_token):
            nonlocal auth_info
            auth_info = {"connector": connector, "link_token": link_token}

        openai_client = OpenAI(api_key=openai_api_key)

        with st.chat_message("assistant"):
            response_text = st.write_stream(
                run_agent(
                    user_message=prompt,
                    history=history,
                    ah_client=ah_client,
                    openai_client=openai_client,
                    on_status=on_status,
                    on_tool_call=on_tool_call,
                    on_tool_result=on_tool_result,
                    on_auth_required=on_auth_required,
                )
            )

        status_container.empty()

        # Save assistant message
        assistant_msg = {"role": "assistant", "content": response_text or ""}
        if tool_calls_collected:
            assistant_msg["tool_calls"] = tool_calls_collected
        if auth_info:
            assistant_msg["auth"] = auth_info
        st.session_state.chat_messages.append(assistant_msg)

        # Show auth link if needed
        if auth_info:
            st.info(f"🔗 Authentication required for **{auth_info['connector']}**")
            link_token = auth_info["link_token"]
            st.link_button(
                f"Connect {auth_info['connector'].title()}",
                f"https://ah-api.merge.dev/magic-link/{_encode_link_token(link_token)}/",
            )
            st.caption("After authenticating, come back and try your request again.")

        st.rerun()


def _encode_link_token(token: str) -> str:
    import base64
    return base64.urlsafe_b64encode(token.encode()).decode().rstrip("=")
