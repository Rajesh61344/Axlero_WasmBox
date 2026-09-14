"""
WasmBox Host Function Declaration System.

Provides infrastructure for declaring, registering, validating, and
executing host functions that plugins can call through the host bridge.

Security model:
    - Host functions are explicitly registered.
    - Plugins can request only registered functions.
    - Tenant policy controls which functions are permitted.
    - Disabled functions cannot be used.
    - Dangerous functions require explicit permissions.
    - Host function callbacks are never exposed directly to untrusted code.
"""

from __future__ import annotations

import functools
import inspect
import logging
from dataclasses import dataclass
from typing import Any, Callable

from backend.compiler.errors import (
    CompilerStage,
    Diagnostic,
    ErrorSeverity,
)
from backend.integration.runtime_contract import (
    HostFunctionSpec,
    TenantPolicy,
)

logger = logging.getLogger("wasmbox.host_functions")


# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------

HostCallback = Callable[..., Any]


@dataclass
class RegisteredHostFunction:
    """A registered host function.

    Contains the public specification and optional trusted implementation
    callback. The callback is executed only by trusted runtime code after
    authorization has succeeded.
    """

    spec: HostFunctionSpec
    callback: HostCallback | None = None
    enabled: bool = True

    def to_dict(self) -> dict[str, Any]:
        """Return a serializable representation."""
        return {
            **self.spec.to_dict(),
            "enabled": self.enabled,
            "has_callback": self.callback is not None,
        }


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

