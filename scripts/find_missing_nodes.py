import os

def find_functions(directory, functions):
    results = {}
    for root, dirs, files in os.walk(directory):
        for file in files:
            if file.endswith('.py'):
                path = os.path.join(root, file)
                with open(path, 'r', encoding='utf-8', errors='ignore') as f:
                    content = f.read()
                    for func in functions:
                        if f'def {func}' in content:
                            if func not in results:
                                results[func] = []
                            results[func].append(path)
    return results

if __name__ == '__main__':
    funcs_to_find = ['classify_intent', 'input_guardrails', 'policy_guard']
    found = find_functions('src', funcs_to_find)
    for func, paths in found.items():
        print(f"{func}: {', '.join(paths)}")
