variable "project" {
  description = "Projektname, Präfix für alle Ressourcen"
  type        = string
  default     = "contentforge"
}

variable "environment" {
  description = "Umgebung (dev, test, prod)"
  type        = string
  default     = "dev"

  validation {
    condition     = can(regex("^[a-z]{2,4}$", var.environment))
    error_message = "environment: 2–4 Kleinbuchstaben (Namenslimits von Storage Account und Key Vault)."
  }
}

variable "location" {
  # Produktiv wäre germanywestcentral naheliegend. "Azure for Students" erlaubt per Policy nur wenige Regionen
  # (u. a. francecentral) – Daten bleiben damit trotzdem in der EU.
  description = "Azure-Region"
  type        = string
  default     = "francecentral"
}

variable "container_image" {
  description = "Initiales Image aus der ACR (z. B. acrxyz.azurecr.io/contentforge:v1). Updates danach per CI/CD."
  type        = string
}

variable "anthropic_api_key" {
  description = "Claude API Key – landet im Key Vault, nie im Container-Image"
  type        = string
  sensitive   = true
}

variable "app_api_key" {
  description = "Schlüssel für schreibende API-Endpunkte (Header X-API-Key), auch von n8n genutzt"
  type        = string
  sensitive   = true
}

variable "llm_provider" {
  description = "anthropic = echte Claude-Aufrufe, mock = kostenlose Demo ohne API-Key-Verbrauch"
  type        = string
  default     = "anthropic"

  validation {
    condition     = contains(["anthropic", "mock"], var.llm_provider)
    error_message = "llm_provider: anthropic oder mock."
  }
}

variable "llm_model" {
  type    = string
  default = "claude-opus-5"
}

variable "llm_judge_model" {
  type    = string
  default = "claude-opus-5"
}

variable "daily_budget_usd" {
  description = "Kostenbremse: neue Runs werden blockiert, sobald die Tageskosten diesen Wert erreichen"
  type        = number
  default     = 5
}

variable "n8n_webhook_url" {
  description = "Optional: n8n-Webhook für Freigabe-Benachrichtigungen"
  type        = string
  default     = ""
}

variable "github_repo" {
  description = "Optional: GitHub-Repository im Format <user>/<repo>. Legt die Identität für GitHub Actions (OIDC) an."
  type        = string
  default     = ""

  validation {
    condition     = var.github_repo == "" || can(regex("^[A-Za-z0-9-]+/[A-Za-z0-9._-]+$", var.github_repo))
    error_message = "github_repo: Format <user>/<repo>, z. B. davidseibert/contentforge."
  }
}
