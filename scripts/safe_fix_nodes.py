import sys

def apply_fixes(file_path):
    with open(file_path, 'r') as f:
        lines = f.readlines()

    new_lines = []
    i = 0
    while i < len(lines):
        line = lines[i]
        
        # Replace execute_action
        if line.startswith('def execute_action(state: AgentState) -> AgentState:'):
            new_lines.append(line)
            new_lines.append('    intent = str(state.get("intent", "")).strip().lower()\n')
            new_lines.append('    message = state.get("message", "").strip()\n')
            new_lines.append('    words = _tokenize(message)\n')
            new_lines.append('\n')
            new_lines.append('    # 1. Rule-based overrides priority\n')
            new_lines.append('    if _is_portal_bound_support_request(message, words):\n')
            new_lines.append('        order_id = _extract_order_reference(message)\n')
            new_lines.append('        tool_result = {"order_id": order_id, "redirect_url": SUPPORT_PORTAL_URL, "support_email": SUPPORT_EMAIL, "support_response_time": SUPPORT_RESPONSE_TIME, "reason": "Managed through account portal"}\n')
            new_lines.append('        return {**state, "action": "portal_redirect", "tool_result": tool_result}\n')
            new_lines.append('\n')
            new_lines.append('    if _is_order_tracking_request(message, words) or intent == "order_tracking":\n')
            new_lines.append('        tool_result = {"redirect_url": ORDER_TRACKING_URL, "reason": "Tracking redirects"}\n')
            new_lines.append('        return {**state, "action": "order_tracking_redirect", "tool_result": tool_result}\n')
            new_lines.append('\n')
            new_lines.append('    if _is_support_contact_request(message, words):\n')
            new_lines.append('        tool_result = {"support_email": SUPPORT_EMAIL, "support_response_time": SUPPORT_RESPONSE_TIME, "support_portal_url": SUPPORT_PORTAL_URL}\n')
            new_lines.append('        return {**state, "action": "support_contact", "tool_result": tool_result}\n')
            new_lines.append('\n')
            new_lines.append('    # 2. Shopping or Knowledge\n')
            new_lines.append('    if intent == "shopping" or _is_knowledge_query(message) or _is_best_sellers_query(message, words):\n')
            new_lines.append('        action = "knowledge_and_search" if _is_knowledge_query(message) else "search_products"\n')
            new_lines.append('        clean_query = "Karungali Rudraksha Rose Quartz" if _is_best_sellers_query(message, words) else _extract_search_query(message)\n')
            new_lines.append('        tool_result = tooling_service.search_products(clean_query)\n')
            new_lines.append('        return {**state, "action": action, "tool_result": tool_result}\n')
            new_lines.append('\n')
            new_lines.append('    # 3. Fallback\n')
            new_lines.append('    return {**state, "action": "general_conversation", "tool_result": {}}\n')
            
            # Skip the old implementation
            i += 1
            while i < len(lines) and not lines[i].startswith('def '):
                i += 1
            continue

        # Replace _deterministic_grounded_fallback
        if line.startswith('def _deterministic_grounded_fallback'):
            new_lines.append(line)
            new_lines.append('    user_message = str(state.get("message", "")).strip()\n')
            new_lines.append('    if product_snippets:\n')
            new_lines.append('        items_text = "\\n".join([f"- **{p.get(\'name\') or p.get(\'title\')}** (**₹{p.get(\'price\')}**)" for p in product_snippets[:4]])\n')
            new_lines.append('        return f"I found some authentic SATMI options for \'{user_message}\':\\n\\n{items_text}\\n\\nWould you like me to narrow this down?"\n')
            new_lines.append('    if policy_context:\n')
            new_lines.append('        return f"Regarding {policy_context[0].get(\'title\')}:\\n\\n{policy_context[0].get(\'content\')}"\n')
            new_lines.append('    return f"I can help with \'{user_message}\'! Could you clarify your goal?"\n')
            
            # Skip old
            i += 1
            while i < len(lines) and not lines[i].startswith('def '):
                i += 1
            continue

        # Update compose_response checks
        if 'if intent == "shopping" and action in {"search_products", "knowledge_and_search"}:' in line:
            new_lines.append(line.replace('intent == "shopping"', 'intent in {"shopping", "general"}'))
            i += 1
            continue
        if 'if intent != "shopping":' in line:
            new_lines.append(line.replace('intent != "shopping"', 'intent not in {"shopping", "general"}'))
            i += 1
            continue

        new_lines.append(line)
        i += 1

    with open(file_path, 'w') as f:
        f.writelines(new_lines)

if __name__ == '__main__':
    apply_fixes('src/satmi_agent/nodes.py')
    print('SUCCESS')
