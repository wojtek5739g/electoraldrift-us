locals {
  site_address = var.domain != "" ? var.domain : "${replace(openstack_compute_instance_v2.app.access_ip_v4, ".", "-")}.sslip.io"
}

output "public_ip" {
  value = openstack_compute_instance_v2.app.access_ip_v4
}

output "url" {
  value = "https://${local.site_address}"
}

output "ssh" {
  value = "ssh ubuntu@${openstack_compute_instance_v2.app.access_ip_v4}"
}
