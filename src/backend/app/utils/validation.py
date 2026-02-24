"""
Input validation utilities for security and data integrity.

This module provides validation functions for:
- SQL injection prevention
- XSS (Cross-Site Scripting) prevention
- Path traversal prevention
- Command injection prevention
- Input sanitization

Usage:
    >>> from app.utils.validation import validate_email, sanitize_html
    >>> is_valid = validate_email("user@example.com")
    >>> safe_html = sanitize_html("<script>alert('xss')</script>")
"""
import re
import urllib.parse
from html import escape as html_escape
from typing import Any, List, Optional

# ==================== SQL Injection Prevention ====================

DANGEROUS_SQL_PATTERNS = [
    r"--",  # SQL comment
    r";",  # Statement separator
    r"/\*", r"\*/",  # Multi-line comment
    r"\b(ALTER|CREATE|DELETE|DROP|EXEC|EXECUTE|INSERT|INTO|UPDATE|UNION|SELECT)\b",
    r"\b(OR|AND)\s+\S+\s*(=|LIKE|IN)",
]

DANGEROUS_SQL_REGEX = re.compile(
    "|".join(DANGEROUS_SQL_PATTERNS),
    re.IGNORECASE | re.MULTILINE
)


def detect_sql_injection(value: str) -> bool:
    """Detect potential SQL injection in input value.

    Args:
        value: The string value to check.

    Returns:
        True if potential SQL injection is detected, False otherwise.
    """
    if not isinstance(value, str):
        return False
    return bool(DANGEROUS_SQL_REGEX.search(value))


def sanitize_sql_identifier(identifier: str) -> str:
    """Sanitize a SQL identifier (table name, column name, etc.).

    Args:
        identifier: The identifier to sanitize.

    Returns:
        Sanitized identifier safe for SQL queries.

    Raises:
        ValueError: If identifier contains dangerous characters.
    """
    # Only allow alphanumeric characters, underscores, and dots
    if not re.match(r'^[a-zA-Z_][a-zA-Z0-9_.]*$', identifier):
        raise ValueError(f"Invalid SQL identifier: {identifier}")
    return identifier


# ==================== XSS Prevention ====================

DANGEROUS_HTML_TAGS = {
    'script', 'iframe', 'object', 'embed', 'form', 'input', 'button',
    'link', 'meta', 'style', 'applet', 'body', 'onload', 'onerror',
}

DANGEROUS_HTML_EVENTS = {
    'onload', 'onerror', 'onclick', 'onmouseover', 'onmouseout',
    'onfocus', 'onblur', 'onchange', 'onsubmit', 'onreset', 'onkeydown',
    'onkeypress', 'onkeyup', 'onscroll',
}

XSS_PATTERN = re.compile(
    r'<\s*/?\s*(script|iframe|object|embed|form|input|button|link|meta|style|applet)',
    re.IGNORECASE
)


def detect_xss(value: str) -> bool:
    """Detect potential XSS (Cross-Site Scripting) attack.

    Args:
        value: The string value to check.

    Returns:
        True if potential XSS is detected, False otherwise.
    """
    if not isinstance(value, str):
        return False

    # Check for dangerous HTML tags
    if XSS_PATTERN.search(value):
        return True

    # Check for dangerous event handlers
    for event in DANGEROUS_HTML_EVENTS:
        if event in value.lower():
            return True

    # Check for javascript: protocol
    if "javascript:" in value.lower():
        return True

    return False


def sanitize_html(value: str, allowed_tags: Optional[List[str]] = None) -> str:
    """Sanitize HTML input to prevent XSS attacks.

    This function escapes HTML entities and removes potentially dangerous content.

    Args:
        value: The HTML string to sanitize.
        allowed_tags: Optional list of allowed HTML tags (e.g., ['b', 'i', 'p']).

    Returns:
        Sanitized HTML string safe for display.
    """
    if not isinstance(value, str):
        return str(value)

    # First, HTML escape the entire string
    safe_value = html_escape(value)

    # If no allowed tags specified, return escaped string
    if not allowed_tags:
        return safe_value

    # For more advanced sanitization with allowed tags,
    # you would use a library like bleach
    # For now, we'll keep it simple and just return escaped HTML
    return safe_value


