#!/usr/bin/env bash
# Überträgt die Terraform-Ausgaben als Secrets/Variablen in das GitHub-Repository.
# Voraussetzung: `gh auth login`, Repo existiert, `terraform apply` mit github_repo ist durchgelaufen.
#
#   bash scripts/github_setup.sh
#
# Hinweis: Die drei "Secrets" sind keine Passwörter, sondern IDs. Dank OIDC liegt kein Geheimnis in GitHub.
set -euo pipefail

cd "$(dirname "$0")/../infra/terraform"

secrets=$(terraform output -json github_secrets)
variables=$(terraform output -json github_variables)

if [ "$secrets" = "null" ]; then
  echo "github_repo ist in terraform.tfvars nicht gesetzt – erst eintragen und 'terraform apply' ausführen." >&2
  exit 1
fi

for name in AZURE_CLIENT_ID AZURE_TENANT_ID AZURE_SUBSCRIPTION_ID; do
  gh secret set "$name" --body "$(jq -r ".$name" <<<"$secrets")"
done

for name in ACR_NAME RESOURCE_GROUP CONTAINER_APP; do
  gh variable set "$name" --body "$(jq -r ".$name" <<<"$variables")"
done

echo
echo "Fertig. Kontrolle: gh secret list && gh variable list"
echo "Deployment starten: gh workflow run deploy.yml   (oder einfach auf main pushen)"
