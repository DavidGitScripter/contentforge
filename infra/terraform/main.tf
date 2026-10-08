data "azurerm_client_config" "current" {}

resource "random_string" "suffix" {
  length  = 5
  upper   = false
  special = false
}

locals {
  name     = "${var.project}-${var.environment}"
  compact  = "${var.project}${var.environment}${random_string.suffix.result}"
  app_name = "ca-${local.name}"
  database_url = format(
    "postgresql+psycopg://%s:%s@%s:5432/contentforge?sslmode=require",
    "cfadmin", random_password.db.result, "psql-${local.name}-${random_string.suffix.result}.postgres.database.azure.com",
  )
  tags = {
    project     = var.project
    environment = var.environment
    managed_by  = "terraform"
  }
}

resource "azurerm_resource_group" "main" {
  name     = "rg-${local.name}"
  location = var.location
  tags     = local.tags
}

# --------------------------------------------------------------------------- Observability

resource "azurerm_log_analytics_workspace" "main" {
  name                = "log-${local.name}"
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name
  sku                 = "PerGB2018"
  retention_in_days   = 30
  tags                = local.tags
}

# --------------------------------------------------------------------------- Identität (keine Passwörter im Code)

resource "azurerm_user_assigned_identity" "app" {
  name                = "id-${local.name}"
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name
  tags                = local.tags
}

# --------------------------------------------------------------------------- Container Registry

resource "azurerm_container_registry" "main" {
  name                = substr("acr${local.compact}", 0, 50)
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name
  sku                 = "Basic"
  admin_enabled       = false
  tags                = local.tags
}

resource "azurerm_role_assignment" "app_acr_pull" {
  scope                = azurerm_container_registry.main.id
  role_definition_name = "AcrPull"
  principal_id         = azurerm_user_assigned_identity.app.principal_id
}

# --------------------------------------------------------------------------- Secrets

# Netzwerk: Der Vault bleibt öffentlich erreichbar, der Zugriff ist aber rein RBAC-basiert (nur die App-Identity
# liest, nur der Deployer schreibt). Ein "Deny"-Firewall würde die App aussperren: Azure Container Apps ist kein
# "Trusted Microsoft Service" und kommt ohne VNet nicht am Key-Vault-Firewall vorbei. Härtung für Produktion:
# VNet-integriertes Container-Apps-Environment + Private Endpoint für den Key Vault.
# nosemgrep: terraform.azure.security.keyvault.keyvault-specify-network-acl.keyvault-specify-network-acl
resource "azurerm_key_vault" "main" {
  name                       = substr("kv-${local.compact}", 0, 24)
  location                   = azurerm_resource_group.main.location
  resource_group_name        = azurerm_resource_group.main.name
  tenant_id                  = data.azurerm_client_config.current.tenant_id
  sku_name                   = "standard"
  rbac_authorization_enabled = true
  soft_delete_retention_days = 7
  purge_protection_enabled   = true # gelöschte Secrets 7 Tage wiederherstellbar, kein sofortiges Purge
  tags                       = local.tags

  network_acls {
    default_action = "Allow"
    bypass         = "AzureServices"
  }
}

resource "azurerm_role_assignment" "deployer_kv_officer" {
  scope                = azurerm_key_vault.main.id
  role_definition_name = "Key Vault Secrets Officer"
  principal_id         = data.azurerm_client_config.current.object_id
}

resource "azurerm_role_assignment" "app_kv_reader" {
  scope                = azurerm_key_vault.main.id
  role_definition_name = "Key Vault Secrets User"
  principal_id         = azurerm_user_assigned_identity.app.principal_id
}

# Neue Rollenzuweisungen brauchen in Azure ein bis zwei Minuten, bis sie wirken. Ohne Pause scheitern das
# Schreiben der Secrets (403) oder die erste Revision der Container App (Secret nicht lesbar).
resource "time_sleep" "rbac_propagation" {
  create_duration = "90s"
  depends_on = [
    azurerm_role_assignment.deployer_kv_officer,
    azurerm_role_assignment.app_kv_reader,
    azurerm_role_assignment.app_acr_pull,
  ]
}

resource "azurerm_key_vault_secret" "anthropic_api_key" {
  name         = "anthropic-api-key"
  content_type = "api-key"
  value        = var.anthropic_api_key
  key_vault_id = azurerm_key_vault.main.id
  depends_on   = [time_sleep.rbac_propagation]
}

resource "azurerm_key_vault_secret" "app_api_key" {
  name         = "app-api-key"
  content_type = "api-key"
  value        = var.app_api_key
  key_vault_id = azurerm_key_vault.main.id
  depends_on   = [time_sleep.rbac_propagation]
}

