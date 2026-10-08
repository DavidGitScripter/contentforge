# ContentForge im Gespräch vorstellen

Spickzettel für das Gespräch bei Pexon. Erst kommt das Was und Warum, dann die Demo, dann die Technik zum Nachschlagen.

---

## 1. Worum geht es (60 Sekunden)

> IT-Dienstleister brauchen für jede Kombination aus Leistung und Branche eine eigene Landingpage, also zum Beispiel
> „RAG-Plattform für Banken“ oder „Azure-Migration für Energieversorger“. Bei vier Leistungen und vier Branchen sind das
> schon 16 Seiten, plus LinkedIn-Post und Newsletter. Von Hand dauert das Tage.
>
> ContentForge erstellt diese Pakete mit Claude aus einer gepflegten Wissensbasis. Bevor ein Mensch den Text sieht,
> prüft das System automatisch: Ist jede Zahl durch einen Fakt belegt? Stimmen SEO-Vorgaben und Markenregeln? Ein zweiter
> Claude-Aufruf bewertet als Marketing-Lead. Fällt der Text durch, wird er automatisch überarbeitet. Am Ende gibt ein
> Mensch frei, und erst dann geht die Seite live.
>
> Das Ganze läuft in Azure: Container App, Key Vault, PostgreSQL, Infrastruktur komplett mit Terraform, und jedes
> Update rollt GitHub Actions automatisch aus.

## 2. Der Mehrwert

**Für ein Unternehmen, das es einsetzt**

- **Tempo.** Ein komplettes Paket mit Landingpage, LinkedIn-Post und Newsletter dauert etwa 70 Sekunden statt eines halben
  Tages.
- **Kosten.** Rund 0,27 $ Claude-Kosten pro Paket, gemessen mit echtem Modell. Dazu kommen Infrastrukturkosten von wenigen
  Euro pro Woche. Eine Kostenbremse stoppt bei einem Tageslimit.
- **Keine erfundenen Zahlen.** Der größte Risikofaktor bei KI-Texten sind Halluzinationen. Jede Zahl im Text muss
  wörtlich in einem Fakt aus der Wissensbasis stehen, sonst blockiert die Prüfung. Das ist deterministisch geprüft, nicht
  per KI.
- **Kontrolle bleibt beim Menschen.** Nichts geht ohne Freigabe live. Wer was wann entschieden hat, steht im Protokoll.
  Das passt zu dem, was der EU AI Act an Transparenz und menschlicher Aufsicht verlangt.
- **Messbare Qualität.** Ein Eval-Skript bewertet alle 16 Kombinationen. Ändert man einen Prompt, sieht man sofort, ob
  die Qualität steigt oder fällt. Die CI bricht ab, wenn die Quote unter 100 % fällt.
- **SEO von Anfang an.** Strukturierte Daten (JSON-LD), Sitemap, eigene Gestaltung pro Branche, mobiltauglich.

**Für Pexon als Beratung**

- Das Muster lässt sich übertragen: LLM erzeugt, deterministische Regeln prüfen, ein Mensch gibt frei, Azure-nativer
  Betrieb. Das funktioniert genauso für Angebotsentwürfe, Antworten auf Support-Tickets oder Produkttexte.
- Der Stack ist genau der, den eine Azure-first-Beratung beim Kunden aufbaut: Container Apps, Managed Identity,
  Key Vault, Terraform, CI/CD mit OIDC. Kein Passwort liegt irgendwo im Code.
- Die Wissensbasis (`knowledge/brand.yaml`) ist austauschbar. Für einen neuen Kunden ändert man Marke, Leistungen,
  Branchen und Fakten, der Code bleibt gleich.

**Was es über mich zeigt (Bezug zur Stelle)**

Python, API-Integration (Claude-SDK mit Structured Outputs), Prompt Engineering mit versionierten Prompts und Evals,
Automatisierung (Batch-Läufe, Webhook-Schnittstelle) und Cloud-Betrieb auf Azure.

