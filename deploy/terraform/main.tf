resource "openstack_compute_keypair_v2" "deployer" {
  name       = "electoraldrift-deployer"
  public_key = file(pathexpand(var.ssh_public_key_path))
}

# Firewall: the project's security-group quota is used up, so the VM uses the
# existing "default" group and the real filtering is done on the VM by ufw
# (see cloud-init.yaml.tftpl): HTTP/HTTPS open to everyone, SSH only from admin_cidr.
resource "openstack_compute_instance_v2" "app" {
  name            = "electoraldrift-app"
  image_name      = var.image
  flavor_name     = var.flavor
  key_pair        = openstack_compute_keypair_v2.deployer.name
  security_groups = ["default"]

  network {
    name = "Ext-Net" # OVHcloud public network: gives the VM a public IPv4
  }

  user_data = templatefile("${path.module}/cloud-init.yaml.tftpl", {
    repo_url    = var.repo_url
    repo_branch = var.repo_branch
    admin_cidr  = var.admin_cidr
    domain      = var.domain
  })

  lifecycle {
    # OVHcloud refreshes base images regularly; don't recreate the VM when that happens.
    ignore_changes = [image_name, user_data]
  }
}
