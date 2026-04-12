import os

def final_definitive_fix(file_path):
    with open(file_path, 'r') as f:
        lines = f.readlines()

    new_lines = []
    i = 0
    while i < len(lines):
        line = lines[i]

        # Fix compose_response duplication/wipes
        if 'def compose_response(state: AgentState) -> AgentState:' in line:
            new_lines.append(line)
            i += 1
            # Specifically look for and skip the wipe block
            if i < len(lines) and 'if state.get("intent") != "shopping":' in lines[i]:
                # Skip the entire 4-line block
                i += 4
            continue
        
        # Ensure 'clarification' action is handled (idempotent check)
        if 'elif action == "portal_redirect":' in line and 'action == "clarification"' not in "".join(new_lines[-5:]):
            new_lines.append('    elif action == "clarification":\n')
            new_lines.append('        response = "I want to be as helpful as possible, but I\'m not quite sure how to assist with that. Could you please clarify if you\'re looking for product recommendations, store policies, or help with an order?"\n')
            new_lines.append('        response_source = "clarification_fallback"\n')
            new_lines.append(line)
            i += 1
            continue

        # Update the condition that populates recommended_products
        if 'if intent == "shopping" and action in {"search_products", "knowledge_and_search"}:' in line:
            new_lines.append(line.replace('intent == "shopping"', 'intent in {"shopping", "general"}'))
            i += 1
            continue

        # Update the kill switch
        if 'if intent != "shopping":' in line:
            new_lines.append(line.replace('intent != "shopping"', 'intent not in {"shopping", "general"}'))
            i += 1
            continue
        
        new_lines.append(line)
        i += 1

    with open(file_path, 'w') as f:
        f.writelines(new_lines)

if __name__ == '__main__':
    final_definitive_fix('src/satmi_agent/nodes.py')
    print('SUCCESS')
