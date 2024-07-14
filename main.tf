terraform {
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "5.30.0"
    }
  }
}

provider "google" {
  project = var.project
  region  = var.region
  zone    = var.zone
}

data "google_project" "project" {}

##############
# APIs
##############

resource "google_project_service" "cloudrun" {
  project            = var.project
  service            = "run.googleapis.com"
  disable_on_destroy = false
}

resource "google_project_service" "compute" {
  project            = var.project
  service            = "compute.googleapis.com"
  disable_on_destroy = false
}

resource "google_project_service" "cloudbuild" {
  project            = var.project
  service            = "cloudbuild.googleapis.com"
  disable_on_destroy = false
}

resource "google_project_service" "containerregistry" {
  project            = var.project
  service            = "containerregistry.googleapis.com"
  disable_on_destroy = false
}

resource "google_project_service" "cloudresourcemanager" {
  project            = var.project
  service            = "cloudresourcemanager.googleapis.com"
  disable_on_destroy = false
}

resource "google_project_service" "dataproc" {
  project            = var.project
  service            = "dataproc.googleapis.com"
  disable_on_destroy = false
}

resource "google_project_service" "cloudscheduler" {
  project            = var.project
  service            = "cloudscheduler.googleapis.com"
  disable_on_destroy = false
}

resource "google_project_service" "bigquery" {
  project            = var.project
  service            = "bigquery.googleapis.com"
  disable_on_destroy = false
}


resource "google_project_service" "alloydb" {
  project            = var.project
  service            = "alloydb.googleapis.com"
  disable_on_destroy = false
}

resource "google_project_service" "servicenetworking" {
  project            = var.project
  service            = "servicenetworking.googleapis.com"
  disable_on_destroy = false
}

##############
# Service Accounts & permissions
##############

## Dataproc & Cloud Scheduler service account

resource "google_service_account" "scheduler_service_account" {
  account_id   = "scheduler-service-account"
  display_name = "Scheduler Service Account"
}

resource "google_project_iam_custom_role" "dataproc_runner_role" {
  role_id = "dataprocWorkflowTemplateInstantiator"
  title   = "Dataproc Workflow Template Instantiator"
  permissions = [
    "dataproc.workflowTemplates.instantiate",
    "iam.serviceAccounts.actAs"
  ]
  project = var.project
}

resource "google_project_iam_member" "dataproc_scheduler" {
  project = var.project
  role    = google_project_iam_custom_role.dataproc_runner_role.name
  member  = "serviceAccount:${google_service_account.scheduler_service_account.email}"
}

resource "google_project_iam_custom_role" "dataproc_default_account_role" {
  role_id = "dataprocDefaultAccountRole"
  title   = "Dataproc Default Account Role"
  permissions = [
    "storage.buckets.get",
    "storage.objects.create",
    "storage.objects.delete",
    "storage.objects.get",
    "storage.objects.list",
    "storage.objects.update"
  ]
  project = var.project
}

resource "google_project_iam_member" "dataproc_default_account_object_admin" {
  project = var.project
  role    = google_project_iam_custom_role.dataproc_default_account_role.name
  member  = "serviceAccount:${data.google_project.project.number}-compute@developer.gserviceaccount.com"
}

##############
# Buckets
##############

resource "google_storage_bucket" "meteoetl_bucket" {
  name                        = "meteoetl-bucket"
  location                    = var.location
  storage_class               = "STANDARD"
  uniform_bucket_level_access = true
  force_destroy               = true
}

resource "google_storage_bucket_object" "update_gefs_script" {
  name   = "update_gefs.py"
  bucket = google_storage_bucket.meteoetl_bucket.name
  source = "scripts/python/update_gefs.py"
}

##############
# BigQuery
##############

resource "google_bigquery_dataset" "meteo_dataset" {
  dataset_id = "meteo_dataset"
  location   = var.location
}

resource "google_bigquery_table" "gefs" {
  dataset_id          = google_bigquery_dataset.meteo_dataset.dataset_id
  table_id            = "gefs"
  deletion_protection = false
  schema              = <<EOF
[
  {
    "name": "time",
    "type": "TIMESTAMP",
    "mode": "NULLABLE"
  },
  {
    "name": "valid_time",
    "type": "TIMESTAMP",
    "mode": "NULLABLE"
  },
  {
    "name": "latitude",
    "type": "FLOAT",
    "mode": "NULLABLE"
  },
  {
    "name": "longitude",
    "type": "FLOAT",
    "mode": "NULLABLE"
  },
  {
    "name": "number",
    "type": "INT64",
    "mode": "NULLABLE"
  },
  {
    "name": "u10",
    "type": "FLOAT",
    "mode": "NULLABLE"
  },
  {
    "name": "v10",
    "type": "FLOAT",
    "mode": "NULLABLE"
  },
  {
    "name": "tp",
    "type": "FLOAT",
    "mode": "NULLABLE"
  },
  {
    "name": "tcc",
    "type": "FLOAT",
    "mode": "NULLABLE"
  },
  {
    "name": "t2m",
    "type": "FLOAT",
    "mode": "NULLABLE"
  },
  {
    "name": "prmsl",
    "type": "FLOAT",
    "mode": "NULLABLE"
  }
]
EOF

  time_partitioning {
    type  = "DAY"
    field = "time"
  }
}

##############
# Dataproc
##############

