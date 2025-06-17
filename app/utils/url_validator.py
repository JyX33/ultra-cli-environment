# ABOUTME: URL validation utility to prevent SSRF attacks and malicious URL access
# ABOUTME: Validates schemes, IP ranges, ports and URL format for security

import ipaddress
from urllib.parse import urlparse

# Configuration for URL validation
ALLOWED_SCHEMES: set[str] = {'http', 'https'}
ALLOWED_PORTS: set[int] = {80, 443, 8080, 8443}
BLOCKED_PORTS: set[int] = {
    22,    # SSH
    23,    # Telnet
    25,    # SMTP
    53,    # DNS
    135,   # Microsoft RPC
    139,   # NetBIOS
    445,   # SMB
    993,   # IMAPS
    995,   # POP3S
    1433,  # Microsoft SQL Server
    1521,  # Oracle
    2049,  # NFS
    3306,  # MySQL
    3389,  # RDP
    5432,  # PostgreSQL
    5984,  # CouchDB
    6379,  # Redis
    8086,  # InfluxDB
    9200,  # Elasticsearch
    9300,  # Elasticsearch
    11211, # Memcached
    27017, # MongoDB
    27018, # MongoDB
    27019, # MongoDB
}


class URLValidationError(Exception):
    """Raised when a URL fails security validation."""
    pass


def is_url_valid(url: str | None) -> bool:
    """
    Check if a URL is valid for security (boolean return).

    Args:
        url: The URL to validate

    Returns:
        True if URL is valid and safe, False otherwise
    """
    return validate_url(url)


def validate_url(url: str | None) -> bool:
    """
    Validate a URL for security to prevent SSRF attacks.

    This function validates URLs to ensure they:
    - Use only HTTP or HTTPS schemes
    - Don't access internal/private IP addresses
    - Don't use suspicious ports commonly used for internal services
    - Have proper URL format

    Args:
        url: The URL to validate

    Returns:
        True if URL is valid and safe, False otherwise
    """
    try:
        validate_url_strict(url)
        return True
    except URLValidationError:
        return False


def validate_url_strict(url: str | None) -> None:
    """
    Validate a URL for security (raises exceptions for backward compatibility).

    Args:
        url: The URL to validate

    Raises:
        URLValidationError: If the URL is invalid or poses a security risk
    """
    _validate_url_internal(url)


def _validate_url_internal(url: str | None) -> None:
    """
    Internal URL validation that raises exceptions.

    Args:
        url: The URL to validate

    Raises:
        URLValidationError: If the URL is invalid or poses a security risk
    """
    if not url:
        raise URLValidationError("Invalid URL format")

    if not isinstance(url, str):
        raise URLValidationError("Invalid URL format")

    # Prevent resource exhaustion with overly long URLs
    if len(url) > 2048:
        raise URLValidationError("Invalid URL format")

    try:
        parsed = urlparse(url)
    except Exception:
        raise URLValidationError("Invalid URL format") from None

    # Check for HTTP header injection patterns in URL
    if '\n' in url or '\r' in url or '%0a' in url.lower() or '%0d' in url.lower():
        raise URLValidationError("Invalid URL format")

    # Validate scheme first (case-insensitive)
    scheme = parsed.scheme.lower() if parsed.scheme else ""
    if scheme not in ALLOWED_SCHEMES:
        raise URLValidationError("Only HTTP and HTTPS schemes are allowed")

    # Check for required components after scheme validation
    if not parsed.netloc:
        raise URLValidationError("Invalid URL format")

    # Extract hostname and port with error handling
    try:
        hostname = parsed.hostname
        port = parsed.port
    except ValueError:
        raise URLValidationError("Invalid URL format") from None

    if not hostname:
        raise URLValidationError("Invalid URL format")

    # Check for IP address (including various representations)
    resolved_ip = _resolve_hostname_to_ip(hostname)
    if resolved_ip:
        _validate_ip_address(resolved_ip)
    else:
        # Not an IP address, check if it's a hostname that might resolve to internal IPs
        _validate_hostname(hostname)

    # Validate port if specified
    if port is not None:
        _validate_port(port)


