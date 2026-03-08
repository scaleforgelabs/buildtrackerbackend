import os
import glob

def process_file(filepath):
    with open(filepath, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    out_lines = []
    has_adrf = any('from adrf.decorators import api_view' in l for l in lines)
    if has_adrf:
        print(f"Skipping {filepath}, already has adrf")
        return

    i = 0
    in_api_view_function = False
    function_indent = 0
    
    while i < len(lines):
        line = lines[i]
        
        if 'from rest_framework.decorators import' in line and 'api_view' in line:
            line = line.replace('api_view, ', '').replace(', api_view', '').replace('api_view', '')
            if line.strip() == 'from rest_framework.decorators import':
                i += 1
                continue
            out_lines.append(line)
            i += 1
            continue

        if line.strip().startswith('@api_view'):
            out_lines.append(line)
            
            while i + 1 < len(lines) and not lines[i+1].strip().startswith('def '):
                i += 1
                out_lines.append(lines[i])
            
            i += 1
            def_line = lines[i]
            if def_line.strip().startswith('def '):
                function_def_lines = [def_line]
                while i + 1 < len(lines) and not function_def_lines[-1].strip().endswith(':'):
                    i += 1
                    function_def_lines.append(lines[i])
                
                function_def_lines[0] = function_def_lines[0].replace('def ', 'async def ', 1)
                for dl in function_def_lines:
                    out_lines.append(dl)
                
                function_indent = len(function_def_lines[0]) - len(function_def_lines[0].lstrip())
                inner_indent = function_indent + 4
                
                out_lines.append(' ' * inner_indent + '@sync_to_async\n')
                out_lines.append(' ' * inner_indent + 'def _sync_logic():\n')
                
                i += 1
                while i < len(lines):
                    body_line = lines[i]
                    stripped = body_line.strip()
                    if stripped:
                        line_indent = len(body_line) - len(body_line.lstrip())
                        if line_indent <= function_indent and not stripped.startswith('#'):
                            break
                    
                    if stripped:
                        out_lines.append(' ' * 4 + body_line)
                    else:
                        out_lines.append('\n')
                    i += 1
                
                out_lines.append(' ' * inner_indent + 'return await _sync_logic()\n\n')
                
                if i < len(lines):
                    continue
                else:
                    break
            else:
                out_lines.append(def_line)
                i += 1
                continue
                
        else:
            out_lines.append(line)
            i += 1
            
    if not has_adrf:
        import_idx = 0
        for idx, l in enumerate(out_lines):
            if l.startswith('from ') or l.startswith('import '):
                import_idx = idx
                break
        out_lines.insert(import_idx, 'from adrf.decorators import api_view\n')
        out_lines.insert(import_idx+1, 'from asgiref.sync import sync_to_async\n')

    with open(filepath, 'w', encoding='utf-8') as f:
        f.writelines(out_lines)
    print(f"Processed {filepath}")


if __name__ == '__main__':
    for p in glob.glob("**/*/views.py", recursive=True) + glob.glob("**/*/views/*.py", recursive=True):
        if 'venv' in p: continue
        with open(p, 'r', encoding='utf-8') as f:
            if '@api_view' not in f.read(): continue
        process_file(p)
    print("Done")
