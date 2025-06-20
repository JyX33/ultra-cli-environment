# ABOUTME: URL validation utility to prevent SSRF attacks and malicious URL access
# ABOUTME: Validates schemes, IP ranges, ports and URL format for security

from dataclasses import dataclass
import ipaddress
import re
import unicodedata
from urllib.parse import unquote, urlparse

from app.core.exceptions import (
    InvalidURLFormatError,
    RestrictedNetworkError,
    RestrictedPortError,
    SecurityViolationError,
    UnsupportedSchemeError,
    URLValidationError,
)

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


@dataclass
class URLValidationResult:
    """Result of URL validation with detailed information."""
    is_valid: bool
    url: str
    error_type: str | None = None
    error_message: str | None = None
    error_code: str | None = None
    validation_context: dict | None = None

    @property
    def is_invalid(self) -> bool:
        """Check if URL validation failed."""
        return not self.is_valid


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


def validate_url_detailed(url: str | None) -> URLValidationResult:
    """
    Validate a URL with detailed result information.

    Args:
        url: The URL to validate

    Returns:
        URLValidationResult with detailed validation information
    """
    if not url:
        return URLValidationResult(
            is_valid=False,
            url=url or "",
            error_type="InvalidURLFormatError",
            error_message="URL is None or empty",
            error_code="URL_EMPTY",
            validation_context={"provided_url": url}
        )

    try:
        _validate_url_internal(url)
        return URLValidationResult(
            is_valid=True,
            url=url,
            validation_context={
                "scheme": urlparse(url).scheme,
                "hostname": urlparse(url).hostname,
                "port": urlparse(url).port
            }
        )
    except InvalidURLFormatError as e:
        return URLValidationResult(
            is_valid=False,
            url=url,
            error_type="InvalidURLFormatError",
            error_message=str(e),
            error_code=getattr(e, 'error_code', 'URL_FORMAT_INVALID'),
            validation_context=getattr(e, 'context', {})
        )
    except UnsupportedSchemeError as e:
        return URLValidationResult(
            is_valid=False,
            url=url,
            error_type="UnsupportedSchemeError",
            error_message=str(e),
            error_code=getattr(e, 'error_code', 'URL_SCHEME_UNSUPPORTED'),
            validation_context=getattr(e, 'context', {})
        )
    except RestrictedNetworkError as e:
        return URLValidationResult(
            is_valid=False,
            url=url,
            error_type="RestrictedNetworkError",
            error_message=str(e),
            error_code=getattr(e, 'error_code', 'URL_NETWORK_RESTRICTED'),
            validation_context=getattr(e, 'context', {})
        )
    except RestrictedPortError as e:
        return URLValidationResult(
            is_valid=False,
            url=url,
            error_type="RestrictedPortError",
            error_message=str(e),
            error_code=getattr(e, 'error_code', 'URL_PORT_RESTRICTED'),
            validation_context=getattr(e, 'context', {})
        )
    except SecurityViolationError as e:
        return URLValidationResult(
            is_valid=False,
            url=url,
            error_type="SecurityViolationError",
            error_message=str(e),
            error_code=getattr(e, 'error_code', 'URL_SECURITY_VIOLATION'),
            validation_context=getattr(e, 'context', {})
        )
    except URLValidationError as e:
        return URLValidationResult(
            is_valid=False,
            url=url,
            error_type="URLValidationError",
            error_message=str(e),
            error_code=getattr(e, 'error_code', 'URL_VALIDATION_FAILED'),
            validation_context=getattr(e, 'context', {})
        )


