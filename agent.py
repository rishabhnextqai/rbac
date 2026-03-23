"""Streaming agentic loop — yields chunks for Streamlit's st.write_stream."""

import json
from typing import Generator
from openai import OpenAI
from ah_client import AgentHandlerClient

SYSTEM_PROMPT = (
    "You are a helpful AI assistant with access to external tools. "
    "Use the available tools to help the user accomplish their tasks. "
    "When a tool requires authentication, tell the user they need to authenticate "
    "with the connector first. Always be clear about what actions you're taking."
)


def _to_openai_tools(ah_tools: list[dict]) -> list[dict]:
    funcs = []
    for t in ah_tools:
        name = t["name"]
        # Skip tools the LLM doesn't need — our code handles auth, validation is internal
        if name.startswith("authenticate_") or name.endswith("validate_credential"):
            continue
        fn = {"type": "function", "function": {"name": name, "description": t.get("description", "")}}
        fn["function"]["parameters"] = t.get("inputSchema") or {"type": "object", "properties": {}}
        funcs.append(fn)
    return funcs


def run_agent(
    user_message: str,
    history: list[dict],
    ah_client: AgentHandlerClient,
    openai_client: OpenAI,
    model: str = "gpt-5.2",
    on_status: callable = None,
    on_tool_call: callable = None,
    on_tool_result: callable = None,
    on_auth_required: callable = None,
) -> Generator[str, None, None]:
    """
    Streaming agentic loop. Yields text tokens for the final response.
    Callbacks for status/tool_call/tool_result/auth_required events.
    """

    if on_status: on_status("Loading tools...")
    try:
        ah_tools = ah_client.list_tools()
    except Exception as e:
        yield f"Error loading tools: {e}"
        return

    openai_tools = _to_openai_tools(ah_tools)
    if on_status: on_status(f"Loaded {len(openai_tools)} tools.")

    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    messages.extend(history)
    messages.append({"role": "user", "content": user_message})

    for _ in range(10):
        if on_status: on_status("Thinking...")

        try:
            kwargs = {"model": model, "messages": messages, "stream": True}
            if openai_tools:
                kwargs["tools"] = openai_tools
                kwargs["tool_choice"] = "auto"
            stream = openai_client.chat.completions.create(**kwargs)
        except Exception as e:
            yield f"LLM error: {e}"
            return

        text = ""
        tool_calls_map: dict[int, dict] = {}

        for chunk in stream:
            delta = chunk.choices[0].delta if chunk.choices else None
            if not delta:
                continue
            if delta.content:
                text += delta.content
                yield delta.content
            if delta.tool_calls:
                for tc in delta.tool_calls:
                    idx = tc.index
                    if idx not in tool_calls_map:
                        tool_calls_map[idx] = {"id": "", "name": "", "args": ""}
                    entry = tool_calls_map[idx]
                    if tc.id: entry["id"] = tc.id
                    if tc.function:
                        if tc.function.name: entry["name"] = tc.function.name
                        if tc.function.arguments: entry["args"] += tc.function.arguments

        if text and not tool_calls_map:
            return

        if not tool_calls_map:
            return

        # Build assistant message
        assembled = []
        for idx in sorted(tool_calls_map.keys()):
            e = tool_calls_map[idx]
            assembled.append({"id": e["id"], "type": "function",
                              "function": {"name": e["name"], "arguments": e["args"]}})
        assistant_msg = {"role": "assistant", "tool_calls": assembled}
        if text: assistant_msg["content"] = text
        messages.append(assistant_msg)

        for tc in assembled:
            fn_name = tc["function"]["name"]
            try:
                fn_args = json.loads(tc["function"]["arguments"])
            except json.JSONDecodeError:
                fn_args = {}

            if on_tool_call: on_tool_call(fn_name, fn_args)

            if fn_name.startswith("authenticate_"):
                connector = fn_name.replace("authenticate_", "")
                try:
                    result = ah_client.call_tool(fn_name, fn_args)
                    link_token = None
                    for item in result.get("content", []):
                        if item.get("type") == "text":
                            try:
                                data = json.loads(item["text"])
                                link_token = data.get("link_token")
                            except Exception:
                                pass
                    if not link_token:
                        link_token = ah_client.create_link_token(connector)
                    if on_auth_required: on_auth_required(connector, link_token)
                except Exception:
                    pass
                messages.append({"role": "tool", "tool_call_id": tc["id"],
                    "content": json.dumps({"status": "authentication_completed",
                        "message": f"User authenticated with {connector}. Proceed with their request."})})
                continue

            try:
                if on_status: on_status(f"Executing: {fn_name}...")
                result = ah_client.call_tool(fn_name, fn_args)
                if on_tool_result: on_tool_result(fn_name, result)
                messages.append({"role": "tool", "tool_call_id": tc["id"], "content": json.dumps(result)})
            except Exception as e:
                messages.append({"role": "tool", "tool_call_id": tc["id"], "content": json.dumps({"error": str(e)})})
