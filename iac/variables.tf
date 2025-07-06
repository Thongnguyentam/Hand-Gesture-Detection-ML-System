variable "project_id" {
    description = "The ID of the project to create the cluster in"
    default = "fsds-461704"
}

variable "region" {
  description = "The region the cluster in"
  default     = "us-central1"
}

variable "zone" {
  description = "Zone for the compute engine instance"
  default     = "us-central1-a"
  
}

variable "machine_type" {
  description = "The machine type to use for the cluster"
  default     = "e2-standard-2"
}

variable "boot_disk_image" {
  description = "Boot disk image for the compute engine instance"
  default     = "ubuntu-os-cloud/ubuntu-2204-lts"
}

variable "boot_disk_size" {
  description = "Boot disk size for the compute engine instance in GB"
  default     = 100
}

variable "firewall_name" {
  description = "Name of the firewall rule"
  default     = "jenkins-asl-firewall"
}

variable "jenkins_instance_name" {
  description = "Name of the jenkins instance"
  default     = "jenkins-asl"
}

variable "ssh_key"{
  description = "value of the ssh key to access the instance"
  type = string
}