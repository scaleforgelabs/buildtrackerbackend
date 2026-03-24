import glob

count = 0
for filepath in glob.glob("**/*/models.py", recursive=True):
    if 'venv' in filepath:
        continue
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    lines = content.split('\n')
    modified = False
    for i, line in enumerate(lines):
        if ('created_at =' in line or 'status =' in line) and 'models.' in line:
            if 'db_index=True' not in line:
                if line.rstrip().endswith(')'):
                    lines[i] = line.rstrip()[:-1] + ', db_index=True)'
                    modified = True
    
    if modified:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write('\n'.join(lines))
        count += 1
print(f"Added db_index=True to {count} models.")
