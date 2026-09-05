#!/usr/bin/env bash
# Render build step. Fail the build on any error rather than deploying half of it.
set -o errexit

pip install --upgrade pip
pip install -r requirements.txt

python manage.py collectstatic --no-input
python manage.py migrate

# Synthetic demo data, so the deployed prototype has something to show. This is
# invented data and is safe to create; seeding is skipped unless explicitly
# asked for, so a redeploy never resets a demo someone is using.
if [ "${SEED_DEMO:-false}" = "true" ]; then
  python manage.py seed_demo
  python manage.py build_ehr
  python manage.py sync_ehr
fi
