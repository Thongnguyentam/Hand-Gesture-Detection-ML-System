terraform {
  required_providers {
    google = {
      source = "hashicorp/google"
      version = "~> 4.0"
    }
  }
  required_version = ">= 1.0.0"
}

provider "google" {
  project = var.project_id
  region = var.region
}

resource "google_container_cluster" "asl-cluster" {
  name = "asl-cluster"
  location = var.region

  # We are using a GKE Standard cluster to have full control,
  # which is necessary for running privileged containers for Elasticsearch.
  enable_autopilot = false

  # In Standard mode, we must define the node pool configuration.
  node_config {
    machine_type = var.machine_type
    disk_size_gb = 200
    disk_type = "pd-standard"
  }

  # This is for the default node pool. For more complex setups,
  # you would define separate `google_container_node_pool` resources.
  initial_node_count = 1
}

resource "google_compute_instance" "asl-jenkins" {
  name         = var.jenkins_instance_name
  machine_type = var.machine_type
  zone         = var.zone
  boot_disk {
    initialize_params {
      image = var.boot_disk_image
      size = var.boot_disk_size
    }
  }
  network_interface {   
    network = "default"
    access_config {
      // Ephemeral IP
    }
  }
  metadata = {
        ssh-keys = var.ssh_key,
        startup-script = file("jenkins_startup.sh")
  }
  tags = ["jenkins"]
}

// firewall for jenkins
resource "google_compute_firewall" "jenkins-firewall" {
  name = var.firewall_name
  network = "default"
  allow {
    protocol = "tcp"
    ports = [
      "22",   // SSH
      "80",   // HTTP
      "443",  // HTTPS
      "8080", // Jenkins web interface and GitHub webhooks
      "50000" // Jenkins agents
    ]
  }
  source_ranges = ["0.0.0.0/0"] // allow all traffic
  target_tags = ["jenkins"]
}