
filepath = r"c:\Users\USER\OneDrive\Desktop\coding\buildtracker_project\buildtracker_backend\buildtracker__backend\subscriptions\views.py"

with open(filepath, 'r', encoding='utf-8') as f:
    lines = f.readlines()

# SubscriptionDetailView.get is lines 65-143 (0-indexed 64-142)
for i in range(64, 143):
    if lines[i].strip():
        lines[i] = "    " + lines[i]

# InitiateSubscriptionView.post is lines 157-302 (0-indexed 156-301)
for i in range(156, 302):
    if lines[i].strip():
        lines[i] = "    " + lines[i]

with open(filepath, 'w', encoding='utf-8') as f:
    f.writelines(lines)