class HostFunctionRegistry:
    """Registry for host functions available to sandboxed plugins.

    The registry is intentionally explicit and deny-by-default.

    A plugin cannot:
        - dynamically discover host functions,
        - invoke an unregistered host function,
        - invoke a disabled host function,
        - bypass tenant authorization.
    """

    def __init__(self) -> None:
        self._functions: dict[str, RegisteredHostFunction] = {}
        self._register_defaults()

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def _register_defaults(self) -> None:
        """Register the built-in host function specifications."""

        # --------------------------------------------------------------
        # Logging
        # --------------------------------------------------------------
        self.register(
            HostFunctionSpec(
                name="log",
                permissions=["logging"],
                description="Write a log message from the plugin.",
                param_types=["string"],
                return_type="none",
            )
        )

        # --------------------------------------------------------------
        # Input / output
        # --------------------------------------------------------------
        self.register(
            HostFunctionSpec(
                name="get_input",
                permissions=["io:read"],
                description="Get the input data passed to the plugin.",
                param_types=[],
                return_type="any",
            )
        )

        self.register(
            HostFunctionSpec(
                name="set_output",
                permissions=["io:write"],
                description="Set output data from the plugin.",
                param_types=["any"],
                return_type="none",
            )
        )

        # --------------------------------------------------------------
        # Key-value store
        # --------------------------------------------------------------
        self.register(
            HostFunctionSpec(
                name="kv_get",
                permissions=["kv:read"],
                description="Read a value from the tenant key-value store.",
                param_types=["string"],
                return_type="any",
            )
        )

        self.register(
            HostFunctionSpec(
                name="kv_set",
                permissions=["kv:write"],
                description="Write a value to the tenant key-value store.",
                param_types=["string", "any"],
                return_type="none",
            )
        )

        # --------------------------------------------------------------
        # HTTP
        #
        # HTTP remains explicitly permission-gated.
        # --------------------------------------------------------------
        self.register(
            HostFunctionSpec(
                name="http_get",
                permissions=["http:read"],
                description="Make an HTTP GET request through the host proxy.",
                param_types=["string"],
                return_type="dict",
            )
        )

        # --------------------------------------------------------------
        # Dangerous administrative operation.
        #
        # This is intentionally registered only as a specification.
        # There is NO default destructive callback.
        # --------------------------------------------------------------
        self.register(
            HostFunctionSpec(
                name="delete_database",
                permissions=["system:admin"],
                description=(
                    "Administrative database deletion operation. "
                    "Requires explicit system:admin authorization."
                ),
                param_types=["string"],
                return_type="none",
            )
        )

    def register(
        self,
        spec: HostFunctionSpec,
        callback: HostCallback | None = None,
    ) -> None:
        """Register a host function.

        Args:
            spec:
                Public host function specification.
            callback:
                Trusted implementation callback.

        Raises:
            ValueError:
                If the function name is empty or invalid.
        """

        if not isinstance(spec.name, str) or not spec.name.strip():
            raise ValueError("Host function name must be a non-empty string.")

        name = spec.name.strip()

        if name != spec.name:
            raise ValueError(
                "Host function name must not contain leading/trailing whitespace."
            )

        if name.startswith("_"):
            raise ValueError(
                "Host function names beginning with '_' are reserved."
            )

        if callback is not None and not callable(callback):
            raise ValueError(
                f"Callback for host function '{name}' must be callable."
            )

        self._functions[name] = RegisteredHostFunction(
            spec=spec,
            callback=callback,
            enabled=True,
        )

        logger.debug("Registered host function: %s", name)

    def unregister(self, name: str) -> bool:
        """Remove a host function from the registry.

        Returns:
            True when removed, False when the function did not exist.
        """

        if name in self._functions:
            del self._functions[name]
            logger.debug("Unregistered host function: %s", name)
            return True

        return False

    def enable(self, name: str) -> bool:
        """Enable a registered host function."""

        registered = self.get(name)

        if registered is None:
            return False

        registered.enabled = True
        logger.info("Enabled host function: %s", name)
        return True

    def disable(self, name: str) -> bool:
        """Disable a registered host function."""

        registered = self.get(name)

        if registered is None:
            return False

        registered.enabled = False
        logger.info("Disabled host function: %s", name)
        return True

    # ------------------------------------------------------------------
    # Lookup
    # ------------------------------------------------------------------

    def get(self, name: str) -> RegisteredHostFunction | None:
        """Get a registered host function by name."""

        return self._functions.get(name)

    def contains(self, name: str) -> bool:
        """Return True if a host function is registered."""

        return name in self._functions

    def list_functions(self) -> list[HostFunctionSpec]:
        """List enabled host function specifications."""

        return [
            registered.spec
            for registered in self._functions.values()
            if registered.enabled
        ]

    def list_names(self) -> list[str]:
        """List enabled host function names."""

        return [
            name
            for name, registered in self._functions.items()
            if registered.enabled
        ]

    def list_all_names(self) -> list[str]:
        """List all registered host function names, including disabled ones."""

        return list(self._functions.keys())

    # ------------------------------------------------------------------
    # Authorization
    # ------------------------------------------------------------------

    def validate_requested(
        self,
        requested: list[str],
        tenant_policy: TenantPolicy,
    ) -> tuple[list[str], list[Diagnostic]]:
        """Validate requested host functions against tenant policy.

        Validation order:

        1. Function must exist.
        2. Function must be enabled.
        3. Tenant must explicitly allow it.

        Returns:
            Tuple of approved function names and diagnostics.
        """

        approved: list[str] = []
        diagnostics: list[Diagnostic] = []

        # Remove duplicates while preserving request order.
        seen: set[str] = set()
        normalized_requested: list[str] = []

        for func_name in requested:
            if not isinstance(func_name, str):
                diagnostics.append(
                    Diagnostic(
                        code="E803",
                        severity=ErrorSeverity.ERROR,
                        stage=CompilerStage.RUNTIME,
                        message=(
                            "Host function name must be a string."
                        ),
                    )
                )
                continue

            if func_name in seen:
                continue

            seen.add(func_name)
            normalized_requested.append(func_name)

        for func_name in normalized_requested:
            registered = self.get(func_name)

            # ----------------------------------------------------------
            # Unknown function
            # ----------------------------------------------------------
            if registered is None:
                diagnostics.append(
                    Diagnostic(
                        code="E800",
                        severity=ErrorSeverity.ERROR,
                        stage=CompilerStage.RUNTIME,
                        message=f"Unknown host function: '{func_name}'",
                        suggestion=(
                            "Use only explicitly registered host functions. "
                            "Plugins cannot dynamically discover host functions."
                        ),
                    )
                )
                continue

            # ----------------------------------------------------------
            # Disabled function
            # ----------------------------------------------------------
            if not registered.enabled:
                diagnostics.append(
                    Diagnostic(
                        code="E801",
                        severity=ErrorSeverity.ERROR,
                        stage=CompilerStage.RUNTIME,
                        message=(
                            f"Host function '{func_name}' is currently disabled."
                        ),
                    )
                )
                continue

            # ----------------------------------------------------------
            # Tenant authorization
            # ----------------------------------------------------------
            if not tenant_policy.is_host_function_allowed(func_name):
                diagnostics.append(
                    Diagnostic(
                        code="E802",
                        severity=ErrorSeverity.ERROR,
                        stage=CompilerStage.RUNTIME,
                        message=(
                            f"Host function '{func_name}' is not allowed "
                            f"for tenant '{tenant_policy.tenant_id}'"
                        ),
                        suggestion=(
                            "Contact your administrator to request access "
                            "to this host function."
                        ),
                        context={
                            "function": func_name,
                            "tenant_id": tenant_policy.tenant_id,
                            "required_permissions": (
                                registered.spec.permissions
                            ),
                        },
                    )
                )
                continue

            # ----------------------------------------------------------
            # Approved
            # ----------------------------------------------------------
            approved.append(func_name)

            logger.debug(
                "Host function '%s' approved for tenant '%s'",
                func_name,
                tenant_policy.tenant_id,
            )

        # --------------------------------------------------------------
        # Approval diagnostic
        # --------------------------------------------------------------
        if approved:
            diagnostics.append(
                Diagnostic(
                    code="I800",
                    severity=ErrorSeverity.INFO,
                    stage=CompilerStage.RUNTIME,
                    message=(
                        f"Approved host functions: {', '.join(approved)}"
                    ),
                )
            )

        return approved, diagnostics

    # ------------------------------------------------------------------
    # Manifest
    # ------------------------------------------------------------------

    def get_specs_for_manifest(
        self,
        function_names: list[str],
    ) -> list[dict[str, Any]]:
        """Get serializable specifications for manifest generation."""

        specs: list[dict[str, Any]] = []

        seen: set[str] = set()

        for name in function_names:
            if name in seen:
                continue

            seen.add(name)

            registered = self.get(name)

            if registered is None:
                continue

            specs.append(registered.spec.to_dict())

        return specs

    # ------------------------------------------------------------------
    # Trusted execution
    # ------------------------------------------------------------------

    def invoke(
        self,
        name: str,
        tenant_policy: TenantPolicy,
        *args: Any,
        **kwargs: Any,
    ) -> Any:
        """Invoke an authorized host function.

        IMPORTANT:
            This method is intended for trusted runtime code only.

        The function is executed only when:

            - It exists.
            - It is enabled.
            - The tenant explicitly allows it.
            - A trusted callback is registered.

        Returns:
            Callback result.

        Raises:
            PermissionError:
                If tenant policy denies access.
            LookupError:
                If function does not exist or is disabled.
            RuntimeError:
                If no callback is registered.
        """

        registered = self.get(name)

        if registered is None:
            raise LookupError(
                f"Unknown host function: '{name}'"
            )

        if not registered.enabled:
            raise LookupError(
                f"Host function '{name}' is disabled."
            )

        if not tenant_policy.is_host_function_allowed(name):
            logger.warning(
                "Denied host function '%s' for tenant '%s'",
                name,
                tenant_policy.tenant_id,
            )

            raise PermissionError(
                f"Host function '{name}' is not allowed "
                f"for tenant '{tenant_policy.tenant_id}'"
            )

        if registered.callback is None:
            raise RuntimeError(
                f"Host function '{name}' has no registered implementation."
            )

        logger.debug(
            "Invoking host function '%s' for tenant '%s'",
            name,
            tenant_policy.tenant_id,
        )

        return registered.callback(*args, **kwargs)


