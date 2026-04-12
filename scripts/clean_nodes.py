import os

def clean_nodes_file(file_path):
    with open(file_path, 'r') as f:
        lines = f.readlines()

    new_lines = []
    skip_mode = False
    
    # We'll identify the start and end of the corrupted block
    # Based on the sed output, line 602 is the start of the first good definition.
    # The corruption seems to start after line 636 in the original file.
    
    # Let's find the correct boundaries based on function definitions at column 0
    i = 0
    while i < len(lines):
        line = lines[i]
        
        # Keep the first _deterministic_grounded_fallback but skip any subsequent one 
        # or garbage until the next top-level def
        if line.startswith('def _deterministic_grounded_fallback'):
            if any(l.startswith('def _deterministic_grounded_fallback') for l in new_lines):
                # We already have one, skip this one
                i += 1
                while i < len(lines) and not lines[i].startswith('def '):
                    i += 1
                continue
            else:
                new_lines.append(line)
                i += 1
                # Add the function body until the next def or garbage
                while i < len(lines) and not lines[i].startswith('def '):
                    # Basic sanity check: if line is garbage (starts with quote on column 0)
                    if lines[i].startswith("'") or lines[i].startswith("."):
                        i += 1
                        continue
                    new_lines.append(lines[i])
                    i += 1
                continue
        
        new_lines.append(line)
        i += 1

    with open(file_path, 'w') as f:
        f.writelines(new_lines)

if __name__ == '__main__':
    clean_nodes_file('src/satmi_agent/nodes.py')
    print('SUCCESS')
