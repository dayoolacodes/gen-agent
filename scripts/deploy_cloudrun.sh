#!/usr/bin/env bash
# Deploy the MCP server to Cloud Run with settings from .env, then allow its public hostnames.
#   bash scripts/deploy_cloudrun.sh
# Needs: gcloud logged in, billing on the project, .env with the keys and GOOGLE_SA_JSON (file path).
# Secrets go into a temp file readable only by you, deleted on exit. Nothing is printed.
set -euo pipefail
cd "$(dirname "$0")/.."

PROJECT="${PROJECT:-adaeze-energy}"
REGION="${REGION:-europe-west1}"
SERVICE="${SERVICE:-energy-mcp}"

ENVFILE="$(mktemp)"
trap 'rm -f "$ENVFILE"' EXIT
chmod 600 "$ENVFILE"

.venv/bin/python - "$ENVFILE" <<'EOF'
import json, sys
from dotenv import dotenv_values

env = dotenv_values(".env")
keep = ["MCP_BEARER_TOKEN", "VTPASS_API_KEY", "VTPASS_PUBLIC_KEY", "VTPASS_SECRET_KEY", "VTPASS_SERVICE_ID",
        "VTPASS_VARIATION", "SHEET_ID", "GEN_LITRES_PER_HOUR", "TARIFF_NGN_PER_KWH", "WEEKLY_DIESEL_BUDGET_NGN",
        "MAX_UNATTENDED_NGN", "DIESEL_ALERT_DAYS"]
out = {k: env[k] for k in keep if env.get(k)}
out["VEND_PROVIDER"] = "vtpass"
out["MCP_ALLOWED_HOSTS"] = "set-after-deploy.invalid"  # real hosts are known only after the first deploy
# Cloud Run has no file to mount, so the service-account JSON travels as a string.
out["GOOGLE_SA_JSON_CONTENT"] = json.dumps(json.load(open(env["GOOGLE_SA_JSON"])))
# PORT is deliberately left out: Cloud Run sets it and rejects deploys that try to.
with open(sys.argv[1], "w") as f:
    for k, v in out.items():
        f.write(f"{k}: {json.dumps(str(v))}\n")
print("env vars:", ", ".join(sorted(out)))
EOF

gcloud run deploy "$SERVICE" --source . --region "$REGION" --project "$PROJECT" \
  --allow-unauthenticated --env-vars-file "$ENVFILE" --quiet

# Cloud Run serves on two hostnames (the hashed *.a.run.app and the newer *.run.app). Allow both.
HOSTS="$(gcloud run services describe "$SERVICE" --region "$REGION" --project "$PROJECT" --format=json \
  | .venv/bin/python -c 'import json,sys
d=json.load(sys.stdin)
urls=json.loads(d["metadata"].get("annotations",{}).get("run.googleapis.com/urls","[]")) or [d["status"]["url"]]
print(",".join(sorted({u.split("://",1)[1].rstrip("/") for u in urls + [d["status"]["url"]]})))')"

# ^;^ switches gcloud's list delimiter so the comma in the value survives.
gcloud run services update "$SERVICE" --region "$REGION" --project "$PROJECT" --quiet \
  --update-env-vars "^;^MCP_ALLOWED_HOSTS=$HOSTS"

echo "MCP_ALLOWED_HOSTS=$HOSTS"
for h in ${HOSTS//,/ }; do echo "URL: https://$h"; done
