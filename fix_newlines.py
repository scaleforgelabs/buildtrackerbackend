import os
import glob

def fix_file(filepath):
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    # We are looking for sequences where "    return await _sync_logic()"
    # is attached to the previous statement.
    # For example: "...status=status.HTTP_200_OK)    return await _sync_logic()"
    # We simply replace "    return await _sync_logic()" with "\n    return await _sync_logic()"
    # But ONLY if it's not already preceded by a newline.
    
    modified = False
    new_content = ""
    lines = content.split('\n')
    out_lines = []
    
    for line in lines:
        if 'return await _sync_logic()' in line and not line.strip() == 'return await _sync_logic()':
            # It's attached!
            parts = line.split('    return await _sync_logic()')
            if len(parts) > 1:
                out_lines.append(parts[0])
                out_lines.append('    return await _sync_logic()' + parts[1])
                modified = True
            else:
                out_lines.append(line)
        else:
            out_lines.append(line)
            
    if modified:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write('\n'.join(out_lines))
        print(f"Fixed {filepath}")

if __name__ == '__main__':
    for p in glob.glob("**/*/views.py", recursive=True) + glob.glob("**/*/views/*.py", recursive=True):
        if 'venv' in p: continue
        fix_file(p)
    print("Fix done")