---

## 3. Demo-Drehbuch (10–12 Minuten)

**Vorher (am Morgen):**
- Dashboard einmal öffnen, damit die App warm ist.
- 3–4 Pakete sollten schon fertig sein, eines davon freigegeben.
- Browser-Tabs vorbereiten:
  1. Dashboard (`dashboard_url`)
  2. veröffentlichte Seiten (`site_url`)
  3. GitHub → Actions
  4. Azure-Portal → Resource Group `rg-contentforge-dev`
  5. VS Code mit dem Projekt

| # | Zeigen | Sagen |
|---|---|---|
| 1 | **Übersicht** im Dashboard | „Das läuft gerade live in Azure, nicht auf meinem Laptop.“ Kennzahlen: Gate-Quote, Kosten, offene Freigaben |
| 2 | **Content-Planung** → leeres Feld anklicken | „Ich starte jetzt ein echtes Paket mit Claude. Das dauert gut eine Minute, in der Zeit zeige ich Azure.“ |
| 3 | **Azure-Portal** → Resource Group | Die Bausteine durchgehen (siehe Abschnitt 4). Container App → *Revisions* zeigt jede ausgerollte Version |
| 4 | Zurück: Vorgang öffnen → Tab **Prüfung** | Regelprüfungen (SEO, Marke, Faktenbelege) und Bewertung durch Claude als Marketing-Lead. Bei Überarbeitungen sieht man, was beim ersten Entwurf falsch war |
| 5 | Tab **Inhalte** → Vorschau, Handy-Ansicht | Landingpage, LinkedIn-Post, Newsletter. Zahlen sind hervorgehoben, jede stammt aus einem Fakt der Wissensbasis |
| 6 | **Freigeben** | „Erst jetzt geht die Seite live, und das Protokoll hält fest, wer freigegeben hat.“ |
| 7 | Tab mit `site_url` neu laden | Die Seite liegt jetzt im Azure Storage (Static Website), mit Sitemap und strukturierten Daten |
| 8 | **GitHub → Actions** | Einen grünen Lauf von „Deploy to Azure“ öffnen: Tests → Image bauen → ausrollen → Health-Check (Abschnitt 5) |
| 9 | Optional live: kleine Änderung pushen | Etwa einen Text in `knowledge/brand.yaml`. Nach ~4 Min steht unter **System** die neue Version (Commit-SHA) |
| 10 | **VS Code** → `infra/terraform/main.tf` | „Die komplette Infrastruktur ist Code. Ein `terraform destroy` und alles ist weg, ein `apply` und alles ist wieder da.“ |

> Bei Schritt 9 darf gerade kein Paket in Arbeit sein. Beim Neustart markiert die neue Version unterbrochene Vorgänge
> als fehlgeschlagen.

---

## 4. Die Azure-Bausteine – was, warum, wo im Code

Alles steht in [infra/terraform/main.tf](../infra/terraform/main.tf).

