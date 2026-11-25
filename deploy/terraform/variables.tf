variable "region" {
  description = "OVHcloud Public Cloud region (WAW1 = Warsaw, GRA11 = Gravelines, ...)"
  type        = string
  default     = "WAW1"
}

variable "flavor" {
  description = "Instance size. d2-4 (4 GB) is enough for the map; d2-8 (8 GB) when Postgres/Redpanda/Spark are added. OVHcloud only resizes upward; going smaller needs -replace."
  type        = string
  default     = "d2-4"
}

variable "image" {
  description = "OS image name as listed in the OVHcloud catalog"
  type        = string
  default     = "Ubuntu 24.04"
}

variable "ssh_public_key_path" {
  description = "Path to your public SSH key"
  type        = string
  default     = "~/.ssh/id_ed25519.pub"
}

variable "admin_cidr" {
  description = "Your IP in CIDR form allowed to SSH (e.g. 89.64.1.2/32). Find it at https://ifconfig.me"
  type        = string
}

variable "repo_url" {
  description = "Git repository cloned onto the VM"
  type        = string
  default     = "https://github.com/wojtek5739g/electoraldrift-us.git"
}

variable "repo_branch" {
  description = "Branch to deploy"
  type        = string
  default     = "main"
}

variable "domain" {
  description = "Domain for HTTPS (an A record must point to the VM). Empty = use <ip-with-dashes>.sslip.io"
  type        = string
  default     = ""
}