resource "azurerm_key_vault_secret" "database_url" {
  name         = "database-url"
  content_type = "connection-string"
  value        = local.database_url
  key_vault_id = azurerm_key_vault.main.id
  depends_on   = [time_sleep.rbac_propagation]
}

# --------------------------------------------------------------------------- Datenbank (PostgreSQL Flexible Server)

# Lokal läuft ContentForge mit SQLite. In der Cloud wäre eine SQLite-Datei im Container nach jedem Deployment
# leer – deshalb eine verwaltete PostgreSQL-Instanz. Umgeschaltet wird nur über DATABASE_URL.
resource "random_password" "db" {
  length  = 32
  special = false # vermeidet URL-Encoding im Connection-String
}

resource "azurerm_postgresql_flexible_server" "main" {
  name                          = "psql-${local.name}-${random_string.suffix.result}"
  location                      = azurerm_resource_group.main.location
  resource_group_name           = azurerm_resource_group.main.name
  version                       = "16"
  sku_name                      = "B_Standard_B1ms" # Burstable, kleinste Stufe
  storage_mb                    = 32768
  backup_retention_days         = 7
  administrator_login           = "cfadmin"
  administrator_password        = random_password.db.result
  public_network_access_enabled = true
  tags                          = local.tags

  lifecycle {
    ignore_changes = [zone] # Azure wählt die Zone selbst
  }
}

resource "azurerm_postgresql_flexible_server_database" "app" {
  name      = "contentforge"
  server_id = azurerm_postgresql_flexible_server.main.id
  charset   = "UTF8"
  collation = "en_US.utf8"
}

# Erlaubt Verbindungen aus Azure-Diensten (Container Apps hat ohne VNet keine feste Ausgangs-IP).
# Zugriff zusätzlich nur mit Passwort + TLS. Härtung für Produktion: VNet-Integration + Private Endpoint.
resource "azurerm_postgresql_flexible_server_firewall_rule" "azure_services" {
  name             = "AllowAzureServices"
  server_id        = azurerm_postgresql_flexible_server.main.id
  start_ip_address = "0.0.0.0"
  end_ip_address   = "0.0.0.0"
}

# --------------------------------------------------------------------------- Veröffentlichte SEO-Seiten (Static Website)

# Queue-Logging nicht relevant: Der Account dient nur als Static Website (Blob), Queues werden nicht genutzt.
# nosemgrep: terraform.azure.security.storage.storage-queue-services-logging.storage-queue-services-logging
resource "azurerm_storage_account" "site" {
  name                            = substr("st${local.compact}", 0, 24)
  location                        = azurerm_resource_group.main.location
  resource_group_name             = azurerm_resource_group.main.name
  account_tier                    = "Standard"
  account_replication_type        = "LRS"
  min_tls_version                 = "TLS1_2"
  https_traffic_only_enabled      = true
  allow_nested_items_to_be_public = false
  tags                            = local.tags
}

resource "azurerm_storage_account_static_website" "site" {
  storage_account_id = azurerm_storage_account.site.id
  index_document     = "index.html"
  error_404_document = "404.html"
}

resource "azurerm_role_assignment" "app_blob_writer" {
  scope                = azurerm_storage_account.site.id
  role_definition_name = "Storage Blob Data Contributor"
  principal_id         = azurerm_user_assigned_identity.app.principal_id
}

# --------------------------------------------------------------------------- Container App (API + Dashboard)

resource "azurerm_container_app_environment" "main" {
  name                       = "cae-${local.name}"
  location                   = azurerm_resource_group.main.location
  resource_group_name        = azurerm_resource_group.main.name
  log_analytics_workspace_id = azurerm_log_analytics_workspace.main.id
  tags                       = local.tags
}

