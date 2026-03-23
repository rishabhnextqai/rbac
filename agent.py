"""
Streaming agentic loop — supports both OpenAI and Anthropic.
Auto-handles tool limits per provider.
"""

import json
from typing import Generator
from ah_client import AgentHandlerClient

SYSTEM_PROMPT = (
    "You are a helpful AI assistant with access to external tools. "
    "Use the available tools to help the user accomplish their tasks. "
    "When a tool requires authentication, tell the user they need to authenticate "
    "with the connector first. Always be clear about what actions you're taking."
)

# Provider detection
OPENAI_MODELS = {"gpt-5.2", "gpt-4.1", "gpt-4.1-mini", "gpt-4o", "gpt-4o-mini", "o4-mini"}
ANTHROPIC_MODELS = {"claude-sonnet-4-6", "claude-opus-4-6", "claude-haiku-4-5"}
OPENAI_MAX_TOOLS = 128


def _is_anthropic(model: str) -> bool:
    return model.startswith("claude") or model in ANTHROPIC_MODELS


def _filter_tools(ah_tools: list[dict]) -> list[dict]:
    """Remove only validate_credential tools. Keep authenticate_* so the LLM can trigger auth."""
    return [t for t in ah_tools if "validate_credential" not in t["name"]]


def _to_openai_tools(tools: list[dict], max_tools: int = OPENAI_MAX_TOOLS) -> list[dict]:
    funcs = []
    for t in tools:
        fn = {"type": "function", "function": {
            "name": t["name"], "description": t.get("description", ""),
            "parameters": t.get("inputSchema") or {"type": "object", "properties": {}},
        }}
        funcs.append(fn)
    return funcs[:max_tools]


def _to_anthropic_tools(tools: list[dict]) -> list[dict]:
    """Convert to Anthropic's tool format. No tool limit."""
    return [
        {
            "name": t["name"],
            "description": t.get("description", ""),
            "input_schema": t.get("inputSchema") or {"type": "object", "properties": {}},
        }
        for t in tools
    ]


def run_agent(
    user_message: str,
    history: list[dict],
    ah_client: AgentHandlerClient,
    llm_client,  # OpenAI or Anthropic client
    model: str = "gpt-5.2",
    on_status=None,
    on_tool_call=None,
    on_tool_result=None,
    on_auth_required=None,
) -> Generator[str, None, None]:

    if on_status:
        on_status("Loading tools...")
    try:
        ah_tools = ah_client.list_tools()
    except Exception as e:
        yield f"Error loading tools: {e}"
        return

    filtered = _filter_tools(ah_tools)
    use_anthropic = _is_anthropic(model)

    if on_status:
        provider = "Anthropic" if use_anthropic else "OpenAI"
        on_status(f"Loaded {len(filtered)} tools ({provider} / {model})")

    if use_anthropic:
        yield from _run_anthropic(user_message, history, filtered, ah_client, llm_client, model,
                                  on_status, on_tool_call, on_tool_result, on_auth_required)
    else:
        yield from _run_openai(user_message, history, filtered, ah_client, llm_client, model,
                               on_status, on_tool_call, on_tool_result, on_auth_required)


# ══════════════════════════════════════════════════════════════
#  OpenAI streaming loop
# ══════════════════════════════════════════════════════════════