def _sanitize_and_validate_url_format(url: str) -> str:
    """
    Sanitize URL and detect common bypass techniques.

    Args:
        url: The URL to sanitize

    Returns:
        Sanitized URL

    Raises:
        SecurityViolationError: If bypass techniques are detected
        InvalidURLFormatError: If URL format is invalid
    """
    original_url = url

    # Detect and prevent whitespace bypasses
    if url != url.strip():
        raise SecurityViolationError(
            "URL contains leading or trailing whitespace",
            error_code="URL_WHITESPACE_BYPASS",
            context={"original_url": original_url}
        )

    # Check for control characters and unusual whitespace
    control_chars = ['\t', '\n', '\r', '\f', '\v']
    for char in control_chars:
        if char in url:
            raise SecurityViolationError(
                f"URL contains control character: {char!r}",
                error_code="URL_CONTROL_CHAR",
                context={"original_url": original_url, "control_char": repr(char)}
            )

    # Check for Unicode normalization bypasses
    normalized_url = unicodedata.normalize('NFKD', url)
    if normalized_url != url:
        raise SecurityViolationError(
            "URL contains Unicode characters that normalize differently",
            error_code="URL_UNICODE_BYPASS",
            context={"original_url": original_url, "normalized_url": normalized_url}
        )

    # Detect multiple URL encoding layers
    decoded_once = url
    decode_count = 0
    max_decode_attempts = 3

    while decode_count < max_decode_attempts:
        try:
            decoded_temp = unquote(decoded_once)
            if decoded_temp == decoded_once:
                break  # No more decoding possible
            decoded_once = decoded_temp
            decode_count += 1
        except Exception:
            break

    # If we decoded multiple times, it might be a bypass attempt
    if decode_count > 1:
        raise SecurityViolationError(
            f"URL appears to use multiple encoding layers ({decode_count} levels)",
            error_code="URL_MULTIPLE_ENCODING",
            context={"original_url": original_url, "decode_levels": decode_count, "final_decoded": decoded_once}
        )

    # Perform single decode for further validation
    try:
        decoded_url = unquote(url)
    except Exception as e:
        raise InvalidURLFormatError(
            "URL decoding failed",
            error_code="URL_DECODE_ERROR",
            context={"original_url": original_url, "decode_error": str(e)}
        ) from e

    return decoded_url


def _check_for_security_violations(url: str, original_url: str) -> None:
    """
    Check for various security violations and bypass attempts.

    Args:
        url: The sanitized URL to check
        original_url: The original URL for context

    Raises:
        SecurityViolationError: If security violations are detected
    """
    # Check for HTTP header injection patterns (enhanced)
    injection_patterns = [
        '\n', '\r', '%0a', '%0d', '%20%0a', '%20%0d',
        '\x0a', '\x0d', '\x20\x0a', '\x20\x0d'
    ]

    detected_patterns = []
    for pattern in injection_patterns:
        if pattern in url.lower():
            detected_patterns.append(pattern)

    if detected_patterns:
        raise SecurityViolationError(
            "URL contains HTTP header injection patterns",
            error_code="URL_HEADER_INJECTION",
            context={"original_url": original_url, "detected_patterns": detected_patterns}
        )

    # Check for unusual protocols that might bypass scheme validation
    suspicious_schemes = [
        'file:', 'ftp:', 'gopher:', 'ldap:', 'dict:', 'sftp:', 'tftp:',
        'javascript:', 'data:', 'vbscript:', 'mailto:', 'news:', 'nntp:'
    ]

    url_lower = url.lower()
    for scheme in suspicious_schemes:
        if url_lower.startswith(scheme):
            raise SecurityViolationError(
                f"URL uses suspicious scheme: {scheme}",
                error_code="URL_SUSPICIOUS_SCHEME",
                context={"original_url": original_url, "detected_scheme": scheme}
            )

    # Check for URL fragment manipulation
    if '#' in url:
        fragment_part = url.split('#', 1)[1]
        # Check if fragment contains injection attempts
        if any(char in fragment_part for char in ['\n', '\r', '<', '>', '"', "'"]):
            raise SecurityViolationError(
                "URL fragment contains potentially dangerous characters",
                error_code="URL_FRAGMENT_INJECTION",
                context={"original_url": original_url, "fragment": fragment_part}
            )

    # Check for credential inclusion (username:password@host)
    if '@' in url:
        # Parse to check if @ is part of credentials
        try:
            parsed = urlparse(url)
            if parsed.username or parsed.password:
                raise SecurityViolationError(
                    "URL contains embedded credentials",
                    error_code="URL_EMBEDDED_CREDENTIALS",
                    context={"original_url": original_url}
                )
        except Exception:  # noqa: S110
            # If parsing fails here, it will be caught later
            pass


