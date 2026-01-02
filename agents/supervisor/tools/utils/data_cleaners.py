"""Data cleaning and validation utilities."""

import re
from typing import Optional, List


def clean_year_value(value) -> Optional[str]:
    """
    Clean and validate year values.
    
    Args:
        value: Raw year value (string, int, or other)
        
    Returns:
        Cleaned 4-digit year string or None if invalid
    """
    if value is None:
        return None
    
    # Handle different year formats
    year_str = str(value).strip()
    
    # Extract 4-digit year
    year_match = re.search(r'\b(19|20)\d{2}\b', year_str)
    if year_match:
        year = year_match.group(0)
        # Validate reasonable range for catastrophe events
        if validate_year_range(int(year)):
            return year
    
    return None


def clean_text_value(value, max_length: int = 500) -> Optional[str]:
    """
    Clean and validate text values.
    
    Args:
        value: Raw text value
        max_length: Maximum allowed length
        
    Returns:
        Cleaned text or None if invalid
    """
    if value is None:
        return None
    
    text = str(value).strip()
    
    # Remove excessive whitespace
    text = re.sub(r'\s+', ' ', text)
    
    # Return None for empty or very short text
    if len(text) < 2:
        return None
    
    return text[:max_length]


def clean_numeric_value(value) -> Optional[float]:
    """
    Clean and validate numeric values.
    
    Args:
        value: Raw numeric value (string, int, float, or other)
        
    Returns:
        Cleaned float value or None if invalid
    """
    if value is None:
        return None
    
    # Handle numeric types directly
    if isinstance(value, (int, float)):
        return float(value) if value > 0 else None
    
    # Handle string representations
    value_str = str(value).strip()
    
    # Remove common formatting characters
    cleaned = re.sub(r'[,$\s]', '', value_str)
    
    # Try to parse as float
    try:
        numeric_value = float(cleaned)
        return numeric_value if numeric_value > 0 else None
    except (ValueError, TypeError):
        return None


def validate_year_range(year: int, min_year: int = 1990, max_year: int = 2030) -> bool:
    """
    Validate that a year is within a reasonable range.
    
    Args:
        year: Year to validate
        min_year: Minimum valid year
        max_year: Maximum valid year
        
    Returns:
        True if year is valid
    """
    return min_year <= year <= max_year


def validate_numeric_positive(value: float) -> bool:
    """
    Validate that a numeric value is positive.
    
    Args:
        value: Numeric value to validate
        
    Returns:
        True if value is positive
    """
    return value > 0


def validate_year_format(year_value: str) -> bool:
    """
    Validate that a year value is a 4-digit string.
    
    Args:
        year_value: Year value to validate
        
    Returns:
        True if year is a valid 4-digit format
    """
    if not year_value:
        return False
    year_str = str(year_value).strip()
    return year_str.isdigit() and len(year_str) == 4


def validate_description_length(description: str, min_length: int = 3) -> bool:
    """
    Validate that a description meets minimum length requirements.
    
    Args:
        description: Description text to validate
        min_length: Minimum required length
        
    Returns:
        True if description meets length requirement
    """
    if not description:
        return False
    return len(str(description).strip()) >= min_length