def escape_html(value: Any) -> str:
    """Escape HTML special characters.

    Args:
        value: The value to escape (will be converted to string).

    Returns:
        HTML-escaped string.
    """
    return html_escape(str(value))


# ==================== Path Traversal Prevention ====================

PATH_TRAVERSAL_PATTERNS = [
    r'\.\./',  # Parent directory traversal
    r'\.\.\\',  # Parent directory (Windows style)
    r'~',  # Home directory
    r'%2e%2e',  # URL encoded parent directory
    r'%252e',  # Double URL encoded dot
    r'\x00',  # Null byte
]

PATH_TRAVERSAL_REGEX = re.compile(
    "|".join(PATH_TRAVERSAL_PATTERNS),
    re.IGNORECASE
)


def detect_path_traversal(path: str) -> bool:
    """Detect potential path traversal attack.

    Args:
        path: The file path to check.

    Returns:
        True if path traversal is detected, False otherwise.
    """
    if not isinstance(path, str):
        return False

    # Check for path traversal patterns
    if PATH_TRAVERSAL_REGEX.search(path):
        return True

    # Check for absolute paths (often dangerous)
    if path.startswith('/') or path.startswith('\\'):
        return True

    # Check for Windows drive letters
    if re.match(r'^[A-Za-z]:\\', path):
        return True

    return False


def sanitize_path(path: str, base_dir: str = "/tmp") -> str:
    """Sanitize a file path to prevent path traversal attacks.

    Args:
        path: The file path to sanitize.
        base_dir: The base directory for relative paths.

    Returns:
        Safe file path within base_dir.
    """
    import os

    # Remove any null bytes
    path = path.replace('\x00', '')

    # Get the basename (filename only)
    safe_path = os.path.basename(path)

    # Join with base directory
    full_path = os.path.join(base_dir, safe_path)

    # Ensure the result is within base_dir
    full_path = os.path.abspath(full_path)
    base_dir = os.path.abspath(base_dir)

    if not full_path.startswith(base_dir):
        raise ValueError(f"Path traversal detected: {path}")

    return full_path


# ==================== Command Injection Prevention ====================

DANGEROUS_COMMAND_CHARS = [';', '|', '&', '$', '`', '(', ')', '<', '>', '\n', '\r']
DANGEROUS_COMMANDS = [
    'curl', 'wget', 'nc', 'netcat', 'telnet', 'ssh',
    'eval', 'exec', 'system', 'passthru', 'shell_exec',
    'ping', 'chmod', 'chown', 'rm', 'mv', 'cp',
]


def detect_command_injection(value: str) -> bool:
    """Detect potential command injection attack.

    Args:
        value: The string value to check.

    Returns:
        True if command injection is detected, False otherwise.
    """
    if not isinstance(value, str):
        return False

    # Check for dangerous characters
    for char in DANGEROUS_COMMAND_CHARS:
        if char in value:
            return True

    # Check for dangerous commands
    value_lower = value.lower()
    for cmd in DANGEROUS_COMMANDS:
        if cmd in value_lower:
            return True

    return False


def sanitize_command_arg(arg: str) -> str:
    """Sanitize a command line argument.

    Args:
        arg: The argument to sanitize.

    Returns:
        Sanitized argument safe for command execution.

    Raises:
        ValueError: If argument contains dangerous characters.
    """
    # Only allow safe characters: alphanumeric, hyphens, underscores, dots, slashes, colons
    # This is restrictive but safe
    if not re.match(r'^[a-zA-Z0-9._/\-:\s]+$', arg):
        raise ValueError(f"Invalid command argument: {arg}")
    return arg


