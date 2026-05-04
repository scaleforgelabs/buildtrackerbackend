import os

preamble = """# BuildTracker Backend Entity-Relationship Diagram (ERD)

This document contains the complete Entity-Relationship Diagram (ERD) of the BuildTracker Django backend schema. It maps out all the models parsed from the `models.py` files across all backend applications, visualizing their database tables, fields, and relationships.

Below is the visual block diagram representing the tables and their relations as an interactive scalable diagram:

"""

post = """
### Notes:
- **Keys**: `FK` indicates Foreign Key constraints linking to other tables, while `PK` signifies Primary Keys.
- **Lines/Pointers**:
  - `||--o{` : Denotes a "One-to-Many" relationship (e.g. A Workspace has many Members).
  - `||--||` : Denotes a strict "One-to-One" relationship.
  - `}o--o{` : Denotes a "Many-to-Many" relationship.
- **Coverage**: The diagram walks through the schema by traversing all `models.py` definitions.
"""

with open('new_erd.md', 'r', encoding='utf-8') as f:
    mermaid = f.read()

artifact_path = r'C:\Users\USER\.gemini\antigravity\brain\ea85c1ab-f784-4257-9620-39b62da50c3a\backend_schema_erd.md'

with open(artifact_path, 'w', encoding='utf-8') as f:
    f.write(preamble + mermaid + post)

print("Artifact updated successfully!")