# ---------------------------------------------------------------------------
# Decorator
# ---------------------------------------------------------------------------

def host_function(
    name: str,
    permissions: list[str] | None = None,
    description: str = "",
) -> Callable[[HostCallback], HostCallback]:
    """Decorator for declaring a host function.

    Example:

        @host_function(
            name="log",
            permissions=["logging"],
            description="Write a log message",
        )
        def host_log(message: str) -> None:
            print(message)

    The decorator attaches the HostFunctionSpec to the trusted callback.
    It does NOT automatically expose the callback to sandboxed plugins.
    """

    if not isinstance(name, str) or not name.strip():
        raise ValueError(
            "Host function name must be a non-empty string."
        )

    normalized_name = name.strip()

    if normalized_name.startswith("_"):
        raise ValueError(
            "Host function names beginning with '_' are reserved."
        )

    normalized_permissions = list(permissions or [])

    def decorator(func: HostCallback) -> HostCallback:
        if not callable(func):
            raise TypeError(
                "host_function decorator can only be applied to callables."
            )

        spec = HostFunctionSpec(
            name=normalized_name,
            permissions=normalized_permissions,
            description=description or inspect.getdoc(func) or "",
            param_types=_get_parameter_types(func),
            return_type=_get_return_type(func),
        )

        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            logger.debug(
                "Trusted host function '%s' called",
                normalized_name,
            )

            return func(*args, **kwargs)

        # Metadata used by the registration layer.
        wrapper._wasmbox_host_spec = spec  # type: ignore[attr-defined]
        wrapper._wasmbox_host_function = True  # type: ignore[attr-defined]

        return wrapper

    return decorator


