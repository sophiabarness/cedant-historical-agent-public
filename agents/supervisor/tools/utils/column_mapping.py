"""Column mapping and header detection utilities."""

from typing import Optional, Dict, List, Tuple, Set


def find_header_row(
    worksheet,
    expected_columns: Dict[str, List[str]],
    max_search_rows: int = 10,
    min_required_fields: int = 2
) -> Tuple[Optional[int], Dict[str, int]]:
    """
    Find header row and create column mappings in an Excel worksheet.
    
    Args:
        worksheet: Excel worksheet object
        expected_columns: Dict mapping field names to list of possible column names
        max_search_rows: Maximum number of rows to search for headers
        min_required_fields: Minimum number of fields that must be found
        
    Returns:
        Tuple of (header_row_number, column_mappings_dict)
    """
    max_row = worksheet.max_row or 0
    max_col = worksheet.max_column or 0
    
    # Search first N rows for headers
    for row_num in range(1, min(max_search_rows + 1, max_row + 1)):
        headers = []
        for col_num in range(1, min(21, max_col + 1)):
            cell = worksheet.cell(row=row_num, column=col_num)
            header_text = str(cell.value).strip().lower() if cell.value else ""
            headers.append((col_num, header_text))
        
        # Create column mappings for this row
        column_mappings = create_column_mapping(headers, expected_columns)
        
        # Check if we found enough required fields
        if len(column_mappings) >= min_required_fields:
            return row_num, column_mappings
    
    return None, {}


def create_column_mapping(
    headers: List[Tuple[int, str]],
    expected_columns: Dict[str, List[str]],
    min_match_score: int = 60
) -> Dict[str, int]:
    """
    Create column mappings from headers and expected column names.
    
    Args:
        headers: List of (column_number, header_text) tuples
        expected_columns: Dict mapping field names to list of possible column names
        min_match_score: Minimum score required for a match (0-100)
        
    Returns:
        Dictionary mapping field names to column numbers
    """
    column_mappings = {}
    used_columns: Set[int] = set()
    
    for field, expected_names in expected_columns.items():
        best_match_col = None
        best_match_score = 0
        
        for col_num, header_text in headers:
            if not header_text or col_num in used_columns:
                continue
            
            for expected_name in expected_names:
                score = calculate_match_score(expected_name, header_text)
                
                if score > best_match_score and score >= min_match_score:
                    best_match_score = score
                    best_match_col = col_num
        
        if best_match_col:
            column_mappings[field] = best_match_col
            used_columns.add(best_match_col)
    
    return column_mappings


def calculate_match_score(expected: str, actual: str) -> int:
    """
    Calculate match score between expected and actual column names.
    
    Args:
        expected: Expected column name (normalized)
        actual: Actual column name from file (normalized)
        
    Returns:
        Match score (0-100)
    """
    # Exact match
    if expected == actual:
        return 100
    
    # Substring match
    if expected in actual or actual in expected:
        return 80
    
    # Word-based matching
    expected_words = set(expected.split())
    actual_words = set(actual.split())
    if expected_words & actual_words:
        return 60
    
    return 0


def map_column_names(
    fieldnames: List[str],
    expected_mappings: Dict[str, List[str]]
) -> Dict[str, str]:
    """
    Map CSV column names to expected field names.
    
    Args:
        fieldnames: List of actual column names from CSV
        expected_mappings: Dict mapping expected field names to possible variations
        
    Returns:
        Dictionary mapping expected field names to actual column names
    """
    column_mapping = {}
    
    for expected_field, possible_names in expected_mappings.items():
        for fieldname in fieldnames:
            fieldname_normalized = fieldname.lower().replace(' ', '').replace('_', '')
            
            for possible_name in possible_names:
                possible_normalized = possible_name.lower().replace(' ', '').replace('_', '')
                
                if fieldname_normalized == possible_normalized:
                    column_mapping[expected_field] = fieldname
                    break
            
            if expected_field in column_mapping:
                break
    
    return column_mapping


def validate_required_columns(
    column_mapping: Dict[str, any],
    required_fields: List[str]
) -> Tuple[bool, List[str]]:
    """
    Validate that all required columns are present in the mapping.
    
    Args:
        column_mapping: Dictionary of field mappings
        required_fields: List of required field names
        
    Returns:
        Tuple of (is_valid, list_of_missing_fields)
    """
    missing_fields = [field for field in required_fields if field not in column_mapping]
    return len(missing_fields) == 0, missing_fields
