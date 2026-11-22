variable "region" {
  description = "OVHcloud Public Cloud region (WAW1 = Warsaw, GRA11 = Gravelines, ...)"
  type        = string
  default     = "WAW1"
}

variable "flavor" {
  description = "Instance size. b3-8 = 2 vCPU / 8 GB, enough for now and for Postgres later."
  type        = string
  default     = "b3-8"
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
