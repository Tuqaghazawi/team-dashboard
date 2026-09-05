#!/usr/bin/env bash
#
# Render build step. Fail the build on any error rather than deploying half of it.
#
# The deployed instance has no guideline index. Building one needs the KHCC and
# NCCN PDFs, which are licensed and git-ignored, so the guideline brain and the
# agentic self-check report "unavailable" there. Every other part of the pathway
# works — see README, "What the deployed demo cannot do".
#
# The peri-operative check does not need ai/pharmacy/pharmacy.db: it reads the
# medications synced onto each patient and takes only the rule table, which is a
# CSV in the repository. That database belongs to the standalone Session 3
# scripts.
set -o errexit

pip install --upgrade pip
pip install -r requirements.txt

python manage.py collectstatic --no-input
python manage.py migrate

# Synthetic demo data. Invented patients, safe to create, but seeding is opt-in
# so a redeploy never resets a demo somebody is part-way through.
if [ "${SEED_DEMO:-false}" = "true" ]; then
  python manage.py seed_demo
  python manage.py build_ehr
  python manage.py sync_ehr
fi
