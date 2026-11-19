# Operator policy used after setup (the root token is revoked): manage leases and seal Vault in an emergency.
path "sys/leases/lookup/*" {
  capabilities = ["list", "sudo"]
}
path "sys/leases/revoke-prefix/*" {
  capabilities = ["update", "sudo"]
}
path "sys/seal" {
  capabilities = ["update", "sudo"]
}
