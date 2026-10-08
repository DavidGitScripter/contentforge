terraform {
  required_version = ">= 1.6"

  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 4.0"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.6"
    }
    time = {
      source  = "hashicorp/time"
      version = "~> 0.12"
    }
  }

  # Für Teamarbeit Remote State nutzen, z. B.:
  # backend "azurerm" {
  #   resource_group_name  = "rg-tfstate"
  #   storage_account_name = "sttfstate<suffix>"
  #   container_name       = "tfstate"
  #   key                  = "contentforge.tfstate"
  # }
}

# Subscription kommt aus ARM_SUBSCRIPTION_ID (lokal: az login + export ARM_SUBSCRIPTION_ID=...)
provider "azurerm" {
  features {
    key_vault {
      purge_soft_delete_on_destroy = false
    }
  }
}