resource "azurerm_container_app" "app" {
  name                         = local.app_name
  container_app_environment_id = azurerm_container_app_environment.main.id
  resource_group_name          = azurerm_resource_group.main.name
  revision_mode                = "Single"
  tags                         = local.tags

  identity {
    type         = "UserAssigned"
    identity_ids = [azurerm_user_assigned_identity.app.id]
  }

  registry {
    server   = azurerm_container_registry.main.login_server
    identity = azurerm_user_assigned_identity.app.id
  }

  ingress {
    external_enabled = true
    target_port      = 8000

    traffic_weight {
      percentage      = 100
      latest_revision = true
    }
  }

  template {
    # Genau eine Replica: Hintergrund-Jobs laufen im Prozess (ThreadPool). Für mehrere Replicas bräuchte es
    # eine Job-Queue (z. B. Azure Service Bus) – die Daten selbst liegen bereits in PostgreSQL.
    min_replicas = 1
    max_replicas = 1

    container {
      name   = "contentforge"
      image  = var.container_image
      cpu    = 0.5
      memory = "1Gi"

      env {
        name  = "LLM_PROVIDER"
        value = var.llm_provider
      }
      env {
        name  = "LLM_MODEL"
        value = var.llm_model
      }
      env {
        name  = "LLM_JUDGE_MODEL"
        value = var.llm_judge_model
      }
      env {
        name  = "DAILY_BUDGET_USD"
        value = tostring(var.daily_budget_usd)
      }
      env {
        name  = "PUBLISHER"
        value = "azure_blob"
      }
      env {
        name  = "AZURE_STORAGE_ACCOUNT_URL"
        value = trimsuffix(azurerm_storage_account.site.primary_blob_endpoint, "/")
      }
      env {
        name  = "SITE_BASE_URL"
        value = trimsuffix(azurerm_storage_account.site.primary_web_endpoint, "/")
      }
      env {
        # Die App liest Claude-Key, App-Key und Datenbank-URL beim Start selbst aus dem Key Vault (app/config.py).
        # Container Apps "Express" erlaubt keine Key-Vault-Referenzen – so bleibt trotzdem kein Secret in der App-Konfiguration.
        name  = "AZURE_KEY_VAULT_URL"
        value = azurerm_key_vault.main.vault_uri
      }
      env {
        # DefaultAzureCredential wählt damit die User-Assigned Managed Identity
        name  = "AZURE_CLIENT_ID"
        value = azurerm_user_assigned_identity.app.client_id
      }
      env {
        name  = "DASHBOARD_BASE_URL"
        value = "https://${local.app_name}.${azurerm_container_app_environment.main.default_domain}"
      }
      dynamic "env" {
        for_each = var.n8n_webhook_url == "" ? [] : [var.n8n_webhook_url]
        content {
          name  = "N8N_WEBHOOK_URL"
          value = env.value
        }
      }

      liveness_probe {
        transport = "HTTP"
        port      = 8000
        path      = "/api/health"
      }
    }
  }

  lifecycle {
    # Das Image-Tag setzt die CI/CD-Pipeline (az containerapp update), nicht Terraform.
    ignore_changes = [template[0].container[0].image]
  }

  depends_on = [
    time_sleep.rbac_propagation,
    azurerm_key_vault_secret.anthropic_api_key,
    azurerm_key_vault_secret.app_api_key,
    azurerm_key_vault_secret.database_url,
    azurerm_postgresql_flexible_server_database.app,
    azurerm_postgresql_flexible_server_firewall_rule.azure_services,
  ]
}

# --------------------------------------------------------------------------- CI/CD-Rechte (GitHub Actions via OIDC)

# GitHub Actions meldet sich ohne Passwort an: GitHub stellt pro Workflow-Lauf ein signiertes OIDC-Token aus,
# Azure vertraut diesem Token über die Federated Credential – aber nur für genau dieses Repo + Environment "dev".
resource "azurerm_user_assigned_identity" "github" {
  count               = var.github_repo == "" ? 0 : 1
  name                = "id-${local.name}-github"
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name
  tags                = local.tags
}

resource "azurerm_federated_identity_credential" "github" {
  count                     = var.github_repo == "" ? 0 : 1
  name                      = "github-${var.environment}"
  user_assigned_identity_id = azurerm_user_assigned_identity.github[0].id
  audience                  = ["api://AzureADTokenExchange"]
  issuer                    = "https://token.actions.githubusercontent.com"
  subject                   = "repo:${var.github_repo}:environment:${var.environment}"
}

# Minimale Rechte: Image in der Registry bauen (ACR Tasks) und die Container App aktualisieren – sonst nichts.
resource "azurerm_role_assignment" "ci_acr" {
  count                = var.github_repo == "" ? 0 : 1
  scope                = azurerm_container_registry.main.id
  role_definition_name = "Contributor" # AcrPush reicht für "az acr build" nicht (braucht scheduleRun)
  principal_id         = azurerm_user_assigned_identity.github[0].principal_id
}

resource "azurerm_role_assignment" "ci_app" {
  count                = var.github_repo == "" ? 0 : 1
  scope                = azurerm_container_app.app.id
  role_definition_name = "Contributor"
  principal_id         = azurerm_user_assigned_identity.github[0].principal_id
}

resource "azurerm_role_assignment" "ci_rg_reader" {
  count                = var.github_repo == "" ? 0 : 1
  scope                = azurerm_resource_group.main.id
  role_definition_name = "Reader"
  principal_id         = azurerm_user_assigned_identity.github[0].principal_id
}
