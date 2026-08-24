"""
WasmBox Compiler API Routes.

FastAPI routes for compiling and validating WebAssembly plugins.
"""

from __future__ import annotations

from typing import Any, List
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from backend.compiler import compile as compile_plugin, validate as validate_source
from backend.compiler.config import CompilerEnvironment
from backend.compiler.models import CompilationResult, DiagnosticModel, PluginManifest, CompilationMetrics


router = APIRouter(prefix="/api/plugins", tags=["Compiler"])


class CompileRequest(BaseModel):
    """Request model for plugin compilation."""
    name: str = Field(..., description="Name of the plugin")
    source: str = Field(..., description="Python source code of the plugin")
    tenant_id: str = Field(..., description="Tenant ID owning the plugin")
    dependencies: list[str] = Field(default_factory=list, description="List of dependencies")


class CompileResponse(BaseModel):
    """Response model for plugin compilation."""
    success: bool
    plugin_id: str | None = None
    artifact_hash: str | None = None
    artifact_size_bytes: int | None = None
    manifest: dict[str, Any] | None = None
    diagnostics: list[DiagnosticModel] = Field(default_factory=list)
    metrics: dict[str, Any] = Field(default_factory=dict)


class ValidateRequest(BaseModel):
    """Request model for plugin source validation."""
    source: str = Field(..., description="Python source code of the plugin to validate")


class ValidateResponse(BaseModel):
    """Response model for plugin source validation."""
    success: bool
    diagnostics: list[DiagnosticModel] = Field(default_factory=list)
    metrics: dict[str, Any] = Field(default_factory=dict)


@router.post("/compile", response_model=CompileResponse)
async def compile_route(request: CompileRequest) -> CompileResponse:
    """Compile Python source code into a WebAssembly plugin artifact.
    
    Validates the source code against security policies, analyzes dependencies,
    and generates a WasmBox compatible WebAssembly module.
    """
    try:
        result: CompilationResult = compile_plugin(
            source=request.source,
            plugin_name=request.name,
            tenant_id=request.tenant_id,
        )
        
        response = CompileResponse(
            success=result.success,
            plugin_id=result.plugin_id,
            artifact_hash=result.artifact_hash,
            artifact_size_bytes=result.artifact_size_bytes,
            diagnostics=result.diagnostics,
            metrics=result.metrics.model_dump() if result.metrics else {},
        )
        
        if result.manifest:
            response.manifest = result.manifest.model_dump()
            
        if not result.success:
            # We don't raise HTTPException here because we want to return the diagnostics
            pass
            
        return response
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Compiler encountered an unexpected error: {str(e)}"
        )


@router.post("/validate", response_model=ValidateResponse)
async def validate_route(request: ValidateRequest) -> ValidateResponse:
    """Validate Python source code without generating an artifact.
    
    Checks syntax and validates against security policies.
    """
    try:
        # We assume validate_source signature matches compile but without some fields
        # If validate_source doesn't exist, we can use compile with a config that skips backend
        result: CompilationResult = validate_source(source=request.source)
        
        return ValidateResponse(
            success=result.success,
            diagnostics=result.diagnostics,
            metrics=result.metrics.model_dump() if result.metrics else {},
        )
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Validator encountered an unexpected error: {str(e)}"
        )


@router.get("/../compiler/env")
async def env_route() -> dict[str, Any]:
    """Get compiler environment diagnostics.
    
    Returns information about the available compiler toolchain and runtimes.
    """
    env = CompilerEnvironment.detect()
    return {
        "python_version": env.python_version,
        "wasmtime_available": env.wasmtime_available,
        "wasmtime_version": env.wasmtime_version,
        "micropython_wasm_available": env.micropython_wasm_available,
        "wasm_backend": env.wasm_backend,
        "platform": env.platform,
        "issues": env.validate()
    }

# Also add the exact path requested by user:
@router.get("/env")
async def env_route_alternate() -> dict[str, Any]:
    """Get compiler environment diagnostics."""
    env = CompilerEnvironment.detect()
    return {
        "python_version": env.python_version,
        "wasmtime_available": env.wasmtime_available,
        "wasmtime_version": env.wasmtime_version,
        "micropython_wasm_available": env.micropython_wasm_available,
        "wasm_backend": env.wasm_backend,
        "platform": env.platform,
        "issues": env.validate()
    }
