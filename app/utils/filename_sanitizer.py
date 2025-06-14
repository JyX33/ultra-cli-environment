# ABOUTME: Filename sanitization utility to prevent path traversal attacks and ensure filesystem safety
# ABOUTME: Removes dangerous characters, enforces length limits, and handles reserved names

import re
import unicodedata
from pathlib import Path
from typing import Optional


class FilenameSecurityError(Exception):
    """Raised when a filename cannot be safely sanitized."""
    pass


# Configuration for filename sanitization
MAX_FILENAME_LENGTH = 255
DANGEROUS_CHARS = r'[<>:"|*?\\\/]'
CONTROL_CHARS = r'[\x00-\x1f\x7f]'
WINDOWS_RESERVED_NAMES = {
    'con', 'prn', 'aux', 'nul',
    'com1', 'com2', 'com3', 'com4', 'com5', 'com6', 'com7', 'com8', 'com9',
    'lpt1', 'lpt2', 'lpt3', 'lpt4', 'lpt5', 'lpt6', 'lpt7', 'lpt8', 'lpt9'
}


def sanitize_filename(filename: Optional[str], max_length: int = MAX_FILENAME_LENGTH) -> str:
    """
    Sanitize a filename to prevent security vulnerabilities and ensure filesystem compatibility.
    
    This function removes or replaces dangerous characters, prevents path traversal attacks,
    enforces length limits, and handles operating system reserved names.
    
    Args:
        filename: The filename to sanitize
        max_length: Maximum allowed filename length (default: 255)
        
    Returns:
        A sanitized filename that is safe for filesystem use
        
    Raises:
        FilenameSecurityError: If the filename cannot be safely sanitized
    """
    if filename is None:
        raise FilenameSecurityError("Invalid filename: None provided")
    
    if not isinstance(filename, str):
        raise FilenameSecurityError("Invalid filename: must be a string")
    
    # Start with the original filename
    sanitized = filename.strip()
    
    # Handle empty or whitespace-only filenames
    if not sanitized:
        raise FilenameSecurityError("Invalid filename: empty or whitespace only")
    
    # Remove path traversal sequences
    sanitized = _remove_path_traversal(sanitized)
    
    # Remove dangerous characters
    sanitized = _remove_dangerous_characters(sanitized)
    
    # Remove control characters and null bytes
    sanitized = _remove_control_characters(sanitized)
    
    # Handle unicode normalization
    sanitized = _normalize_unicode(sanitized)
    
    # Handle reserved names
    sanitized = _handle_reserved_names(sanitized)
    
    # Enforce length limits
    sanitized = _enforce_length_limits(sanitized, max_length)
    
    # Final validation
    if not sanitized or sanitized in ('.', '..'):
        raise FilenameSecurityError("Invalid filename: results in empty or dangerous name")
    
    return sanitized


def _remove_path_traversal(filename: str) -> str:
    """Remove path traversal sequences from filename."""
    # Remove all instances of .. and path separators
    sanitized = filename
    
    # Remove various path traversal patterns
    traversal_patterns = [
        r'\.\.+',   # Multiple dots
        r'\.\./',   # Unix path traversal
        r'\.\.\/', # Unix path traversal (escaped)
        r'\.\.\\',  # Windows path traversal
        r'\.\.\\\\', # Windows path traversal (escaped)
        r'/',       # Forward slashes
        r'\\',      # Backslashes
    ]
    
    for pattern in traversal_patterns:
        sanitized = re.sub(pattern, '', sanitized)
    
    return sanitized


def _remove_dangerous_characters(filename: str) -> str:
    """Remove characters that could be dangerous in filenames."""
    # Remove dangerous characters
    sanitized = re.sub(DANGEROUS_CHARS, '', filename)
    
    # Remove other potentially dangerous characters (but keep hyphens which are safe)
    dangerous_extras = r"[|;&$`(){}[\]!#%^+=~'\"]+|--+"
    sanitized = re.sub(dangerous_extras, '', sanitized)
    
    return sanitized


def _remove_control_characters(filename: str) -> str:
    """Remove control characters and null bytes."""
    # Remove control characters (0x00-0x1F and 0x7F)
    sanitized = re.sub(CONTROL_CHARS, '', filename)
    
    # Remove any remaining non-printable characters
    sanitized = ''.join(char for char in sanitized if char.isprintable())
    
    return sanitized


def _normalize_unicode(filename: str) -> str:
    """Normalize unicode characters for filesystem compatibility."""
    try:
        # Normalize unicode to NFC form
        normalized = unicodedata.normalize('NFC', filename)
        
        # Optionally convert to ASCII if needed for compatibility
        # For now, we'll keep unicode but normalize it
        return normalized
    except Exception:
        # If unicode normalization fails, try to encode/decode as ASCII
        try:
            return filename.encode('ascii', 'ignore').decode('ascii')
        except Exception:
            # Last resort: remove non-ASCII characters
            return ''.join(char for char in filename if ord(char) < 128)


def _handle_reserved_names(filename: str) -> str:
    """Handle Windows reserved names and other problematic names."""
    # Split filename and extension
    path_obj = Path(filename)
    name = path_obj.stem
    extension = path_obj.suffix
    
    # Check for reserved names in any part of the filename
    # Split by underscores to check individual components
    name_parts = name.split('_')
    
    for i, part in enumerate(name_parts):
        if part.lower() in WINDOWS_RESERVED_NAMES:
            # Add a prefix to make it safe
            name_parts[i] = f"safe_{part}"
    
    # Reconstruct the name
    name = '_'.join(name_parts)
    
    # Handle names that start with dots (hidden files on Unix)
    if name.startswith('.'):
        name = f"file{name}"
    
    # Reconstruct filename
    if extension:
        return f"{name}{extension}"
    else:
        return name


def _enforce_length_limits(filename: str, max_length: int) -> str:
    """Enforce filename length limits while preserving extension."""
    if len(filename) <= max_length:
        return filename
    
    # Split filename and extension
    path_obj = Path(filename)
    name = path_obj.stem
    extension = path_obj.suffix
    
    # Calculate how much space we have for the name
    available_length = max_length - len(extension)
    
    if available_length <= 0:
        # Extension is too long, truncate it too
        extension = extension[:max_length//2]
        available_length = max_length - len(extension)
    
    # Truncate the name to fit
    if available_length > 0:
        name = name[:available_length]
    else:
        name = "file"  # Fallback name
    
    return f"{name}{extension}"


def generate_safe_filename(subreddit: str, topic: str, extension: str = ".md") -> str:
    """
    Generate a safe filename for reports based on subreddit and topic.
    
    Args:
        subreddit: The subreddit name
        topic: The topic name  
        extension: File extension (default: .md)
        
    Returns:
        A sanitized filename safe for filesystem use
    """
    # Create the base filename
    topic_safe = topic.replace(' ', '_')
    base_filename = f"reddit_report_{subreddit}_{topic_safe}{extension}"
    
    # Sanitize the entire filename
    return sanitize_filename(base_filename)