# ==================== Email Validation ====================

EMAIL_REGEX = re.compile(
    r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
)


def validate_email(email: str) -> bool:
    """Validate an email address format.

    Args:
        email: The email address to validate.

    Returns:
        True if email format is valid, False otherwise.
    """
    if not isinstance(email, str):
        return False
    return bool(EMAIL_REGEX.match(email))


def sanitize_email(email: str) -> str:
    """Sanitize an email address (lowercase and strip whitespace).

    Args:
        email: The email address to sanitize.

    Returns:
        Sanitized email address.
    """
    if not isinstance(email, str):
        return ""
    return email.strip().lower()


# ==================== Username Validation ====================

USERNAME_REGEX = re.compile(r'^[a-zA-Z0-9_-]{3,50}$')


def validate_username(username: str) -> bool:
    """Validate a username format.

    Args:
        username: The username to validate.

    Returns:
        True if username format is valid, False otherwise.
    """
    if not isinstance(username, str):
        return False
    return bool(USERNAME_REGEX.match(username))


def sanitize_username(username: str) -> str:
    """Sanitize a username.

    Args:
        username: The username to sanitize.

    Returns:
        Sanitized username.
    """
    if not isinstance(username, str):
        return ""

    # Remove invalid characters, keep only alphanumeric, underscore, hyphen
    sanitized = re.sub(r'[^a-zA-Z0-9_-]', '', username)

    # Truncate to max length
    return sanitized[:50]


# ==================== General Input Sanitization ====================

def sanitize_string(value: Any, max_length: int = 10000) -> str:
    """Sanitize a string input by removing null bytes and limiting length.

    Args:
        value: The value to sanitize.
        max_length: Maximum allowed length.

    Returns:
        Sanitized string.
    """
    if not isinstance(value, str):
        value = str(value)

    # Remove null bytes
    value = value.replace('\x00', '')

    # Limit length
    if len(value) > max_length:
        value = value[:max_length]

    # Strip whitespace
    return value.strip()


def validate_max_length(value: str, max_length: int) -> bool:
    """Validate that a string doesn't exceed maximum length.

    Args:
        value: The string to validate.
        max_length: Maximum allowed length.

    Returns:
        True if length is within limit, False otherwise.
    """
    return len(value) <= max_length


def validate_min_length(value: str, min_length: int) -> bool:
    """Validate that a string meets minimum length.

    Args:
        value: The string to validate.
        min_length: Minimum required length.

    Returns:
        True if length meets minimum, False otherwise.
    """
    return len(value) >= min_length


# ==================== URL Validation ====================

def validate_url(url: str) -> bool:
    """Validate a URL format.

    Args:
        url: The URL to validate.

    Returns:
        True if URL format is valid, False otherwise.
    """
    if not isinstance(url, str):
        return False

    try:
        result = urllib.parse.urlparse(url)
        # Must have scheme and netloc
        return all([result.scheme, result.netloc]) and result.scheme in ('http', 'https', '')
    except Exception:
        return False


def sanitize_url(url: str) -> str:
    """Sanitize a URL by removing dangerous fragments.

    Args:
        url: The URL to sanitize.

    Returns:
        Sanitized URL.

    Raises:
        ValueError: If URL is invalid or contains dangerous content.
    """
    if not isinstance(url, str):
        raise ValueError("URL must be a string")

    # Parse the URL
    parsed = urllib.parse.urlparse(url)

    # Check for javascript: protocol
    if parsed.scheme and parsed.scheme.lower() == 'javascript':
        raise ValueError("javascript: protocol is not allowed")

    # Rebuild the URL without the fragment if it looks suspicious
    if parsed.fragment and any(char in parsed.fragment for char in ['<', '>', '"', "'"]):
        # Remove the fragment
        url = url.rsplit('#', 1)[0]

    return url


# ==================== Integer Validation ====================

