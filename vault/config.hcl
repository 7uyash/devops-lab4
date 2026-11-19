storage "file" {
  path = "/vault/file"
}

listener "tcp" {
  address     = "0.0.0.0:8200"
  tls_disable = true   # lab network only - production listeners use TLS certificates
}

api_addr      = "http://vault:8200"
disable_mlock = true   # containers without IPC_LOCK; production hosts keep mlock on
ui            = true
