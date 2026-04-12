import re

def apply_fixes(file_path):
    with open(file_path, 'r') as f:
        content = f.read()

    new_execute_action = """def execute_action(state: AgentState) -> AgentState:
    intent = str(state.get("intent", "")).strip().lower()
    message = state.get("message", "").strip()
    words = _tokenize(message)

    user_id = state.get("user_id", "unknown")
    intent = intent or "unknown"

    # 1. Rule-based overrides (Portal/Support/Tracking) ALWAYS take priority
    if _is_portal_bound_support_request(message, words):
        order_id = _extract_order_reference(message)
        tool_result = {
            "order_id": order_id,
            "redirect_url": SUPPORT_PORTAL_URL,
            "support_email": SUPPORT_EMAIL,
            "support_response_time": SUPPORT_RESPONSE_TIME,
            "reason": "Managed through account portal",
        }
        return {
            **state,
            "action": "portal_redirect",
            "tool_result": tool_result,
            "internal_logs": [
                *_state_logs(state),
                {"event": "action_executed", "action": "portal_redirect", "order_id": order_id, "error_count": 0},
            ],
        }

    if _is_order_tracking_request(message, words) or intent == "order_tracking":
        tool_result = {
            "redirect_url": ORDER_TRACKING_URL,
            "reason": "Tracking redirects to global track-your-order page",
        }
        return {
            **state,
            "action": "order_tracking_redirect",
            "tool_result": tool_result,
            "internal_logs": [
                *_state_logs(state),
                {"event": "action_executed", "action": "order_tracking_redirect", "error_count": 0},
            ],
        }

    if _is_support_contact_request(message, words):
        tool_result = {
            "support_email": SUPPORT_EMAIL,
            "support_response_time": SUPPORT_RESPONSE_TIME,
            "support_portal_url": SUPPORT_PORTAL_URL,
            "reason": "Customer requested contact details",
        }
        return {
            **state,
            "action": "support_contact",
            "tool_result": tool_result,
            "internal_logs": [
                *_state_logs(state),
                {"event": "action_executed", "action": "support_contact", "error_count": 0},
            ],
        }

    if "cancel" in words and "order" in words:
        order_id = _extract_order_reference(message)
        tool_result = {
            "order_id": order_id,
            "redirect_url": SUPPORT_PORTAL_URL,
            "support_email": SUPPORT_EMAIL,
            "support_response_time": SUPPORT_RESPONSE_TIME,
            "reason": "No-cancel policy in chatbot channel",
        }
        return {
            **state,
            "action": "cancel_redirect",
            "tool_result": tool_result,
            "internal_logs": [
                *_state_logs(state),
                {"event": "action_executed", "action": "cancel_redirect", "order_id": order_id, "error_count": 0},
            ],
        }

    # 2. Shopping or Knowledge intents
    if intent == "shopping" or _is_knowledge_query(message) or _is_best_sellers_query(message, words):
        action = "knowledge_and_search" if _is_knowledge_query(message) else "search_products"
        clean_query = "Karungali Rudraksha Rose Quartz" if _is_best_sellers_query(message, words) else _extract_search_query(message)
        tool_result = tooling_service.search_products(clean_query)
        tool_result["effective_query"] = clean_query
        return {
            **state,
            "action": action,
            "tool_result": tool_result,
            "internal_logs": [
                *_state_logs(state),
                {"event": "action_executed", "action": action, "query": clean_query, "error_count": 0},
            ],
        }

    # 3. Policy or FAQ intent (non-redirecting)
    if intent == "policy_brand_faq":
        return {
            **state,
            "action": "general_conversation",
            "tool_result": {},
            "internal_logs": [*_state_logs(state), {"event": "action_executed", "action": "general_conversation", "intent": intent}],
        }

    # 4. Fallback for pure general or ambiguous
    return {
        **state,
        "action": "general_conversation",
        "tool_result": {},
        "internal_logs": [
            *_state_logs(state),
            {"event": "action_executed", "action": "general_conversation", "error_count": 0},
        ],
    }"""

    new_fallback = """def _deterministic_grounded_fallback(*, state: AgentState, policy_context: list[dict[str, str]], product_snippets: list[dict[str, Any]], next_step_guidance: str) -> str:
    user_message = str(state.get("message", "")).strip()
    if product_snippets:
        items_list = []
        for p in product_snippets[:4]:
            name = p.get('name') or p.get('title') or 'Product'
            price = p.get('price') or 'NA'
            items_list.append(f'- **{name}** (**₹{price}**)')
        
        items_text = '\\n'.join(items_list)
        return (
            f'I found some authentic SATMI options for "{user_message}" that you might love:\\n\\n'
            f'{items_text}\\n\\n'
            'I specialize in Govt. Lab Certified Karungali and Rudraksha. Would you like me to narrow this down by your budget or spiritual purpose?'
        )

    if policy_context:
        first_topic = str(policy_context[0].get("title") or "policy guidance").strip()
        policy_content = str(policy_context[0].get("content") or "").strip()
        return (
            f'Regarding {first_topic}, here is the information from our store policy:\\n\\n'
            f'{policy_content}\\n\\n'
            'Does this help, or is there anything else I can clarify for you?'
        )

    return (
        f"I'd be happy to help with '{user_message}'! "
        "To give you the most accurate guidance, could you tell me a bit more about what you're looking for? "
        "For example, are you looking for a specific product category or help with an order?"
    )"""

    # We use a non-regex approach first to find the start and end of the functions
    lines = content.splitlines()
    new_lines = []
    skip = False
    
    # This is a bit manual but safer than re.sub with potentially messy existing content
    i = 0
    while i < len(lines):
        line = lines[i]
        if line.startswith('def _deterministic_grounded_fallback'):
            new_lines.append(new_fallback)
            skip = True
        elif line.startswith('def execute_action'):
            new_lines.append(new_execute_action)
            skip = True
        
        if skip:
            # Skip until we find a blank line or the next function definition at column 0
            i += 1
            while i < len(lines) and (lines[i].startswith(' ') or lines[i].startswith('\t') or not lines[i].strip()):
                i += 1
            skip = False
            continue
        
        new_lines.append(line)
        i += 1

    content = '\n'.join(new_lines) + '\n'
    
    # Update compose_response to include general intent for recommended products
    content = content.replace('if intent == "shopping" and action in {"search_products", "knowledge_and_search"}:',
                              'if intent in {"shopping", "general"} and action in {"search_products", "knowledge_and_search", "general_conversation"}:')
    content = content.replace('if intent != "shopping":\\n        recommended_products = []',
                              'if intent not in {"shopping", "general"}:\\n        recommended_products = []')

    with open(file_path, 'w') as f:
        f.write(content)

if __name__ == '__main__':
    apply_fixes('src/satmi_agent/nodes.py')
    print('SUCCESS')
