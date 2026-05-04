import os, sys, django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'buildtracker__backend.settings')
django.setup()
from django.apps import apps
from django.db import models

mermaid_lines = ['erDiagram']

for model in apps.get_models():
    # Only include project models
    app_label = model._meta.app_label
    if app_label in ['admin', 'auth', 'contenttypes', 'sessions']:
        continue
        
    model_name = model._meta.object_name
    mermaid_lines.append(f'  {model_name} {{')
    
    for field in model._meta.get_fields():
        if isinstance(field, models.Field):
            # Normal field
            field_name = field.name
            field_type = field.get_internal_type()
            pk = ' PK' if field.primary_key else ''
            
            # format type if it's too long
            field_type = field_type.replace('Field', '')
            
            mermaid_lines.append(f'    {field_type} {field_name}{pk}')
    mermaid_lines.append('  }')

    # Relationships
    for field in model._meta.get_fields():
        if field.is_relation and hasattr(field, 'related_model') and field.related_model:
             # handle generic relations gracefully
             if field.related_model is None:
                 continue
             
             if hasattr(field.related_model._meta, 'object_name'):
                 related_name = field.related_model._meta.object_name
                 # Only map internally project models, or CustomUser
                 
                 relation_str = ''
                 if field.many_to_one:
                     relation_str = f'  {related_name} ||--o{{ {model_name} : "{field.name}"'
                 elif field.one_to_one and not field.auto_created:
                     relation_str = f'  {related_name} ||--|| {model_name} : "{field.name}"'
                 elif field.many_to_many and not field.auto_created:
                     relation_str = f'  {related_name} }}o--o{{ {model_name} : "{field.name}"'
                     
                 if relation_str:
                     mermaid_lines.append(relation_str)

with open('erd_mermaid.txt', 'w') as f:
    f.write('\n'.join(mermaid_lines))