def _validate_url_internal(url: str | None) -> None:
    """
    Internal URL validation that raises specific exceptions.

    Args:
        url: The URL to validate

    Raises:
        InvalidURLFormatError: If URL format is invalid
        UnsupportedSchemeError: If URL scheme is not supported
        RestrictedNetworkError: If URL targets restricted network
        RestrictedPortError: If URL uses restricted ports
        SecurityViolationError: If URL violates security policies
    """
    if not url:
        raise InvalidURLFormatError(
            "URL is None or empty",
            error_code="URL_EMPTY"
        )

    if not isinstance(url, str):
        raise InvalidURLFormatError(
            "URL must be a string",
            error_code="URL_NOT_STRING",
            context={"url_type": type(url).__name__}
        )

    # Store original URL for context
    original_url = url

    # Perform initial sanitization and bypass detection
    url = _sanitize_and_validate_url_format(url)

    # Prevent resource exhaustion with overly long URLs
    if len(url) > 2048:
        raise InvalidURLFormatError(
            "URL is too long (exceeds 2048 characters)",
            error_code="URL_TOO_LONG",
            context={"url_length": len(url), "original_url": original_url}
        )

    try:
        parsed = urlparse(url)
    except Exception as e:
        raise InvalidURLFormatError(
            "URL cannot be parsed",
            error_code="URL_PARSE_ERROR",
            context={"parse_error": str(e), "original_url": original_url}
        ) from e

    # Enhanced security violation checks
    _check_for_security_violations(url, original_url)

    # Validate scheme first (case-insensitive)
    scheme = parsed.scheme.lower() if parsed.scheme else ""
    if scheme not in ALLOWED_SCHEMES:
        raise UnsupportedSchemeError(
            f"URL scheme '{scheme}' is not supported",
            error_code="URL_SCHEME_UNSUPPORTED",
            context={
                "provided_scheme": scheme,
                "allowed_schemes": list(ALLOWED_SCHEMES)
            }
        )

    # Check for required components after scheme validation
    if not parsed.netloc:
        raise InvalidURLFormatError(
            "URL missing network location (hostname)",
            error_code="URL_MISSING_NETLOC"
        )

    # Extract hostname and port with error handling
    try:
        hostname = parsed.hostname
        port = parsed.port
    except ValueError as e:
        raise InvalidURLFormatError(
            "URL network location is malformed",
            error_code="URL_NETLOC_MALFORMED",
            context={"netloc": parsed.netloc, "parse_error": str(e)}
        ) from e

    if not hostname:
        raise InvalidURLFormatError(
            "URL missing hostname",
            error_code="URL_MISSING_HOSTNAME",
            context={"netloc": parsed.netloc}
        )

    # Check for IP address (including various representations)
    resolved_ip = _resolve_hostname_to_ip(hostname)
    if resolved_ip:
        _validate_ip_address(resolved_ip, hostname)
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

    # Enhanced IPv6 bracket handling
    if hostname.startswith('[') and hostname.endswith(']'):
        try:
            return ipaddress.ip_address(hostname[1:-1])
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
            # Check individual part ranges first
            for part in parts:
                if int(part) > 255:
                    break
            else:
                # Pad with zeros to make it a full IP
                while len(parts) < 4:
                    parts.append('0')
                full_ip = '.'.join(parts)
                return ipaddress.IPv4Address(full_ip)
    except (ValueError, ipaddress.AddressValueError):
        pass

    # Check for mixed hex/decimal formats (e.g., 0x7f.0x1 for 127.0.0.1)
    try:
        if '.' in hostname and any(part.startswith('0x') for part in hostname.split('.')):
            parts = hostname.split('.')
            decimal_parts = []
            for part in parts:
                if part.startswith('0x'):
                    decimal_parts.append(str(int(part, 16)))
                else:
                    decimal_parts.append(part)
            return _resolve_hostname_to_ip('.'.join(decimal_parts))
    except (ValueError, ipaddress.AddressValueError):
        pass

    # Check for IPv6 with embedded IPv4 (e.g., ::ffff:127.0.0.1)
    try:
        if '::' in hostname and '.' in hostname:
            return ipaddress.ip_address(hostname)
    except ValueError:
        pass

    # Check for URL-encoded IP addresses
    try:
        decoded_hostname = unquote(hostname)
        if decoded_hostname != hostname:
            return _resolve_hostname_to_ip(decoded_hostname)
    except Exception:  # noqa: S110
        pass

    return None


