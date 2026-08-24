import pytest
from backend.compiler.errors import (
    CompilerError,
    CompilerStage,
    ParseError,
    SecurityViolation,
    Diagnostic,
    ErrorSeverity,
    SourceLocation
)

def test_compiler_error_message():
    err = CompilerError(
        code="E999",
        stage=CompilerStage.PIPELINE,
        message="Something went wrong",
        line=10,
        column=5,
        suggestion="Fix it"
    )
    
    msg = err.format_message()
    assert "[E999]" in msg
    assert "pipeline:" in msg
    assert "Something went wrong" in msg
    assert "Line 10" in msg
    assert "Column 5" in msg
    assert "Suggestion: Fix it" in msg

def test_compiler_error_to_dict():
    err = CompilerError(
        code="E999",
        stage=CompilerStage.PIPELINE,
        message="Something went wrong",
        line=10
    )
    
    data = err.to_dict()
    assert data["code"] == "E999"
    assert data["stage"] == "pipeline"
    assert data["message"] == "Something went wrong"
    assert data["location"]["line"] == 10

def test_parse_error_defaults():
    err = ParseError("Syntax error", line=5)
    
    assert err.code == "E001"
    assert err.stage == CompilerStage.PARSER
    assert err.message == "Syntax error"
    assert err.line == 5

def test_security_violation_defaults():
    err = SecurityViolation("Forbidden import")
    
    assert err.code == "E200"
    assert err.stage == CompilerStage.VALIDATOR
    assert err.message == "Forbidden import"

def test_diagnostic_to_dict():
    diag = Diagnostic(
        code="E123",
        severity=ErrorSeverity.WARNING,
        stage=CompilerStage.ANALYZER,
        message="Be careful",
        location=SourceLocation(line=5, column=2),
        suggestion="Do something else"
    )
    
    data = diag.to_dict()
    assert data["code"] == "E123"
    assert data["severity"] == "warning"
    assert data["stage"] == "analyzer"
    assert data["message"] == "Be careful"
    assert data["location"]["line"] == 5
    assert data["location"]["column"] == 2
    assert data["suggestion"] == "Do something else"

def test_diagnostic_str():
    diag = Diagnostic(
        code="E123",
        severity=ErrorSeverity.ERROR,
        stage=CompilerStage.VALIDATOR,
        message="Bad thing",
        location=SourceLocation(line=5, filename="test.py"),
        suggestion="Don't do it"
    )
    
    s = str(diag)
    assert "ERROR E123: Bad thing" in s
    assert "at line 5" in s
    assert "in test.py" in s
    assert "Suggestion: Don't do it" in s

def test_error_hierarchy():
    assert issubclass(ParseError, CompilerError)
    assert issubclass(SecurityViolation, CompilerError)
    
    err = ParseError("err")
    assert isinstance(err, Exception)

def test_error_with_location():
    err = CompilerError(
        code="TEST",
        stage=CompilerStage.PIPELINE,
        message="test message",
        line=42,
        column=12
    )
    
    diag = err.to_diagnostic()
    assert diag.location is not None
    assert diag.location.line == 42
    assert diag.location.column == 12
