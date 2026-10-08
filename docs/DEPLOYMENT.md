# Deployment auf Azure – Schritt für Schritt

Dauer beim ersten Mal: etwa 45 Minuten, davon 15 Minuten Warten auf Azure.
Kosten: rund 5 € pro Woche aus dem Azure-for-Students-Guthaben, dazu etwa 0,27 $ Claude-Kosten pro Content-Paket.

## Was am Ende in Azure läuft

```
                         GitHub (Code)
                              │  push auf main
                              ▼
                      GitHub Actions ──── OIDC-Login (kein Passwort) ───┐
                      testen, bauen, ausrollen                          │
                              │                                         ▼
┌──────────────────── Resource Group rg-contentforge-dev (francecentral) ──────────────────────┐
│                                                                                               │
│   Container Registry ──Image──▶ Container App (FastAPI + Dashboard) ──▶ Claude API          │
│        (ACR)                     │  Managed Identity                                          │
│                                  ├──liest Secrets──▶ Key Vault (Claude-Key, App-Key, DB-URL) │
│                                  ├──speichert─────▶ PostgreSQL Flexible Server               │
│                                  ├──veröffentlicht▶ Storage Account (Static Website)  ◀── Besucher
│                                  └──Logs─────────▶ Log Analytics                             │
└───────────────────────────────────────────────────────────────────────────────────────────────┘
```

Alles davon beschreibt `infra/terraform/main.tf`. Nichts wird im Portal zusammengeklickt.

---

## Teil A – Infrastruktur mit Terraform

### Schritt 1: Voraussetzungen prüfen

```bash
az account show --query "{name:name, user:user.name}" -o table   # Azure for Students, angemeldet?
terraform -version                                               # >= 1.6
az provider register --namespace Microsoft.Storage --wait        # einmalig, war noch nicht registriert
```

Falls `az account show` einen Fehler zeigt: `az login`.

### Schritt 2: Konfiguration anlegen

```bash
cd ~/Desktop/contentforge/infra/terraform
cp terraform.tfvars.example terraform.tfvars
openssl rand -hex 24          # Ausgabe kopieren -> wird dein app_api_key
open -e terraform.tfvars
```

In `terraform.tfvars` eintragen:

| Feld | Wert |
|---|---|
| `anthropic_api_key` | dein Claude-Key (steht in `~/Desktop/contentforge/.env`) |
| `app_api_key` | die Ausgabe von `openssl rand` – damit meldest du dich später im Dashboard an |
| `github_repo` | `<dein-github-name>/contentforge` (genau so, wie das Repo in Teil B heißen wird) |

Die Datei ist in `.gitignore` und landet nie auf GitHub.

### Schritt 3: Phase 1 – Registry anlegen

Die Container App braucht beim Anlegen schon ein fertiges Image. Das Image braucht aber eine Registry.
Deshalb zuerst nur die Registry:

```bash
export ARM_SUBSCRIPTION_ID=$(az account show --query id -o tsv)
terraform init
terraform apply -target=azurerm_container_registry.main -var "container_image=noch-nicht-gebaut"
```

Terraform zeigt den Plan (Resource Group, Zufalls-Suffix, Registry) und fragt nach `yes`.
Die Warnung zu `-target` ist an dieser Stelle normal.

### Schritt 4: Erstes Image in Azure bauen

```bash
ACR=$(terraform output -raw acr_name)
az acr build --registry "$ACR" --image contentforge:v1 --build-arg APP_VERSION=v1 ../..
echo "container_image = \"$ACR.azurecr.io/contentforge:v1\"" >> terraform.tfvars
```

`az acr build` lädt den Code hoch und baut das Docker-Image in Azure (ACR Tasks). Docker muss dafür lokal nicht laufen.
`.env` wird dabei nicht hochgeladen, siehe `.dockerignore`.

### Schritt 5: Phase 2 – alles andere

```bash
terraform apply
```

Das legt rund 25 Ressourcen an und dauert 10–15 Minuten, weil PostgreSQL am längsten braucht. Danach:

```bash
terraform output
```

Wichtig sind `dashboard_url` (die App) und `site_url` (die veröffentlichten SEO-Seiten).

### Schritt 6: Ausprobieren

1. `dashboard_url` im Browser öffnen.
2. Unter **System → Profil** deinen Namen eintragen. Er erscheint im Freigabe-Protokoll.
3. **Content-Planung** → ein leeres Feld der Matrix anklicken. Beim ersten Klick fragt das Dashboard nach dem API-Schlüssel,
   dort kommt dein `app_api_key` hin.
   „Offene Zellen erstellen“ startet alle 16 Kombinationen auf einmal, kostet mit Claude rund 4 $ und stößt fast an die
   Kostenbremse von 5 $ pro Tag.
4. Etwa 70 Sekunden warten. Claude schreibt, die Prüfungen laufen, dann steht das Paket unter **Freigaben**.
5. Freigeben → die Seite liegt jetzt im Storage Account unter `site_url`.
6. Unter **System** sollten jetzt „Datenbank: PostgreSQL“ und „Version: v1“ stehen.

---

## Teil B – GitHub und GitHub Actions

### Schritt 7: GitHub CLI einrichten

```bash
brew install gh
gh auth login          # GitHub.com → HTTPS → im Browser anmelden
```

### Schritt 8: Repository anlegen und hochladen