def _validate_ip_address(ip_addr: ipaddress.IPv4Address | ipaddress.IPv6Address, hostname: str) -> None:
    """
    Validate that an IP address is not internal/private.

    Args:
        ip_addr: The IP address to validate
        hostname: Original hostname that resolved to this IP

    Raises:
        RestrictedNetworkError: If the IP address is internal/private
    """
    context = {
        "ip_address": str(ip_addr),
        "hostname": hostname,
        "ip_version": ip_addr.version
    }

    # Check for localhost
    if ip_addr.is_loopback:
        raise RestrictedNetworkError(
            f"Localhost/loopback address not allowed: {ip_addr}",
            error_code="URL_LOCALHOST_ACCESS",
            context=context
        )

    # Check for private networks
    if ip_addr.is_private:
        raise RestrictedNetworkError(
            f"Private network address not allowed: {ip_addr}",
            error_code="URL_PRIVATE_NETWORK",
            context=context
        )

    # Check for link-local addresses
    if ip_addr.is_link_local:
        raise RestrictedNetworkError(
            f"Link-local address not allowed: {ip_addr}",
            error_code="URL_LINK_LOCAL",
            context=context
        )

    # Check for multicast addresses
    if ip_addr.is_multicast:
        raise RestrictedNetworkError(
            f"Multicast address not allowed: {ip_addr}",
            error_code="URL_MULTICAST",
            context=context
        )

    # Check for reserved addresses
    if ip_addr.is_reserved:
        raise RestrictedNetworkError(
            f"Reserved address not allowed: {ip_addr}",
            error_code="URL_RESERVED_ADDRESS",
            context=context
        )

    # Additional checks for IPv4
    if isinstance(ip_addr, ipaddress.IPv4Address):
        # Check for broadcast address
        if str(ip_addr) == '255.255.255.255':
            raise RestrictedNetworkError(
                f"Broadcast address not allowed: {ip_addr}",
                error_code="URL_BROADCAST_ADDRESS",
                context=context
            )

        # Check for any address (0.0.0.0) - this is intentionally blocked for security
        if str(ip_addr) == '0.0.0.0':  # noqa: S104
            raise RestrictedNetworkError(
                f"Any address (0.0.0.0) not allowed: {ip_addr}",
                error_code="URL_ANY_ADDRESS",
                context=context
            )

        # Check for additional IPv4 reserved ranges
        reserved_ranges = [
            ipaddress.IPv4Network('224.0.0.0/4'),  # Multicast (Class D)
            ipaddress.IPv4Network('240.0.0.0/4'),  # Reserved (Class E)
            ipaddress.IPv4Network('169.254.0.0/16'),  # Link-local (APIPA)
            ipaddress.IPv4Network('100.64.0.0/10'),  # Carrier-grade NAT
        ]

        for reserved_range in reserved_ranges:
            if ip_addr in reserved_range:
                raise RestrictedNetworkError(
                    f"Address in reserved range {reserved_range} not allowed: {ip_addr}",
                    error_code="URL_RESERVED_RANGE",
                    context={**context, "reserved_range": str(reserved_range)}
                )

    # Additional checks for IPv6
    elif isinstance(ip_addr, ipaddress.IPv6Address):
        # Check for IPv6 loopback (should already be caught by is_loopback, but being explicit)
        if str(ip_addr) == '::1':
            raise RestrictedNetworkError(
                f"IPv6 loopback address not allowed: {ip_addr}",
                error_code="URL_IPV6_LOOPBACK",
                context=context
            )

        # Check for IPv6 unspecified address
        if str(ip_addr) == '::':
            raise RestrictedNetworkError(
                f"IPv6 unspecified address not allowed: {ip_addr}",
                error_code="URL_IPV6_UNSPECIFIED",
                context=context
            )

        # Check for IPv4-mapped IPv6 addresses that might bypass IPv4 restrictions
        if ip_addr.ipv4_mapped:
            ipv4_part = ip_addr.ipv4_mapped
            _validate_ip_address(ipv4_part, hostname)

        # Check for IPv4-compatible IPv6 addresses (deprecated but still possible)
        if str(ip_addr).startswith('::') and '.' in str(ip_addr):
            # Extract the IPv4 part and validate it
            ipv4_part_str = str(ip_addr).split('::')[1]
            if '.' in ipv4_part_str:
                try:
                    ipv4_part = ipaddress.IPv4Address(ipv4_part_str)
                    _validate_ip_address(ipv4_part, hostname)
                except ValueError:
                    pass

        # Check for site-local addresses (deprecated but might be used)
        if str(ip_addr).startswith('fec0:') or str(ip_addr).startswith('FEC0:'):
            raise RestrictedNetworkError(
                f"IPv6 site-local address not allowed: {ip_addr}",
                error_code="URL_IPV6_SITE_LOCAL",
                context=context
            )

        # Check for unique local addresses (RFC 4193)
        if str(ip_addr).startswith('fc') or str(ip_addr).startswith('fd'):
            raise RestrictedNetworkError(
                f"IPv6 unique local address not allowed: {ip_addr}",
                error_code="URL_IPV6_UNIQUE_LOCAL",
                context=context
            )