def _resolve_hostname_to_ip(hostname: str) -> ipaddress.IPv4Address | ipaddress.IPv6Address | None:
    """
    Try to resolve hostname to IP address, handling various obfuscation techniques.

    Args:
        hostname: The hostname to resolve

    Returns:
        IP address if hostname represents an IP, None if it's a regular hostname
    """
    # Direct IP address check
    try:
        return ipaddress.ip_address(hostname)
    except ValueError:
        pass

    # Check for decimal representation (e.g., 2130706433 for 127.0.0.1)
    try:
        if hostname.isdigit():
            decimal_value = int(hostname)
            if 0 <= decimal_value <= 4294967295:  # Valid IPv4 range
                # Convert decimal to IP
                return ipaddress.IPv4Address(decimal_value)
    except (ValueError, ipaddress.AddressValueError):
        pass

    # Check for hexadecimal representation (e.g., 0x7f000001 for 127.0.0.1)
    try:
        if hostname.lower().startswith('0x'):
            hex_value = int(hostname, 16)
            if 0 <= hex_value <= 4294967295:
                return ipaddress.IPv4Address(hex_value)
    except (ValueError, ipaddress.AddressValueError):
        pass

    # Check for octal representation (e.g., 017700000001 for 127.0.0.1)
    try:
        if hostname.startswith('0') and len(hostname) > 1 and hostname.isdigit():
            octal_value = int(hostname, 8)
            if 0 <= octal_value <= 4294967295:
                return ipaddress.IPv4Address(octal_value)
    except (ValueError, ipaddress.AddressValueError):
        pass

    # Check for short IP formats (e.g., 127.1 for 127.0.0.1)
    try:
        parts = hostname.split('.')
        if 1 <= len(parts) <= 4 and all(part.isdigit() for part in parts):
            # Pad with zeros to make it a full IP
            while len(parts) < 4:
                parts.append('0')
            full_ip = '.'.join(parts)
            return ipaddress.IPv4Address(full_ip)
    except (ValueError, ipaddress.AddressValueError):
        pass

    return None


def _validate_ip_address(ip_addr: ipaddress.IPv4Address | ipaddress.IPv6Address) -> None:
    """
    Validate that an IP address is not internal/private.

    Args:
        ip_addr: The IP address to validate

    Raises:
        URLValidationError: If the IP address is internal/private
    """
    # Check for localhost
    if ip_addr.is_loopback:
        raise URLValidationError("Internal network access not allowed")

    # Check for private networks
    if ip_addr.is_private:
        raise URLValidationError("Internal network access not allowed")

    # Check for link-local addresses
    if ip_addr.is_link_local:
        raise URLValidationError("Internal network access not allowed")

    # Check for multicast addresses
    if ip_addr.is_multicast:
        raise URLValidationError("Internal network access not allowed")

    # Check for reserved addresses
    if ip_addr.is_reserved:
        raise URLValidationError("Internal network access not allowed")

    # Additional checks for IPv4
    if isinstance(ip_addr, ipaddress.IPv4Address):
        # Check for broadcast address
        if str(ip_addr) == '255.255.255.255':
            raise URLValidationError("Internal network access not allowed")

        # Check for any address (0.0.0.0)
        if str(ip_addr) == '0.0.0.0':
            raise URLValidationError("Internal network access not allowed")


def _validate_hostname(hostname: str) -> None:
    """
    Validate hostname to prevent common SSRF bypasses.

    Args:
        hostname: The hostname to validate

    Raises:
        URLValidationError: If the hostname poses a security risk
    """
    hostname_lower = hostname.lower()

    # Block localhost variations
    localhost_variations = [
        'localhost',
        'localhost.localdomain',
        '0', '0.0', '0.0.0', '0.0.0.0'
    ]

    if hostname_lower in localhost_variations:
        raise URLValidationError("Internal network access not allowed")

    # Block common internal hostnames
    internal_hostnames = [
        'metadata.google.internal',
        '169.254.169.254',  # AWS/GCP metadata service
        'metadata',
        'consul',
        'vault'
    ]

    if hostname_lower in internal_hostnames:
        raise URLValidationError("Internal network access not allowed")


def _validate_port(port: int) -> None:
    """
    Validate that a port is not commonly used for internal services.

    Args:
        port: The port number to validate

    Raises:
        URLValidationError: If the port is commonly used for internal services
    """
    # Check if port is explicitly blocked
    if port in BLOCKED_PORTS:
        raise URLValidationError(f"Port {port} is not allowed (commonly used for internal services)")

    # Block ports below 1024 except for allowed web ports
    if port < 1024 and port not in ALLOWED_PORTS:
        raise URLValidationError(f"Port {port} is not allowed (privileged port)")

    # Block invalid port ranges
    if port > 65535 or port < 1:
        raise URLValidationError(f"Port {port} is not allowed (invalid port range)")
