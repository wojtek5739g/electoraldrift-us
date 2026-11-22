output "public_ip" {
  value = openstack_compute_instance_v2.app.access_ip_v4
}

output "url" {
  value = "http://${openstack_compute_instance_v2.app.access_ip_v4}"
}

output "ssh" {
  value = "ssh ubuntu@${openstack_compute_instance_v2.app.access_ip_v4}"
}
