# Runtime policy of the ShopLite application: read its own config and request database credentials. Nothing else.
path "secret/data/shoplite/config" {
  capabilities = ["read"]
}
path "database/creds/shoplite-app" {
  capabilities = ["read"]
}