def validate_integer(value: Any, min_val: Optional[int] = None, max_val: Optional[int] = None) -> bool:
    """Validate that a value is an integer within optional range.

    Args:
        value: The value to validate.
        min_val: Minimum allowed value (optional).
        max_val: Maximum allowed value (optional).

    Returns:
        True if value is valid integer within range, False otherwise.
    """
    try:
        int_value = int(value)
    except (ValueError, TypeError):
        return False

    if min_val is not None and int_value < min_val:
        return False
    if max_val is not None and int_value > max_val:
        return False
    return True


# ==================== Float Validation ====================

def validate_float(value: Any, min_val: Optional[float] = None, max_val: Optional[float] = None) -> bool:
    """Validate that a value is a float within optional range.

    Args:
        value: The value to validate.
        min_val: Minimum allowed value (optional).
        max_val: Maximum allowed value (optional).

    Returns:
        True if value is valid float within range, False otherwise.
    """
    try:
        float_value = float(value)
    except (ValueError, TypeError):
        return False

    if min_val is not None and float_value < min_val:
        return False
    if max_val is not None and float_value > max_val:
        return False
    return True


# ==================== Choice Validation ====================

def validate_choice(value: Any, allowed_choices: List[Any]) -> bool:
    """Validate that a value is in the list of allowed choices.

    Args:
        value: The value to validate.
        allowed_choices: List of allowed values.

    Returns:
        True if value is in allowed choices, False otherwise.
    """
    return value in allowed_choices


# ==================== Composite Validation ====================

class ValidationResult:
    """Result of a validation operation."""

    def __init__(
        self,
        is_valid: bool,
        errors: Optional[List[str]] = None,
        warnings: Optional[List[str]] = None
    ):
        """Initialize validation result.

        Args:
            is_valid: Whether validation passed.
            errors: List of error messages.
            warnings: List of warning messages.
        """
        self.is_valid = is_valid
        self.errors = errors or []
        self.warnings = warnings or []

    def add_error(self, message: str) -> None:
        """Add an error message.

        Args:
            message: The error message.
        """
        self.errors.append(message)
        self.is_valid = False

    def add_warning(self, message: str) -> None:
        """Add a warning message.

        Args:
            message: The warning message.
        """
        self.warnings.append(message)

    def to_dict(self) -> dict:
        """Convert result to dictionary.

        Returns:
            Dictionary representation of the result.
        """
        result = {"is_valid": self.is_valid}
        if self.errors:
            result["errors"] = self.errors
        if self.warnings:
            result["warnings"] = self.warnings
        return result


def validate_user_input(
    data: dict,
    rules: dict,
    allow_extra_fields: bool = True
) -> ValidationResult:
    """Validate user input based on validation rules.

    Args:
        data: Dictionary of user input.
        rules: Dictionary of field names to validation functions.
        allow_extra_fields: Whether to allow fields not in rules.

    Returns:
        ValidationResult with any errors found.

    Example:
        >>> rules = {
        ...     "username": lambda x: validate_username(x) or "Invalid username",
        ...     "email": lambda x: validate_email(x) or "Invalid email",
        ... }
        >>> result = validate_user_input({"username": "test", "email": "test@example.com"}, rules)
    """
    result = ValidationResult(is_valid=True)

    # Check required fields
    for field, validator in rules.items():
        if field not in data:
            result.add_error(f"Required field '{field}' is missing")
            continue

        value = data.get(field)
        error_message = validator(value)

        if error_message is not True:  # Either False or error string
            if isinstance(error_message, str):
                result.add_error(f"{field}: {error_message}")
            else:
                result.add_error(f"{field}: Validation failed")

    # Check for extra fields
    if not allow_extra_fields:
        extra_fields = set(data.keys()) - set(rules.keys())
        for field in extra_fields:
            result.add_warning(f"Unexpected field '{field}' will be ignored")

    return result
