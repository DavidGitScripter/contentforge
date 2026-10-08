output "resource_group" {
  value = azurerm_resource_group.main.name
}

output "acr_name" {
  value = azurerm_container_registry.main.name
}

output "acr_login_server" {
  value = azurerm_container_registry.main.login_server
}

output "container_app_name" {
  value = azurerm_container_app.app.name
}

output "dashboard_url" {
  value = "https://${azurerm_container_app.app.ingress[0].fqdn}"
}

output "site_url" {
  description = "Öffentliche URL der veröffentlichten SEO-Seiten"
  value       = azurerm_storage_account.site.primary_web_endpoint
}

output "postgres_server" {
  value = azurerm_postgresql_flexible_server.main.name
}

# Werte für GitHub (Settings -> Secrets and variables -> Actions). Keine Geheimnisse: OIDC braucht kein Passwort.
output "github_secrets" {
  value = var.github_repo == "" ? null : {
    AZURE_CLIENT_ID       = azurerm_user_assigned_identity.github[0].client_id
    AZURE_TENANT_ID       = data.azurerm_client_config.current.tenant_id
    AZURE_SUBSCRIPTION_ID = data.azurerm_client_config.current.subscription_id
  }
}

output "github_variables" {
  value = {
    ACR_NAME       = azurerm_container_registry.main.name
    RESOURCE_GROUP = azurerm_resource_group.main.name
    CONTAINER_APP  = azurerm_container_app.app.name
  }
}