def _run_openai(user_message, history, tools, ah_client, client, model,
                on_status, on_tool_call, on_tool_result, on_auth_required):

    openai_tools = _to_openai_tools(tools)
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    messages.extend(history)
    messages.append({"role": "user", "content": user_message})

    for _ in range(10):
        if on_status:
            on_status("Thinking...")

        try:
            kwargs = {"model": model, "messages": messages, "stream": True}
            if openai_tools:
                kwargs["tools"] = openai_tools
                kwargs["tool_choice"] = "auto"
            stream = client.chat.completions.create(**kwargs)
        except Exception as e:
            yield f"LLM error: {e}"
            return

        text = ""
        tc_map: dict[int, dict] = {}

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
                    if idx not in tc_map:
                        tc_map[idx] = {"id": "", "name": "", "args": ""}
                    e = tc_map[idx]
                    if tc.id: e["id"] = tc.id
                    if tc.function:
                        if tc.function.name: e["name"] = tc.function.name
                        if tc.function.arguments: e["args"] += tc.function.arguments

        if not tc_map:
            return

        assembled = [{"id": e["id"], "type": "function",
                      "function": {"name": e["name"], "arguments": e["args"]}}
                     for e in (tc_map[i] for i in sorted(tc_map))]

        msg = {"role": "assistant", "tool_calls": assembled}
        if text:
            msg["content"] = text
        messages.append(msg)

        for tc in assembled:
            result_content = _execute_tool(tc["function"]["name"],
                                           tc["function"]["arguments"],
                                           ah_client, on_status, on_tool_call, on_tool_result, on_auth_required)
            messages.append({"role": "tool", "tool_call_id": tc["id"], "content": result_content})


# ══════════════════════════════════════════════════════════════
#  Anthropic streaming loop
# ══════════════════════════════════════════════════════════════

def _run_anthropic(user_message, history, tools, ah_client, client, model,
                   on_status, on_tool_call, on_tool_result, on_auth_required):

    anthropic_tools = _to_anthropic_tools(tools)

    # Convert history to Anthropic format
    messages = []
    for m in history:
        if m["role"] in ("user", "assistant") and m.get("content"):
            messages.append({"role": m["role"], "content": m["content"]})
    messages.append({"role": "user", "content": user_message})

    for _ in range(10):
        if on_status:
            on_status("Thinking...")

        try:
            with client.messages.stream(
                model=model,
                system=SYSTEM_PROMPT,
                messages=messages,
                tools=anthropic_tools,
                max_tokens=8192,
            ) as stream:
                text = ""
                tool_uses = []

                for event in stream:
                    if event.type == "content_block_delta":
                        if hasattr(event.delta, "text"):
                            text += event.delta.text
                            yield event.delta.text
                        elif hasattr(event.delta, "partial_json"):
                            # Tool input streaming — accumulate
                            if tool_uses:
                                tool_uses[-1]["partial"] += event.delta.partial_json
                    elif event.type == "content_block_start":
                        if event.content_block.type == "tool_use":
                            tool_uses.append({
                                "id": event.content_block.id,
                                "name": event.content_block.name,
                                "partial": "",
                            })

                # Get final message
                final = stream.get_final_message()
                stop = final.stop_reason

        except Exception as e:
            yield f"LLM error: {e}"
            return

        if stop != "tool_use":
            return

        # Build assistant message content blocks
        assistant_content = []
        if text:
            assistant_content.append({"type": "text", "text": text})

        # Process tool uses from the final message
        tool_results = []
        for block in final.content:
            if block.type == "tool_use":
                assistant_content.append({
                    "type": "tool_use",
                    "id": block.id,
                    "name": block.name,
                    "input": block.input,
                })

                result_content = _execute_tool(
                    block.name, json.dumps(block.input),
                    ah_client, on_status, on_tool_call, on_tool_result, on_auth_required)

                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": result_content,
                })

        messages.append({"role": "assistant", "content": assistant_content})
        messages.append({"role": "user", "content": tool_results})


# ══════════════════════════════════════════════════════════════
#  Shared tool execution
# ══════════════════════════════════════════════════════════════

def _execute_tool(fn_name: str, fn_args_json: str, ah_client, on_status, on_tool_call, on_tool_result, on_auth_required) -> str:
    try:
        fn_args = json.loads(fn_args_json)
    except json.JSONDecodeError:
        fn_args = {}

    if on_tool_call:
        on_tool_call(fn_name, fn_args)

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
            if on_auth_required:
                on_auth_required(connector, link_token)
        except Exception:
            pass
        return json.dumps({"status": "authentication_completed",
                           "message": f"User authenticated with {connector}. Proceed."})

    try:
        if on_status:
            on_status(f"Executing: {fn_name}...")
        result = ah_client.call_tool(fn_name, fn_args)
        if on_tool_result:
            on_tool_result(fn_name, result)
        return json.dumps(result)
    except Exception as e:
        return json.dumps({"error": str(e)})
