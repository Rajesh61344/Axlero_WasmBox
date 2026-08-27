"""Security tests for tenant-scoped host function authorization."""

from backend.integration.host_functions import HostFunctionRegistry
from backend.integration.runtime_contract import TenantPolicy


def test_unknown_host_function_is_rejected():
    registry = HostFunctionRegistry()
    policy = TenantPolicy(
        tenant_id="tenant_test",
        allowed_host_functions={"log"},
    )

    approved, diagnostics = registry.validate_requested(
        ["unknown_function"],
        policy,
    )

    assert approved == []
    assert any(d.code == "E800" for d in diagnostics)


def test_disabled_host_function_is_rejected():
    registry = HostFunctionRegistry()
    registry._functions["log"].enabled = False

    policy = TenantPolicy(
        tenant_id="tenant_test",
        allowed_host_functions={"log"},
    )

    approved, diagnostics = registry.validate_requested(
        ["log"],
        policy,
    )

    assert approved == []
    assert any(d.code == "E801" for d in diagnostics)


def test_unauthorized_host_function_is_rejected():
    registry = HostFunctionRegistry()
    policy = TenantPolicy(
        tenant_id="tenant_test",
        allowed_host_functions={"log"},
    )

    approved, diagnostics = registry.validate_requested(
        ["delete_database"],
        policy,
    )

    assert approved == []
    assert any(d.code == "E802" for d in diagnostics)


def test_authorized_host_function_is_accepted():
    registry = HostFunctionRegistry()
    policy = TenantPolicy(
        tenant_id="tenant_test",
        allowed_host_functions={"log"},
    )

    approved, diagnostics = registry.validate_requested(
        ["log"],
        policy,
    )

    assert approved == ["log"]
    assert not any(d.code in {"E800", "E801", "E802"} for d in diagnostics)
