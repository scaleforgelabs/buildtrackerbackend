import os
import ast

mermaid_lines = ['erDiagram']

def extract_model_info(filepath):
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    try:
        tree = ast.parse(content)
    except Exception as e:
        return

    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            # Check if it inherits from models.Model or AbstractUser
            is_model = any("Model" in getattr(base, 'attr', '') or getattr(base, 'id', '') in ["Model", "AbstractUser", "AbstractBaseUser"] for base in node.bases)
            if not is_model:
                continue

            model_name = node.name
            mermaid_lines.append(f'  {model_name} {{')
            
            relations = []

            for elem in node.body:
                if isinstance(elem, ast.Assign):
                    for target in elem.targets:
                        if isinstance(target, ast.Name):
                            field_name = target.id
                            
                            # Determine type
                            field_type = "Field"
                            if isinstance(elem.value, ast.Call):
                                func = elem.value.func
                                if isinstance(func, ast.Attribute):
                                    field_type = func.attr
                            
                            if 'ForeignKey' in field_type or 'OneToOneField' in field_type:
                                # find related model
                                related_model = "Unknown"
                                if isinstance(elem.value, ast.Call) and len(elem.value.args) > 0:
                                    arg = elem.value.args[0]
                                    if isinstance(arg, ast.Constant):
                                        related_model = arg.value
                                        if '.' in related_model:
                                            related_model = related_model.split('.')[-1]
                                        elif related_model == 'self':
                                            related_model = model_name
                                    elif isinstance(arg, ast.Name):
                                        related_model = arg.id
                                relations.append((related_model, model_name, field_name, field_type))
                                field_type = "FK"
                            elif 'ManyToManyField' in field_type:
                                related_model = "Unknown"
                                if isinstance(elem.value, ast.Call) and len(elem.value.args) > 0:
                                    arg = elem.value.args[0]
                                    if isinstance(arg, ast.Constant):
                                        related_model = arg.value
                                        if '.' in related_model:
                                            related_model = related_model.split('.')[-1]
                                        elif related_model == 'self':
                                            related_model = model_name
                                    elif isinstance(arg, ast.Name):
                                        related_model = arg.id
                                relations.append((related_model, model_name, field_name, field_type))
                                field_type = "M2M"
                            
                            field_type = field_type.replace('Field', '')
                            mermaid_lines.append(f'    {field_type} {field_name}')
            
            mermaid_lines.append('  }')
            
            for rel in relations:
                if 'Unknown' in rel[0]:
                    continue
                if rel[3] == 'ForeignKey':
                    mermaid_lines.append(f'  {rel[0]} ||--o{{ {rel[1]} : "{rel[2]}"')
                elif rel[3] == 'OneToOneField' or rel[3] == 'OneToOne':
                    mermaid_lines.append(f'  {rel[0]} ||--|| {rel[1]} : "{rel[2]}"')
                elif rel[3] == 'ManyToManyField' or rel[3] == 'ManyToMany':
                    mermaid_lines.append(f'  {rel[0]} }}o--o{{ {rel[1]} : "{rel[2]}"')

# Walk through directories
for root, dirs, files in os.walk('.'):
    if 'venv' in root or '__pycache__' in root:
        continue
    if 'models.py' in files:
        extract_model_info(os.path.join(root, 'models.py'))

with open('erd_mermaid.txt', 'w', encoding='utf-8') as f:
    f.write('\n'.join(mermaid_lines))
