terraform {
  required_version = ">= 1.5"
  required_providers {
    openstack = {
      source  = "terraform-provider-openstack/openstack"
      version = "~> 3.0"
    }
  }
}

# Credentials come from the OpenRC file you download from the OVHcloud Control Panel
# (Public Cloud > Users & Roles > user > Download OpenStack RC file).
# Run `source openrc.sh` (Linux/WSL/Git Bash) before terraform commands.
provider "openstack" {
  auth_url = "https://auth.cloud.ovh.net/v3/"
  region   = var.region
}