```bash
cd ~/Desktop/contentforge
git init -b main
git add .
git status --short | grep -E "\.env$|tfvars$|tfstate" || echo "OK: keine Geheimnisse im Commit"
git commit -m "ContentForge: KI-Content-Pipeline mit Azure-Deployment"
gh repo create contentforge --private --source=. --push
```

Die `grep`-Zeile muss **„OK“** ausgeben. Steht dort eine Datei, auf keinen Fall committen und erst `.gitignore` prüfen.

Nach dem Push läuft sofort der Workflow **CI** (Tests, Terraform, Docker). **Deploy to Azure** wird noch übersprungen,
weil GitHub die Azure-Werte noch nicht kennt.

> Stimmt der Repo-Name nicht mit `github_repo` aus Schritt 2 überein: `terraform.tfvars` anpassen und `terraform apply`.

### Schritt 9: Azure-Werte an GitHub übergeben

```bash
bash scripts/github_setup.sh
```

Das Skript liest die Terraform-Ausgaben und setzt in GitHub:

| Typ | Name | Woher |
|---|---|---|
| Secret | `AZURE_CLIENT_ID` | Managed Identity `id-contentforge-dev-github` |
| Secret | `AZURE_TENANT_ID` | Tenant der Hochschule |
| Secret | `AZURE_SUBSCRIPTION_ID` | deine Subscription |
| Variable | `ACR_NAME` | Registry |
| Variable | `RESOURCE_GROUP` | Resource Group |
| Variable | `CONTAINER_APP` | Container App |

Zur Kontrolle im Browser: Repo → **Settings → Secrets and variables → Actions**.

### Schritt 10: Erstes automatisches Deployment

```bash
gh workflow run deploy.yml
gh run watch
```

Oder im Browser: Repo → **Actions** → „Deploy to Azure“ → **Run workflow**.
Nach 3–5 Minuten ist alles grün, und unter **System** im Dashboard steht der Commit-SHA statt `v1`.

Ab jetzt reicht ein `git push` auf `main` mit einer Änderung in `app/`, `knowledge/`, `requirements.txt` oder
`Dockerfile`, dann rollt GitHub Actions automatisch aus.

---

## Aufräumen nach dem Gespräch

```bash
cd ~/Desktop/contentforge/infra/terraform
terraform destroy
```

Der Key Vault bleibt wegen Purge Protection 7 Tage „soft-deleted“. Das kostet nichts, und der Zufalls-Suffix verhindert
Namenskonflikte bei einem neuen Deployment.

Zum Pausieren ohne Löschen: `az postgres flexible-server stop -g rg-contentforge-dev -n <postgres_server>`
(Azure startet den Server nach 7 Tagen automatisch wieder).

---

## Wenn etwas schiefgeht

| Fehlermeldung | Ursache und Lösung |
|---|---|
| `RequestDisallowedByPolicy` | Region nicht erlaubt. Student-Subscription: nur francecentral, switzerlandnorth, italynorth, spaincentral, norwayeast |
| `ExpressEnvironmentFeatureNotSupported` | Die Subscription erlaubt nur eine reguläre Container-Apps-Umgebung (belegt durch ein anderes Projekt), neue werden „Express“. ContentForge ist darauf ausgelegt: keine Key-Vault-Referenzen, die App liest die Secrets selbst |
| `MissingSubscriptionRegistration` | `az provider register --namespace <Name> --wait` |
| `403` beim Key-Vault-Secret | Rollen noch nicht aktiv. Terraform wartet 90 s, notfalls `terraform apply` einfach wiederholen |
| Container App startet nicht | `az containerapp logs show -n ca-contentforge-dev -g rg-contentforge-dev --follow` |
| `AADSTS700213: No matching federated identity record` | `github_repo` passt nicht exakt zum Repo (Groß-/Kleinschreibung) |
| `az acr build`: „does not have authorization“ in Actions | Rolle greift noch nicht. 2 Minuten warten, Workflow erneut starten |
| Dashboard meldet „Tagesbudget erreicht“ | Kostenbremse (`daily_budget_usd`, Standard 5 $). In `terraform.tfvars` erhöhen und `terraform apply` |

## Sicherheit im Überblick

- **Keine Secrets im Code oder Image.** Claude-Key, App-Key und Datenbank-URL liegen im Key Vault. Die Container App liest sie
  über ihre Managed Identity (`Key Vault Secrets User`).
- **Keine Registry-Passwörter.** Das Image wird über dieselbe Identity gezogen (`AcrPull`), der Admin-User der ACR ist aus.
- **Kein Storage-Key in der App.** Seiten werden per `DefaultAzureCredential` hochgeladen (`Storage Blob Data Contributor`).
- **Kein Passwort in GitHub.** Workload Identity Federation (OIDC). Azure vertraut nur Tokens aus genau diesem Repo und dem
  Environment `dev`. Die GitHub-Identität darf nur Images bauen und die Container App aktualisieren.
- **Schreibende Endpunkte** verlangen `X-API-Key`, dazu kommt die **Kostenbremse** (`DAILY_BUDGET_USD`).
- **Bewusste Vereinfachungen für die Demo:**
  - Key Vault und PostgreSQL sind öffentlich erreichbar, aber nur mit RBAC bzw. Passwort und TLS nutzbar.
  - Produktiv kämen ein VNet-integriertes Container-Apps-Environment und Private Endpoints dazu.
  - Der Terraform-State liegt lokal und enthält Secrets. Im Team gehört er in ein `backend "azurerm"` mit eingeschränktem
    Zugriff.