def _validate_hostname(hostname: str) -> None:
    """
    Validate hostname to prevent common SSRF bypasses.

    Args:
        hostname: The hostname to validate

    Raises:
        RestrictedNetworkError: If the hostname poses a security risk
    """
    hostname_lower = hostname.lower()
    context = {"hostname": hostname, "hostname_lower": hostname_lower}

    # Enhanced localhost variations - these are intentionally blocked for security
    localhost_variations = [
        'localhost',
        'localhost.localdomain',
        '0', '0.0', '0.0.0', '0.0.0.0',  # noqa: S104
        'localtest.me',  # Common test domain that resolves to localhost
        '127.0.0.1.nip.io',  # Wildcard DNS service
        '127.0.0.1.xip.io',  # Another wildcard DNS service
        'vcap.me',  # Cloud Foundry test domain
        '127.0.0.1.sslip.io'  # SSL IP service
    ]

    if hostname_lower in localhost_variations:
        raise RestrictedNetworkError(
            f"Localhost hostname not allowed: {hostname}",
            error_code="URL_LOCALHOST_HOSTNAME",
            context={**context, "detected_variation": hostname_lower}
        )

    # Enhanced internal hostnames list
    internal_hostnames = [
        'metadata.google.internal',
        '169.254.169.254',  # AWS/GCP metadata service
        'metadata',
        'consul',
        'vault',
        'instance-data',  # AWS instance metadata
        'metadata.packet.net',  # Packet metadata
        'metadata.digitalocean.com',  # DigitalOcean metadata
        'metadata.azure.com',  # Azure metadata
        'kubernetes.default.svc.cluster.local',  # Kubernetes API
        'docker.for.mac.localhost',  # Docker Desktop
        'docker.for.windows.localhost',  # Docker Desktop
        'host.docker.internal'  # Docker internal
    ]

    if hostname_lower in internal_hostnames:
        raise RestrictedNetworkError(
            f"Internal service hostname not allowed: {hostname}",
            error_code="URL_INTERNAL_HOSTNAME",
            context={**context, "detected_hostname": hostname_lower}
        )

    # Check for wildcard DNS bypass attempts
    wildcard_patterns = [
        r'.*\.nip\.io$',
        r'.*\.xip\.io$',
        r'.*\.sslip\.io$',
        r'.*\.localtest\.me$',
        r'.*\.vcap\.me$',
        r'127\.0\.0\.1\..*',
        r'localhost\..*',
        r'.*\.127\.0\.0\.1\..*'
    ]

    for pattern in wildcard_patterns:
        if re.match(pattern, hostname_lower):
            raise RestrictedNetworkError(
                f"Wildcard DNS bypass attempt detected: {hostname}",
                error_code="URL_WILDCARD_DNS_BYPASS",
                context={**context, "pattern": pattern}
            )

    # Check for homograph attacks (similar looking characters)
    suspicious_chars = ['а', 'е', 'о', 'р', 'с', 'х', 'у']  # Cyrillic lookalikes  # noqa: RUF001
    if any(char in hostname_lower for char in suspicious_chars):
        raise RestrictedNetworkError(
            f"Hostname contains suspicious characters (possible homograph attack): {hostname}",
            error_code="URL_HOMOGRAPH_ATTACK",
            context={**context, "suspicious_chars": [c for c in suspicious_chars if c in hostname_lower]}
        )

    # Check for excessive subdomain depth (potential DNS rebinding)
    subdomain_parts = hostname_lower.split('.')
    if len(subdomain_parts) > 10:
        raise RestrictedNetworkError(
            f"Hostname has excessive subdomain depth ({len(subdomain_parts)} levels): {hostname}",
            error_code="URL_EXCESSIVE_SUBDOMAINS",
            context={**context, "subdomain_count": len(subdomain_parts)}
        )

    # Check for numeric-only hostnames that might be IP addresses in disguise
    if hostname.replace('.', '').replace('-', '').isdigit():
        raise RestrictedNetworkError(
            f"Hostname appears to be numeric (possible IP bypass): {hostname}",
            error_code="URL_NUMERIC_HOSTNAME",
            context=context
        )


def _validate_port(port: int) -> None:
    """
    Validate that a port is not commonly used for internal services.

    Args:
        port: The port number to validate

    Raises:
        RestrictedPortError: If the port is commonly used for internal services
        InvalidURLFormatError: If the port is in invalid range
    """
    context = {"port": port}

    # Block invalid port ranges first
    if port > 65535 or port < 1:
        raise InvalidURLFormatError(
            f"Port {port} is invalid (must be 1-65535)",
            error_code="URL_PORT_INVALID_RANGE",
            context=context
        )

    # Check if port is explicitly blocked
    if port in BLOCKED_PORTS:
        raise RestrictedPortError(
            f"Port {port} is restricted (commonly used for internal services)",
            error_code="URL_PORT_BLOCKED",
            context={**context, "blocked_ports": list(BLOCKED_PORTS)}
        )

    # Block ports below 1024 except for allowed web ports
    if port < 1024 and port not in ALLOWED_PORTS:
        raise RestrictedPortError(
            f"Port {port} is restricted (privileged port)",
            error_code="URL_PORT_PRIVILEGED",
            context={**context, "allowed_ports": list(ALLOWED_PORTS)}
        )