| Baustein | Was er macht | Warum so | Code |
|---|---|---|---|
| **Resource Group** | Klammer um alle Ressourcen | Ein Ort für Kosten, Rechte, Aufräumen | `main.tf:24` |
| **Container Registry (ACR)** | Speichert die Docker-Images | Privat, Admin-Zugang aus, Zugriff nur per Identität | `main.tf:52` |
| **Managed Identity** | Ausweis der App gegenüber Azure | Die App braucht kein einziges Passwort, um Registry, Key Vault und Storage zu nutzen | `main.tf:43`, Rollen ab `main.tf:61` |
| **Key Vault** | Tresor für Claude-Key, App-Key, DB-Verbindung | Secrets nie im Code, Image oder in der App-Konfiguration. Die App liest sie beim Start selbst | `main.tf:74`, Code: [config.py:59](../app/config.py) |
| **PostgreSQL Flexible Server** | Datenbank für Vorgänge, Prüfungen, Protokoll | Lokal reicht SQLite, im Container wäre die Datei nach jedem Deployment leer | `main.tf:147` |
| **Storage Account (Static Website)** | Hostet die freigegebenen SEO-Seiten | Statisches HTML ist schnell, billig, SEO-freundlich. Die App lädt per Identität hoch | `main.tf:185`, Code: [publishers.py:24](../app/publishing/publishers.py) |
| **Container Apps Environment + App** | Führt den Container aus (FastAPI + Dashboard) | Serverless Container ohne eigenen Kubernetes-Cluster, mit HTTPS, Revisionen, Health-Probe | `main.tf:219` |
| **Log Analytics** | Sammelt Logs der Container App | Fehlersuche ohne SSH | `main.tf:32` |
| **GitHub-Identität + Federated Credential** | Lässt GitHub Actions ohne Passwort deployen | Azure vertraut nur Tokens aus genau diesem Repo und Environment | `main.tf:344` |

**Wichtige Details, die gern nachgefragt werden:**

- **Woher weiß die App, welche Identität sie nutzt?** `AZURE_CLIENT_ID` (`main.tf:294`). `DefaultAzureCredential` im Python-Code
  findet sie damit automatisch. Lokal nutzt derselbe Code stattdessen das `az login`.
- **Warum zwei Phasen beim ersten Deployment?** Die Container App braucht beim Anlegen ein Image. Das Image braucht eine Registry.
  Also zuerst die Registry, dann das Image, dann der Rest.
- **Warum ignoriert Terraform das Image?** (`main.tf:319`) Terraform ist für die Infrastruktur zuständig, die Pipeline für
  Releases. Sonst würde jedes `terraform apply` auf die alte Version zurückdrehen.
- **Warum genau eine Replica?** (`main.tf:249`) Die Hintergrund-Jobs laufen im Prozess, und Freigaben werden mit einem Lock im
  Prozess serialisiert. Für mehrere Replicas bräuchte es eine Queue (Azure Service Bus) und Sperren in der Datenbank.
- **Warum francecentral statt Deutschland?** Azure for Students erlaubt nur fünf Regionen. Die Daten bleiben in der EU.
  Produktiv wäre `germanywestcentral` eine Variable entfernt.
- **Warum liest die App den Key Vault selbst?** Die Student-Subscription erlaubt insgesamt nur eine reguläre
  Container-Apps-Umgebung, und die belegt meine Masterarbeit. Azure legt dann eine „Express“-Umgebung an, die keine
  Key-Vault-Verweise in der App-Konfiguration kann. Statt die Secrets als Klartext-Variablen zu setzen, bekommt die App nur die
  Key-Vault-Adresse (`main.tf:289`) und holt sich die Werte beim Start per Managed Identity (`load_key_vault_secrets` in
  `app/config.py`). Herausgefunden habe ich das über die Fehlermeldung beim Deployment.

## 5. GitHub Actions erklärt

Zwei Workflows in `.github/workflows/`:

**`ci.yml` – läuft bei jedem Push und Pull Request**

1. `ruff` (Codestil), `pytest` (51 Tests), Eval mit Mock-Modell. Bricht ab, wenn nicht alle 16 Pakete das Gate schaffen.
2. Dieselben Tests noch einmal gegen echtes PostgreSQL. GitHub startet dafür einen Datenbank-Container (`services:`).
3. `terraform fmt` und `terraform validate`.
4. `docker build`, damit das Image garantiert baut.

**`deploy.yml` – läuft bei Push auf `main`, wenn sich App-Code ändert, oder per Knopf**

1. **Tests.** Nur getesteter Code geht live (`needs: test`).
2. **Anmelden per OIDC.** GitHub stellt für diesen einen Lauf ein signiertes Token aus. Azure prüft:
   - Kommt es von GitHub?
   - Aus dem Repo `<user>/contentforge`?
   - Aus dem Environment `dev`?

   Wenn ja, gibt es für ein paar Minuten Zugriff, und zwar nur auf die Registry und die Container App. In GitHub liegen
   nur IDs, kein Passwort (`permissions: id-token: write`).
