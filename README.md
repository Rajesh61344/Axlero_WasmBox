## Security and Sandbox Controls

WasmBox implements a deny-by-default security model for executing untrusted WebAssembly plugins. Security controls are enforced across compilation, validation, runtime execution, and host-function authorization.

### Host Function Authorization

Plugins cannot automatically access host capabilities. A plugin may request specific host functions, but a request does not grant permission.

Each requested host function is validated against:

- Whether the function is registered.
- Whether the function is currently enabled.
- Whether the tenant policy explicitly allows the function.
- Whether the requested function passes the runtime security checks.

Unauthorized, unknown, or disabled host functions are rejected before execution.

### Tenant-Scoped Security Policies

Host-function permissions are evaluated using a tenant-specific `TenantPolicy`.

The runtime supports an injectable policy provider that can resolve permissions for individual tenants:

```text
Plugin
  |
  | requested host functions
  v
Tenant Policy Provider
  |
  | TenantPolicy
  v
Host Function Registry
  |
  | authorization validation
  v
Wasm Runtime