def _get_parameter_types(func: HostCallback) -> list[str]:
    """Extract simple parameter type names from a callback signature."""

    try:
        signature = inspect.signature(func)
    except (TypeError, ValueError):
        return []

    result: list[str] = []

    for parameter in signature.parameters.values():
        if parameter.kind in (
            inspect.Parameter.VAR_POSITIONAL,
            inspect.Parameter.VAR_KEYWORD,
        ):
            result.append("any")
            continue

        annotation = parameter.annotation

        if annotation is inspect.Parameter.empty:
            result.append("any")
            continue

        if isinstance(annotation, type):
            result.append(annotation.__name__)
        else:
            result.append(str(annotation))

    return result


def _get_return_type(func: HostCallback) -> str:
    """Extract a simple return type name from a callback."""

    try:
        signature = inspect.signature(func)
    except (TypeError, ValueError):
        return "any"

    annotation = signature.return_annotation

    if annotation is inspect.Signature.empty:
        return "any"

    if annotation is None or annotation is type(None):
        return "none"

    if isinstance(annotation, type):
        return annotation.__name__

    return str(annotation)


# ---------------------------------------------------------------------------
# Default trusted host implementations
# ---------------------------------------------------------------------------

@host_function(
    name="log",
    permissions=["logging"],
    description="Log a message from a plugin.",
)
def default_host_log(message: str) -> None:
    """Trusted logging implementation."""

    logger.info("[Plugin] %s", message)


@host_function(
    name="get_customer_data",
    permissions=["customer:read"],
    description="Read customer data by ID.",
)
def default_get_customer_data(
    customer_id: str,
) -> dict[str, Any]:
    """Return mock customer data for testing/demo purposes."""

    return {
        "customer_id": customer_id,
        "name": "Example Customer",
    }


@host_function(
    name="delete_database",
    permissions=["system:admin"],
    description=(
        "Administrative database deletion operation. "
        "Requires explicit authorization."
    ),
)
def default_delete_database(db_name: str) -> None:
    """Administrative operation placeholder.

    Intentionally does NOT perform database deletion.

    A real implementation must be supplied by trusted infrastructure
    and separately protected by tenant authorization and operational
    safeguards.
    """

    raise RuntimeError(
        "delete_database has no destructive default implementation."
    )


# ---------------------------------------------------------------------------
# Default registry
# ---------------------------------------------------------------------------

_default_registry: HostFunctionRegistry | None = None


def get_default_registry() -> HostFunctionRegistry:
    """Return the process-wide default host function registry."""

    global _default_registry

    if _default_registry is None:
        _default_registry = HostFunctionRegistry()

    return _default_registry


def reset_default_registry() -> None:
    """Reset the default registry.

    Primarily useful for isolated tests.
    """

    global _default_registry
    _default_registry = None


__all__ = [
    "RegisteredHostFunction",
    "HostFunctionRegistry",
    "HostCallback",
    "host_function",
    "default_host_log",
    "default_get_customer_data",
    "default_delete_database",
    "get_default_registry",
    "reset_default_registry",
]