3. **Image bauen.** `az acr build` baut das Image direkt in Azure. Das Tag ist der Commit-SHA, so ist jede laufende Version
   einem Commit zuzuordnen.
4. **Ausrollen.** `az containerapp update --image …` erzeugt eine neue Revision. Azure schaltet um, sobald sie gesund ist.
5. **Smoke-Test.** Ruft `/api/health` auf, bis die neue Version antwortet. Die URL steht in der Zusammenfassung des Laufs.

**Ein Satz dazu:**

> „Ich pushe Code, GitHub testet ihn, baut ihn in Azure, rollt ihn aus und prüft, ob er läuft. Kein Passwort, kein manueller
> Schritt, und jede Version in Azure kann ich einem Commit zuordnen.“

## 6. Code-Landkarte – wo steht was

| Thema | Datei |
|---|---|
| Ablauf eines Vorgangs: Briefing → Entwurf → Prüfung → Bewertung → Überarbeitung | [app/pipeline/orchestrator.py](../app/pipeline/orchestrator.py), Gate-Schleife `_gate_loop` Zeile 123 |
| Regelprüfungen (SEO, Marke, Sie-Form, Faktenbelege, Zahlen) | [app/pipeline/checks.py](../app/pipeline/checks.py), `run_checks` Zeile 66 |
| Prompts (versioniert) | [app/pipeline/prompts.py](../app/pipeline/prompts.py) |
| Claude-Anbindung: Structured Outputs, Prompt Caching | [app/llm/anthropic_client.py](../app/llm/anthropic_client.py) |
| Mock-Modell für Tests und Offline-Demo | [app/llm/mock_client.py](../app/llm/mock_client.py) |
| Wissensbasis: Marke, Leistungen, Branchen, Fakten | [knowledge/brand.yaml](../knowledge/brand.yaml) |
| REST-API, Freigabe, API-Key, Kostenbremse | [app/api.py](../app/api.py): Lock Zeile 40, API-Key Zeile 43, Budget Zeile 85 |
| Hintergrund-Jobs | [app/pipeline/jobs.py](../app/pipeline/jobs.py) |
| Datenbank: SQLite lokal, PostgreSQL in Azure | [app/db.py](../app/db.py), `get_engine` Zeile 116 |
| Konfiguration über Umgebungsvariablen | [app/config.py](../app/config.py) |
| Landingpages rendern (HTML, JSON-LD, Sitemap) | [app/publishing/renderer.py](../app/publishing/renderer.py), Template [landing_page.html.j2](../app/templates/landing_page.html.j2) |
| Veröffentlichen: lokal oder Azure Blob | [app/publishing/publishers.py](../app/publishing/publishers.py) |
| Container-Image (Multi-Stage, Non-Root) | [Dockerfile](../Dockerfile) |
| Azure-Infrastruktur | [infra/terraform/main.tf](../infra/terraform/main.tf) |
| CI / Deployment | [.github/workflows/ci.yml](../.github/workflows/ci.yml), [deploy.yml](../.github/workflows/deploy.yml) |
| Tests / Evals | [tests/](../tests), [evals/run_eval.py](../evals/run_eval.py) |

## 7. Fragen, die kommen können

**„Warum nicht einfach ChatGPT oder Claude im Browser?“**
Weil man da nichts prüfen, messen oder wiederholen kann. Hier gibt es feste Regeln, Faktenbelege, eine Freigabe, ein Protokoll,
Kosten pro Paket und Evals. Das ist der Unterschied zwischen Ausprobieren und einem Prozess, den eine Firma betreiben kann.

