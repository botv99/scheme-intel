"""
Custom exceptions for scheme-intel.
"""


class SchemeIntelException(Exception):
    """Base exception for scheme-intel."""
    pass


class SourceAccessError(SchemeIntelException):
    """Raised when a source cannot be accessed."""
    pass


class DataParseError(SchemeIntelException):
    """Raised when data parsing fails."""
    pass


class ConfigurationError(SchemeIntelException):
    """Raised when configuration is invalid."""
    pass


class TelegramError(SchemeIntelException):
    """Raised when Telegram notification fails."""
    pass


class DatabaseError(SchemeIntelException):
    """Raised when database operations fail."""
    pass
