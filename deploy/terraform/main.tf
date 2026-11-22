resource "openstack_compute_keypair_v2" "deployer" {
  name       = "electoraldrift-deployer"
  public_key = file(pathexpand(var.ssh_public_key_path))
}

# Firewall: HTTP/HTTPS open to everyone, SSH only from your IP.
resource "openstack_networking_secgroup_v2" "web" {
  name        = "electoraldrift-web"
  description = "ElectoralDrift US web VM"
}

resource "openstack_networking_secgroup_rule_v2" "http" {
  security_group_id = openstack_networking_secgroup_v2.web.id
  direction         = "ingress"
  ethertype         = "IPv4"
  protocol          = "tcp"
  port_range_min    = 80
  port_range_max    = 80
  remote_ip_prefix  = "0.0.0.0/0"
}

resource "openstack_networking_secgroup_rule_v2" "https" {
  security_group_id = openstack_networking_secgroup_v2.web.id
  direction         = "ingress"
  ethertype         = "IPv4"
  protocol          = "tcp"
  port_range_min    = 443
  port_range_max    = 443
  remote_ip_prefix  = "0.0.0.0/0"
}

resource "openstack_networking_secgroup_rule_v2" "ssh" {
  security_group_id = openstack_networking_secgroup_v2.web.id
  direction         = "ingress"
  ethertype         = "IPv4"
  protocol          = "tcp"
  port_range_min    = 22
  port_range_max    = 22
  remote_ip_prefix  = var.admin_cidr
}

resource "openstack_compute_instance_v2" "app" {
  name            = "electoraldrift-app"
  image_name      = var.image
  flavor_name     = var.flavor
  key_pair        = openstack_compute_keypair_v2.deployer.name
  security_groups = [openstack_networking_secgroup_v2.web.name]

  network {
    name = "Ext-Net" # OVHcloud public network: gives the VM a public IPv4
  }

  user_data = templatefile("${path.module}/cloud-init.yaml.tftpl", {
    repo_url    = var.repo_url
    repo_branch = var.repo_branch
  })

  lifecycle {
    # OVHcloud refreshes base images regularly; don't recreate the VM when that happens.
    ignore_changes = [image_name, user_data]
  }
}