**„Wie verhinderst du Halluzinationen?“**
In drei Stufen:
1. Claude bekommt nur die Fakten aus der Wissensbasis und muss pro Abschnitt angeben, welche Fakten er nutzt.
2. Ein deterministischer Check prüft, ob jede Zahl wörtlich in einem dieser Fakten steht.
3. Ein Mensch gibt frei.

Strukturierte Ausgaben (Pydantic-Schema) sorgen dafür, dass die Antwort immer maschinenlesbar ist.

**„Warum bewertet Claude sich selbst? Ist das nicht zirkulär?“**
Die harten Dinge prüft Code, nicht die KI: Zahlen, Längen, verbotene Begriffe. Claude bewertet nur Wirkung und Tonalität, mit
eigenem Prompt in der Rolle der Marketing-Leitung. Das Modell ist konfigurierbar, man könnte auch ein anderes Modell als
Prüfer nehmen.

**„Was kostet das?“**
Pro Paket rund 0,27 $, gemessen mit echtem Claude. Die Infrastruktur kostet in dieser Größe wenige Euro pro Woche. Das Dashboard
zeigt die Kosten pro Paket und pro Tag, die Kostenbremse blockiert ab einem Limit.

**„Was ist mit Datenschutz?“**
- Verarbeitet werden nur Unternehmensfakten und Marketingtexte, keine personenbezogenen Daten.
- Die Azure-Ressourcen liegen in der EU.
- Beim Kunden würde ich prüfen, Claude über Microsoft Foundry zu beziehen. Dann läuft auch die Modellnutzung über den
  Azure-Vertrag.

**„Was würdest du für Produktion ändern?“**
Ehrlich benennen:
- **Netzwerk.** VNet und Private Endpoints für Key Vault und Datenbank, beide sind im Moment öffentlich erreichbar, aber
  nur mit RBAC bzw. Passwort und TLS.
- **Skalierung.** Eine Job-Queue (Service Bus), damit mehrere Replicas möglich sind.
- **Terraform-State.** Gehört in ein gemeinsames Backend.
- **Login.** Entra-ID-Login fürs Dashboard statt API-Key.
- **Feedback-Schleife.** Search-Console-Daten zurückführen, um zu sehen, welche Seiten wirklich ranken.

**„Warum Container Apps und nicht AKS oder App Service?“**
AKS wäre für einen einzelnen Dienst zu viel Betrieb. App Service ginge auch. Container Apps ist container-nativ, hat Revisionen
für sauberes Ausrollen und kann bei Bedarf auf null skalieren.

**„Warum Terraform und nicht Bicep?“**
Beides wäre in Ordnung. Terraform ist cloud-übergreifend verbreitet, und `plan` zeigt vor jeder Änderung genau, was passiert.

**„Wie viel davon hast du selbst geschrieben?“**
Ehrlich antworten: mit Claude Code als Pair-Programmer gebaut. Die Architektur, die Entscheidungen, das Testen und das
Deployment hast du gemacht und kannst jeden Teil erklären. Für eine Stelle in „Automation & KI“ ist genau das eine Stärke.

---

## 8. Vorbereitung bis Donnerstag

- [ ] **Samstag/Sonntag:** Teil A der [Deployment-Anleitung](DEPLOYMENT.md) durchgehen. Dashboard öffnen, ein Paket erstellen,
      freigeben.
- [ ] **Sonntag/Montag:** Teil B, also GitHub-Repo, `scripts/github_setup.sh`, ein Deployment über Actions.
- [ ] **Montag/Dienstag:** Demo-Drehbuch zweimal laut durchspielen. Abschnitt 4 und 5 ohne Zettel erklären können.
- [ ] **Mittwoch:** 3–4 Pakete erstellen, eines freigeben, Tabs vorbereiten.
- [ ] **Donnerstag früh:** Dashboard einmal öffnen, `/api/health` prüfen.
- [ ] **Nach dem Gespräch:** `terraform destroy`.
