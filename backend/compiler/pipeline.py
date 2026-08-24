"""
WasmBox Compiler Pipeline.

Orchestrates the entire compilation process, from parsing Python source
to generating the final WASM artifact.
"""

from __future__ import annotations

import hashlib
import time
import uuid

from .backends.embedded import EmbeddedPythonBackend
from .cache import CompilationCache
from .config import CompileConfig, WasmBackendType
from .dependencies import DependencyManager
from .errors import CompilerError, CompilerStage, Diagnostic, ErrorSeverity
from .manifest import ManifestGenerator, ManifestSerializer, ManifestValidator
from .models import CompilationMetrics, CompilationResult, DiagnosticModel, DiagnosticSeverity
from .packager import WasmPackager
from .parser import PluginParser
from .transformer import SourceTransformer
from .validator import SecurityValidator
from .analyzer import StaticAnalyzer
from .wasm_validator import WasmValidator


class CompilerPipeline:
    """Main orchestrator for the WasmBox compiler pipeline."""

    def __init__(self, config: CompileConfig | None = None) -> None:
        """Initialize all stage components."""
        self.config = config or CompileConfig()
        self.parser = PluginParser(self.config.compilation_limits, self.config.entrypoint_function)
        self.validator = SecurityValidator()
        self.analyzer = StaticAnalyzer()
        self.transformer = SourceTransformer()
        self.dependency_manager = DependencyManager()
        self.packager = WasmPackager()
        self.manifest_generator = ManifestGenerator()
        self.manifest_validator = ManifestValidator()
        self.manifest_serializer = ManifestSerializer()
        self.wasm_validator = WasmValidator()
        self.cache = CompilationCache(self.config.cache_dir) if self.config.enable_cache else None
        
        self.backend = self._select_backend()

    def _select_backend(self):
        """Select the appropriate WasmCompilerBackend based on config.backend."""
        if self.config.backend == WasmBackendType.EMBEDDED:
            return EmbeddedPythonBackend()
        return EmbeddedPythonBackend()

    def compile(
        self, source: str, plugin_name: str, tenant_id: str, dependencies: list[str] | None = None
    ) -> CompilationResult:
        """Run the full compilation pipeline to generate a WASM artifact."""
        deps = dependencies or []
        metrics = CompilationMetrics()
        result = CompilationResult(
            success=False,
            plugin_name=plugin_name,
            tenant_id=tenant_id,
            metrics=metrics,
        )
        t_start = time.perf_counter()

        try:
            # 1. Check cache (if enabled)
            if self.cache:
                cache_key = self.cache.compute_cache_key(source, deps, self.config)
                cached = self.cache.get(cache_key, tenant_id)
                if cached:
                    cached.metrics.cache_hit = True
                    return cached
            else:
                cache_key = None

            # Generate ID
            if self.config.deterministic_builds:
                id_input = f"{tenant_id}:{plugin_name}:{hashlib.sha256(source.encode('utf-8')).hexdigest()}"
                result.plugin_id = hashlib.sha256(id_input.encode('utf-8')).hexdigest()[:16]
            else:
                result.plugin_id = str(uuid.uuid4())

            metrics.source_size_bytes = len(source.encode('utf-8'))

            # 2. Parse source -> ParseResult
            t0 = time.perf_counter()
            parse_result = self.parser.parse(source, filename=f"<{plugin_name}>")
            metrics.parse_time_ms = (time.perf_counter() - t0) * 1000
            metrics.source_lines = len(parse_result.lines)
            self._collect_diagnostics(result, parse_result.diagnostics)

            # 5. Check for error-level diagnostics
            if result.has_errors:
                return self._fail_result(result, t_start)

            # 3. Validate security -> list[Diagnostic]
            t0 = time.perf_counter()
            val_diags = self.validator.validate(parse_result.tree, source, self.config.security_policy)
            metrics.validation_time_ms = (time.perf_counter() - t0) * 1000
            self._collect_diagnostics(result, val_diags)

            if result.has_errors:
                return self._fail_result(result, t_start)

            # 4. Analyze -> AnalysisResult
            t0 = time.perf_counter()
            analysis_result = self.analyzer.analyze(parse_result.tree, source, self.config)
            metrics.analysis_time_ms = (time.perf_counter() - t0) * 1000
            
            # 6. Transform source -> TransformResult
            t0 = time.perf_counter()
            transform_result = self.transformer.transform(source, analysis_result, self.config)
            metrics.transformation_time_ms = (time.perf_counter() - t0) * 1000
            self._collect_diagnostics(result, transform_result.diagnostics)

            if result.has_errors:
                return self._fail_result(result, t_start)

            # 7. Resolve dependencies -> DependencyResult
            t0 = time.perf_counter()
            dep_result = self.dependency_manager.resolve(analysis_result, self.config)
            metrics.dependency_time_ms = (time.perf_counter() - t0) * 1000
            self._collect_diagnostics(result, dep_result.diagnostics)

            # 8. Check for forbidden dependencies, abort if found
            if result.has_errors:
                return self._fail_result(result, t_start)

            # 9. Generate initial manifest
            manifest = self.manifest_generator.generate(
                plugin_name=plugin_name,
                tenant_id=tenant_id,
                analysis=analysis_result,
                artifact_hash="",
                artifact_size=0,
                config=self.config
            )

            # 10. Use backend.compile() to generate WasmArtifact
            t0 = time.perf_counter()
            artifact = self.backend.compile(
                source=transform_result.source,
                manifest=manifest,
                config=self.config
            )
            metrics.backend_compile_time_ms = (time.perf_counter() - t0) * 1000
            
            # 11. Update manifest with actual hash and size
            manifest.artifact_hash = artifact.sha256
            manifest.artifact_size_bytes = artifact.size_bytes
            
            result.artifact_bytes = artifact.wasm_bytes
            result.artifact_hash = artifact.sha256
            result.artifact_size_bytes = artifact.size_bytes
            result.manifest = manifest
            metrics.artifact_size_bytes = artifact.size_bytes
            
            # 12. Validate WASM artifact -> more diagnostics
            t0 = time.perf_counter()
            wasm_diags = self.wasm_validator.validate(artifact.wasm_bytes, self.config)
            metrics.wasm_validation_time_ms = (time.perf_counter() - t0) * 1000
            self._collect_diagnostics(result, wasm_diags)

            if result.has_errors:
                return self._fail_result(result, t_start)

            # 13. If all OK, return successful CompilationResult
            result.success = True
            metrics.total_time_ms = (time.perf_counter() - t_start) * 1000

            # 14. Cache result (if enabled)
            if self.cache and cache_key:
                self.cache.put(cache_key, tenant_id, result)

            return result

        except CompilerError as e:
            self._collect_diagnostics(result, [e.to_diagnostic()])
            return self._fail_result(result, t_start)
        except Exception as e:
            diag = Diagnostic(
                code="E999",
                severity=ErrorSeverity.ERROR,
                stage=CompilerStage.PIPELINE,
                message=f"Unhandled exception during compilation: {str(e)}",
            )
            self._collect_diagnostics(result, [diag])
            return self._fail_result(result, t_start)

    def validate_only(self, source: str) -> CompilationResult:
        """Run only parse, validate, analyze stages."""
        metrics = CompilationMetrics()
        result = CompilationResult(
            success=False,
            metrics=metrics,
        )
        t_start = time.perf_counter()
        
        try:
            metrics.source_size_bytes = len(source.encode('utf-8'))

            t0 = time.perf_counter()
            parse_result = self.parser.parse(source)
            metrics.parse_time_ms = (time.perf_counter() - t0) * 1000
            metrics.source_lines = len(parse_result.lines)
            self._collect_diagnostics(result, parse_result.diagnostics)

            if result.has_errors:
                return self._fail_result(result, t_start)

            t0 = time.perf_counter()
            val_diags = self.validator.validate(parse_result.tree, source, self.config.security_policy)
            metrics.validation_time_ms = (time.perf_counter() - t0) * 1000
            self._collect_diagnostics(result, val_diags)

            if result.has_errors:
                return self._fail_result(result, t_start)

            t0 = time.perf_counter()
            analysis_result = self.analyzer.analyze(parse_result.tree, source, self.config)
            metrics.analysis_time_ms = (time.perf_counter() - t0) * 1000
            
            t0 = time.perf_counter()
            dep_result = self.dependency_manager.resolve(analysis_result, self.config)
            metrics.dependency_time_ms = (time.perf_counter() - t0) * 1000
            self._collect_diagnostics(result, dep_result.diagnostics)

            if result.has_errors:
                return self._fail_result(result, t_start)

            result.success = True
            metrics.total_time_ms = (time.perf_counter() - t_start) * 1000
            return result
            
        except CompilerError as e:
            self._collect_diagnostics(result, [e.to_diagnostic()])
            return self._fail_result(result, t_start)
        except Exception as e:
            diag = Diagnostic(
                code="E999",
                severity=ErrorSeverity.ERROR,
                stage=CompilerStage.PIPELINE,
                message=f"Unhandled exception during validation: {str(e)}",
            )
            self._collect_diagnostics(result, [diag])
            return self._fail_result(result, t_start)

    def _fail_result(self, result: CompilationResult, t_start: float) -> CompilationResult:
        """Helper to mark a compilation result as failed."""
        result.success = False
        result.metrics.total_time_ms = (time.perf_counter() - t_start) * 1000
        return result

    def _collect_diagnostics(self, result: CompilationResult, diagnostics: list[Diagnostic]) -> None:
        """Helper to add diagnostics to the result object appropriately."""
        for diag in diagnostics:
            # Create DiagnosticModel manually as required by the model
            model = DiagnosticModel(
                code=diag.code,
                severity=DiagnosticSeverity(diag.severity.value),
                stage=diag.stage.value,
                message=diag.message,
                line=diag.location.line if diag.location else None,
                column=diag.location.column if diag.location else None,
                suggestion=diag.suggestion
            )
            if diag.severity == ErrorSeverity.ERROR:
                result.errors.append(model)
            elif diag.severity == ErrorSeverity.WARNING:
                result.warnings.append(model)
            else:
                result.diagnostics.append(model)
