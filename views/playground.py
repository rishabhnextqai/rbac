"""Playground — Streaming chat with OpenAI or Anthropic + Agent Handler tools."""

import streamlit as st
import base64
import os

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from ah_client import AgentHandlerClient
from agent import run_agent

MODELS = {
    "GPT-5.2 (OpenAI)": "gpt-5.2",
    "GPT-4.1 (OpenAI)": "gpt-4.1",
    "GPT-4o (OpenAI)": "gpt-4o",
    "Claude Sonnet 4.6 (Anthropic)": "claude-sonnet-4-6",
    "Claude Opus 4.6 (Anthropic)": "claude-opus-4-6",
    "Claude Haiku 4.5 (Anthropic)": "claude-haiku-4-5",
}


def _get_secret(key, default=""):
    try:
        return st.secrets[key]
    except Exception:
        return os.getenv(key, default)


def _encode_token(token: str) -> str:
    return base64.urlsafe_b64encode(token.encode()).decode().rstrip("=")


def _get_llm_client(model_id: str):
    """Return the right client based on model."""
    if model_id.startswith("claude"):
        from anthropic import Anthropic
        return Anthropic(api_key=_get_secret("ANTHROPIC_API_KEY"))
    else:
        from openai import OpenAI
        return OpenAI(api_key=_get_secret("OPENAI_API_KEY"))


def render(ah_api_key: str, openai_api_key: str, default_tool_pack_id: str):
    user = st.session_state.user

    if not user.get("ah_registered_user_id"):
        st.error("⚠️ Your account is not linked to Agent Handler. Contact your admin.")
        return

    # ── Header ──
    h1, h2, h3, h4 = st.columns([2, 1.5, 1.5, 0.8])
    with h1:
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

    with h2:
        user_pack = user.get("ah_tool_pack_id") or default_tool_pack_id
        default_idx = list(pack_map.values()).index(user_pack) if user_pack in pack_map.values() else 0
        selected_name = st.selectbox("Tool Pack", list(pack_map.keys()), index=default_idx, label_visibility="collapsed")
        selected_pack_id = pack_map[selected_name]

    with h3:
        if "selected_model" not in st.session_state:
            st.session_state.selected_model = "GPT-5.2 (OpenAI)"
        model_label = st.selectbox("Model", list(MODELS.keys()), label_visibility="collapsed",
                                   index=list(MODELS.keys()).index(st.session_state.selected_model),
                                   key="model_select")
        st.session_state.selected_model = model_label
        model_id = MODELS[model_label]

    with h4:
        if st.button("🗑️ Clear", use_container_width=True):
            st.session_state.chat_messages = []
            st.rerun()

    # Show model info
    is_anthropic = model_id.startswith("claude")
    tool_limit = "unlimited" if is_anthropic else "128 max"
    st.caption(f"Model: **{model_id}** · Tools: {tool_limit} · Pack: {selected_name}")

    # Per-user client
    ah_client = AgentHandlerClient(ah_api_key, selected_pack_id, user["ah_registered_user_id"])

    # ── Tools panel ──
    with st.expander("🔧 Available Tools & Connections", expanded=False):
        try:
            tools = ah_client.list_tools()
            auth_tools = [t for t in tools if t["name"].startswith("authenticate_")]
            regular_tools = [t for t in tools if not t["name"].startswith("authenticate_") and "validate_credential" not in t["name"]]

            c1, c2, c3 = st.columns(3)
            c1.metric("Ready", len(regular_tools))
            c2.metric("Need Auth", len(auth_tools))
            c3.metric("Sent to LLM", min(len(regular_tools) + len(auth_tools), 128) if not is_anthropic else len(regular_tools) + len(auth_tools))

            # Group regular tools by connector
            connected = set()
            for t in regular_tools:
                if "__" in t["name"]:
                    connected.add(t["name"].split("__")[0])

            if connected:
                st.success(f"Connected: {', '.join(sorted(connected))}")

            if auth_tools:
                st.warning("Need authentication: " + ", ".join(f"**{t['name'].replace('authenticate_','')}**" for t in auth_tools))

            # ── Disconnect / Reconnect ──
            st.markdown("---")
            st.markdown("**Manage Connections**")
            st.caption("Disconnect a connector to re-authenticate (fixes expired tokens)")

            all_connectors = list(connected)
            if all_connectors:
                dc1, dc2 = st.columns([3, 1])
                disconnect_slug = dc1.selectbox("Connector", all_connectors, key="disconnect_slug", label_visibility="collapsed")
                if dc2.button("🔌 Disconnect", use_container_width=True):
                    try:
                        ah_client.delete_user_credentials(disconnect_slug)
                        st.success(f"Disconnected **{disconnect_slug}**. Ask the agent to use it and you'll get a new auth link.")
                        st.rerun()
                    except Exception as e:
                        st.error(str(e))
            else:
                st.caption("No connected connectors to manage.")

            # Tool list
            with st.popover(f"📋 View all {len(regular_tools)} tools"):
                for t in regular_tools:
                    st.markdown(f"`{t['name']}` — {t.get('description', '')[:100]}")

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

    # ── Chat input ──
    if prompt := st.chat_input(f"Ask anything... ({selected_name} · {model_id})"):
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

        llm_client = _get_llm_client(model_id)

        with st.chat_message("assistant"):
            response = st.write_stream(
                run_agent(
                    user_message=prompt, history=history,
                    ah_client=ah_client, llm_client=llm_client, model=model_id,
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
