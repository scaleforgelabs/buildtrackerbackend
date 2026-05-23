#!/bin/bash
set -e

echo "=== Pulling latest code ==="
cd /home/buildtracker/api
git pull origin main

echo "=== Activating venv ==="
source /home/buildtracker/api/venv/bin/activate

echo "=== Installing dependencies ==="
pip install -r requirements.txt --quiet

echo "=== Running migrations ==="
python manage.py migrate --noinput

echo "=== Collecting static files ==="
python manage.py collectstatic --noinput --clear 2>/dev/null || true

echo "=== Restarting services ==="
sudo supervisorctl restart buildtracker:*
sudo systemctl restart nginx

echo "=== Done! ==="
sudo supervisorctl status
