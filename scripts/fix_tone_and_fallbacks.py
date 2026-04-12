import os

def fix_tone_and_fallbacks(file_path):
    with open(file_path, 'r') as f:
        content = f.read()

    new_fallback = \"\"\"def _deterministic_grounded_fallback(*, state: AgentState, policy_context: list[dict[str, str]], product_snippets: list[dict[str, Any]], next_step_guidance: str) -> str:
    user_message = str(state.get(\"message\", \"\")).strip()
    if product_snippets:
        items_list = []
        for p in product_snippets[:4]:
            name = p.get('name') or p.get('title') or 'Product'
            price = p.get('price') or 'NA'
            items_list.append(f'- **{name}** (**₹{price}**)')
        
        items_text = '\\n'.join(items_list)
        return (
            f'I found some authentic SATMI options for \"{user_message}\" that you might love:\\n\\n'
            f'{items_text}\\n\\n'
            'I specialize in Govt. Lab Certified Karungali and Rudraksha. Would you like me to narrow this down by your budget or spiritual purpose?'
        )

    if policy_context:
        first_topic = str(policy_context[0].get(\"title\") or \"policy guidance\").strip()
        policy_content = str(policy_context[0].get(\"content\") or \"\").strip()
        return (
            f'Regarding {first_topic}, here is the information from our store policy:\\n\\n'
            f'{policy_content}\\n\\n'
            'Does this help, or is there anything else I can clarify for you?'
        )

    return (
        f\"I'd be happy to help with '{user_message}'! \"
        \"To give you the most accurate guidance, could you tell me a bit more about what you're looking for? \"
        \"For example, are you looking for a specific product category or help with an order?\"
    )\"\"\"

    # Replace the old fallback
    import re
    content = re.sub(r'def _deterministic_grounded_fallback\(.*?\):.*?return \(.*?\)', new_fallback, content, flags=re.DOTALL)

    with open(file_path, 'w') as f:
        f.write(content)

if __name__ == '__main__':
    fix_tone_and_fallbacks('src/satmi_agent/nodes.py')
    print('SUCCESS')
