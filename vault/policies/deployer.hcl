# Policy of the CI/CD pipeline: it may only hand out a single-use, wrapped secret_id for the app role.
# The pipeline itself can never read application secrets or database credentials.
path "auth/approle/role/shoplite-app/role-id" {
  capabilities = ["read"]
}
path "auth/approle/role/shoplite-app/secret-id" {
  capabilities = ["update"]
  min_wrapping_ttl = "30s"
  max_wrapping_ttl = "5m"
}