resource "google_dataproc_workflow_template" "meteoetl_template" {
  name     = "meteoetl-template"
  location = var.region
  placement {
    managed_cluster {
      cluster_name = "meteoetl-cluster"
      config {
        gce_cluster_config {
          internal_ip_only = false
          zone             = var.zone
        }
        master_config {
          num_instances = 1
          machine_type  = "n1-standard-2"
          disk_config {
            boot_disk_size_gb = 30
          }
        }
        worker_config {
          num_instances = 2
          machine_type  = "n1-standard-2"
          disk_config {
            boot_disk_size_gb = 30
          }
        }
        software_config {
          image_version = "2.2.16-debian12"
          properties = {
            "dataproc:pip.packages"   = "pandas-gbq==0.23.0"
            "dataproc:conda.packages" = "cfgrib==0.9.11.0"
          }
        }
      }
    }
  }
  jobs {
    step_id = "update-gefs-job"
    pyspark_job {
      main_python_file_uri = "gs://${google_storage_bucket.meteoetl_bucket.name}/${google_storage_bucket_object.update_gefs_script.name}"
    }
  }
}

##############
# Cloud Scheduler
##############

resource "google_cloud_scheduler_job" "meteoetl_job_am" {
  name        = "meteoetl-job-am"
  description = "Triggers the Dataproc Meteo ETL workflow template every day at 8 AM"
  schedule    = "0 8 * * *"
  time_zone   = "UTC"

  http_target {
    http_method = "POST"
    uri         = "https://dataproc.googleapis.com/v1/projects/${var.project}/regions/${var.region}/workflowTemplates/${google_dataproc_workflow_template.meteoetl_template.name}:instantiate?alt=json"
    oauth_token {
      service_account_email = google_service_account.scheduler_service_account.email
    }
  }
}

resource "google_cloud_scheduler_job" "meteoetl_job_pm" {
  name        = "meteoetl-job-pm"
  description = "Triggers the Dataproc Meteo ETL workflow template every day at 20 PM"
  schedule    = "0 20 * * *"
  time_zone   = "UTC"

  http_target {
    http_method = "POST"
    uri         = "https://dataproc.googleapis.com/v1/projects/${var.project}/regions/${var.region}/workflowTemplates/${google_dataproc_workflow_template.meteoetl_template.name}:instantiate?alt=json"
    oauth_token {
      service_account_email = google_service_account.scheduler_service_account.email
    }
  }
}

##############
# AlloyDB
##############

resource "google_compute_network" "default" {
  name = "alloydb-network"
}

resource "google_compute_global_address" "private_ip_alloc" {
  name          = "alloydb-cluster"
  address_type  = "INTERNAL"
  purpose       = "VPC_PEERING"
  prefix_length = 16
  network       = google_compute_network.default.id
}

resource "google_service_networking_connection" "vpc_connection" {
  network                 = google_compute_network.default.id
  service                 = "servicenetworking.googleapis.com"
  reserved_peering_ranges = [google_compute_global_address.private_ip_alloc.name]
}

resource "google_alloydb_cluster" "default" {
  cluster_id = "alloydb-cluster"
  location   = var.region
  network_config {
    network = google_compute_network.default.id
  }

  initial_user {
    user     = "alloydb_user"
    password = "alloydb_password"
  }

  automated_backup_policy {
    enabled = false
  }

  continuous_backup_config {
    enabled = false
  }
}

resource "google_alloydb_instance" "default" {
  cluster       = google_alloydb_cluster.default.name
  instance_id   = "alloydb-instance"
  instance_type = "PRIMARY"

  machine_config {
    cpu_count = 2
  }

  depends_on = [google_service_networking_connection.vpc_connection]
}

##############
# CloudRun - streamlit
##############

resource "null_resource" "build_streamlit_app_docker_image" {
  provisioner "local-exec" {
    command = "cd app && gcloud builds submit --region=${var.region} --tag gcr.io/${var.project}/streamlit-app:latest"
  }
}

resource "google_cloud_run_v2_service" "streamlit_app" {
  name     = "streamlit-app"
  project  = var.project
  location = var.region
  ingress  = "INGRESS_TRAFFIC_ALL"

  template {
    containers {
      image   = "gcr.io/${var.project}/streamlit-app:latest"
      command = ["python"]
      args    = ["-m", "streamlit", "run", "app.py", "--server.port", "8080"]
    }
  }
  depends_on = [ null_resource.build_streamlit_app_docker_image ]
}

data "google_iam_policy" "noauth" {
  binding {
    role    = "roles/run.invoker"
    members = ["allUsers"]
  }
}

resource "google_cloud_run_service_iam_policy" "noauth_streamlit" {
  location    = var.region
  project     = var.project
  service     = google_cloud_run_v2_service.streamlit_app.name
  policy_data = data.google_iam_policy.noauth.policy_data
}

##############
# CloudRun - api
##############

resource "null_resource" "build_api_docker_image" {
  provisioner "local-exec" {
    command = "cd api && gcloud builds submit --region=${var.region} --tag gcr.io/${var.project}/api:latest"
  }
}

resource "google_cloud_run_v2_service" "api" {
  name     = "api"
  project  = var.project
  location = var.region
  ingress  = "INGRESS_TRAFFIC_ALL"

  template {
    containers {
      image   = "gcr.io/${var.project}/api:latest"
      command = ["python"]
      args    = ["-m", "flask", "--app", "api", "run", "--host=0.0.0.0", "--port=8080"]
    }
    vpc_access {
      network_interfaces {
        network = google_compute_network.default.name
      }
      egress = "PRIVATE_RANGES_ONLY"
    }
  }
  depends_on = [null_resource.build_api_docker_image]
}

resource "google_cloud_run_service_iam_policy" "noauth_api" {
  location    = var.region
  project     = var.project
  service     = google_cloud_run_v2_service.api.name
  policy_data = data.google_iam_policy.noauth.policy_data
}
