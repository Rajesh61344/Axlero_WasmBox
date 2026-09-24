"""Security tests for tenant-scoped host function authorization."""

from backend.integration.host_functions import HostFunctionRegistry
from backend.integration.runtime_adapter import WasmtimeAdapter
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
    assert not any(
        d.code in {"E800", "E801", "E802"}
        for d in diagnostics
    )


def test_default_runtime_policy_is_restrictive():
    adapter = WasmtimeAdapter()

    policy = adapter.resolve_tenant_policy(
        "tenant_test"
    )

    assert policy.tenant_id == "tenant_test"
    assert policy.allowed_host_functions == {"log"}


def test_runtime_uses_tenant_specific_policy():
    def policy_provider(
        tenant_id: str,
    ) -> TenantPolicy:
        return TenantPolicy(
            tenant_id=tenant_id,
            allowed_host_functions={
                "log",
                "get_customer_data",
            },
        )

    adapter = WasmtimeAdapter(
        policy_provider=policy_provider,
    )

    policy = adapter.resolve_tenant_policy(
        "tenant_customer"
    )

    assert policy.tenant_id == "tenant_customer"
    assert policy.allowed_host_functions == {
        "log",
        "get_customer_data",
    }


def test_runtime_rejects_policy_for_wrong_tenant():
    def policy_provider(
        tenant_id: str,
    ) -> TenantPolicy:
        return TenantPolicy(
            tenant_id="different_tenant",
            allowed_host_functions={"log"},
        )

    adapter = WasmtimeAdapter(
        policy_provider=policy_provider,
    )

    try:
        adapter.resolve_tenant_policy(
            "tenant_test"
        )
        assert False, "Expected ValueError"

    except ValueError as exc:
        assert "different tenant" in str(exc)


def test_runtime_rejects_invalid_policy_provider_result():
    def policy_provider(
        tenant_id: str,
    ):
        return {
            "tenant_id": tenant_id,
            "allowed_host_functions": {"log"},
        }

    adapter = WasmtimeAdapter(
        policy_provider=policy_provider,
    )

    try:
        adapter.resolve_tenant_policy(
            "tenant_test"
        )
        assert False, "Expected TypeError"

    except TypeError as exc:
        assert "TenantPolicy" in str(exc)