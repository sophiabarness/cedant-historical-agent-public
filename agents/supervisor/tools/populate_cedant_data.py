"""Synchronous submission pack processing tools for use within Temporal workflows."""

import csv
import re
import time
from pathlib import Path
from typing import Dict, Any, List, Optional

from models.submission_pack import CatastropheEvent
from agents.supervisor.tools.utils.data_cleaners import clean_year_value, clean_text_value, clean_numeric_value
from shared.config import get_historical_db_path, get_cedant_data_path
import pandas as pd
from fuzzywuzzy import fuzz, process


def extract_pcs_code(event_name: str) -> Optional[str]:
    """
    Extract PCS code from event name using various patterns.
    
    Args:
        event_name: Event name that may contain a PCS code
        
    Returns:
        PCS code as string if found, None otherwise
        
    Examples:
        "Hurricane Ian PCS 2267" -> "2267"
        "HURR NICOLE (PCS2234)" -> "2234"
        "Ian 2267" -> "2267"
        "PCS 1717 Hurricane Irma" -> "1717"
    """
    if not event_name:
        return None
    
    # Convert to string and clean
    name = str(event_name).strip()
    
    # Pattern 1: "PCS 1234" or "PCS1234"
    pcs_match = re.search(r'PCS\s*(\d{4})', name, re.IGNORECASE)
    if pcs_match:
        return pcs_match.group(1)
    
    # Pattern 2: "(PCS1234)" or "(PCS 1234)"
    pcs_paren_match = re.search(r'\(PCS\s*(\d{4})\)', name, re.IGNORECASE)
    if pcs_paren_match:
        return pcs_paren_match.group(1)
    
    # Pattern 3: Standalone 4-digit number (be more careful here)
    # Only match if it's clearly separated and looks like a PCS code
    standalone_match = re.search(r'\b(\d{4})\b', name)
    if standalone_match:
        code = standalone_match.group(1)
        # Basic validation: PCS codes are typically in certain ranges
        # Most PCS codes are between 1000-9999
        if 1000 <= int(code) <= 9999:
            return code
    
    return None


def match_by_pcs_code(
    submission_event: Dict[str, Any], 
    historical_events: List[Dict[str, Any]]
) -> Optional[Dict[str, Any]]:
    """
    Match events based on PCS code with high confidence (0.95).
    
    Args:
        submission_event: Single event data from submission pack
        historical_events: List of historical events to match against
        
    Returns:
        Match result dictionary if PCS match found, None otherwise
    """
    # Extract PCS code from submission event
    submission_description = submission_event.get("loss_description", "")
    submission_pcs = extract_pcs_code(submission_description)
    
    if not submission_pcs:
        return None
    
    # Search for matching PCS code in historical events
    for hist_event in historical_events:
        # Check multiple fields for PCS codes
        hist_event_name = hist_event.get("EventName", "")
        hist_pcs_field = hist_event.get("PCSID", "")  # Use actual PCSID field from database
        hist_event_id = hist_event.get("HistoricalEventID", "")
        
        # Extract PCS from event name
        hist_pcs_from_name = extract_pcs_code(hist_event_name)
        
        # Extract PCS from dedicated PCSID field
        hist_pcs_from_field = extract_pcs_code(str(hist_pcs_field)) if hist_pcs_field else None
        
        # Also check if PCSID field contains the PCS code directly (as string or number)
        hist_pcs_direct = None
        if hist_pcs_field and str(hist_pcs_field).strip() and str(hist_pcs_field).strip() != 'None':
            pcs_str = str(hist_pcs_field).strip()
            if pcs_str.isdigit() and len(pcs_str) == 4:
                hist_pcs_direct = pcs_str
        
        # Check for exact PCS code match
        matched_pcs = None
        match_source = None
        
        if submission_pcs == hist_pcs_from_name:
            matched_pcs = hist_pcs_from_name
            match_source = "event_name"
        elif submission_pcs == hist_pcs_from_field:
            matched_pcs = hist_pcs_from_field
            match_source = "pcsid_field_extracted"
        elif submission_pcs == hist_pcs_direct:
            matched_pcs = hist_pcs_direct
            match_source = "pcsid_field_direct"
        
        if matched_pcs:
            # High confidence match found
            return {
                "success": True,
                "message": f"Found high-confidence PCS code match: {matched_pcs}",
                "hist_event_id": str(hist_event_id),
                "match_confidence": "high",
                "confidence_score": 0.95,
                "potential_matches": [{
                    "hist_event_id": str(hist_event_id),
                    "event_name": hist_event_name,
                    "year": hist_event.get("year", hist_event.get("EventDate", "")[:4] if hist_event.get("EventDate") else ""),
                    "pcs_code": matched_pcs,
                    "confidence_score": 95,
                    "match_reasons": [f"Exact PCS code match: {matched_pcs} (from {match_source})"]
                }],
                "event_description": submission_description,
                "match_type": "pcs_code"
            }
    
    return None


def normalize_event_name(event_name: str) -> str:
    """
    Normalize event name for consistent fuzzy matching.
    
    Args:
        event_name: Raw event name from submission or historical data
        
    Returns:
        Normalized event name for comparison
    """
    if not event_name:
        return ""
    
    # Convert to lowercase and strip whitespace
    normalized = str(event_name).lower().strip()
    
    # Remove common prefixes and suffixes
    normalized = re.sub(r'^(hurricane|hurr|tropical storm|ts)\s+', '', normalized)
    normalized = re.sub(r'\s+(hurricane|hurr)$', '', normalized)
    
    # Remove PCS codes and parenthetical information
    normalized = re.sub(r'\(.*?\)', '', normalized)
    normalized = re.sub(r'pcs\s*\d+', '', normalized)
    
    # Remove extra whitespace and punctuation
    normalized = re.sub(r'[^\w\s]', ' ', normalized)
    normalized = re.sub(r'\s+', ' ', normalized).strip()
    
    return normalized


def extract_hurricane_name(event_name: str) -> Optional[str]:
    """
    Extract hurricane name from various event name formats.
    
    Args:
        event_name: Event name that may contain a hurricane name
        
    Returns:
        Hurricane name if found, None otherwise
    """
    if not event_name:
        return None
    
    name = str(event_name).lower().strip()
    
    # Pattern 1: "Hurricane Nicole" or "HURR NICOLE" or "Tropical Storm Nicole"
    hurricane_match = re.search(r'(?:hurricane|hurr|tropical\s+storm|ts)\s+([a-z]+)', name)
    if hurricane_match:
        return hurricane_match.group(1).title()
    
    # Pattern 2: Extract standalone names if there are hurricane-related keywords OR if it's a simple name
    has_hurricane_keywords = any(keyword in name for keyword in ['hurricane', 'hurr', 'tropical', 'storm'])
    
    words = name.split()
    for word in words:
        # Skip common non-hurricane words
        if word in ['pcs', 'hurricane', 'hurr', 'tropical', 'storm', 'cat', 'category', 'some', 'random', 'text', 'earthquake', 'california']:
            continue
        # Skip numbers and codes
        if word.isdigit() or len(word) < 3:
            continue
        # Skip parenthetical content
        if word.startswith('(') or word.endswith(')'):
            continue
        
        # If it's a reasonable length and alphabetic
        if 3 <= len(word) <= 10 and word.isalpha():
            # If we have hurricane keywords, or if it's a standalone proper-looking name
            if has_hurricane_keywords or (len(words) <= 3):
                return word.title()
    
    return None


def match_by_name_similarity(
    submission_event: Dict[str, Any], 
    historical_events: List[Dict[str, Any]],
    similarity_threshold: float = 0.8
) -> Optional[Dict[str, Any]]:
    """
    Match events based on fuzzy name similarity for events without PCS codes.
    Uses token-based matching to handle variations like "Hurricane Nicole" vs "HURR NICOLE".
    
    Args:
        submission_event: Single event data from submission pack
        historical_events: List of historical events to match against
        similarity_threshold: Minimum similarity score (0.0-1.0) for matches
        
    Returns:
        Match result dictionary if similarity match found, None otherwise
    """
    submission_description = submission_event.get("loss_description", "")
    if not submission_description:
        return None
    
    # Normalize submission event name
    submission_normalized = normalize_event_name(submission_description)
    submission_hurricane = extract_hurricane_name(submission_description)
    
    if not submission_normalized and not submission_hurricane:
        return None
    
    best_matches = []
    
    # Search through historical events
    for hist_event in historical_events:
        hist_event_name = hist_event.get("EventName", "")
        if not hist_event_name:
            continue
        
        # Normalize historical event name
        hist_normalized = normalize_event_name(hist_event_name)
        hist_hurricane = extract_hurricane_name(hist_event_name)
        
        # Calculate different types of similarity scores
        scores = []
        match_reasons = []
        
        # 1. Full name token-based similarity
        if submission_normalized and hist_normalized:
            token_score = fuzz.token_set_ratio(submission_normalized, hist_normalized) / 100.0
            if token_score >= similarity_threshold:
                scores.append(token_score)
                match_reasons.append(f"Token similarity: {token_score:.2f}")
        
        # 2. Hurricane name exact match (high bonus)
        if submission_hurricane and hist_hurricane:
            if submission_hurricane.lower() == hist_hurricane.lower():
                scores.append(0.95)  # High confidence for exact hurricane name match
                match_reasons.append(f"Hurricane name match: {submission_hurricane}")
            else:
                # Fuzzy match on hurricane names
                name_score = fuzz.ratio(submission_hurricane.lower(), hist_hurricane.lower()) / 100.0
                if name_score >= 0.85:  # Slightly lower threshold for hurricane names
                    scores.append(name_score)
                    match_reasons.append(f"Hurricane name similarity: {name_score:.2f}")
        
        # 3. Partial ratio for substring matches
        if submission_normalized and hist_normalized:
            partial_score = fuzz.partial_ratio(submission_normalized, hist_normalized) / 100.0
            if partial_score >= similarity_threshold:
                scores.append(partial_score * 0.9)  # Slightly lower weight for partial matches
                match_reasons.append(f"Partial match: {partial_score:.2f}")
        
        # Take the best score for this historical event
        if scores:
            best_score = max(scores)
            
            # Add year proximity bonus if available
            submission_year = submission_event.get("loss_year")
            hist_year = hist_event.get("year") or (hist_event.get("EventDate", "")[:4] if hist_event.get("EventDate") else None)
            
            if submission_year and hist_year:
                try:
                    year_diff = abs(int(submission_year) - int(hist_year))
                    if year_diff == 0:
                        best_score = min(1.0, best_score + 0.05)  # Same year bonus
                        match_reasons.append(f"Same year: {hist_year}")
                    elif year_diff <= 2:
                        best_score = min(1.0, best_score + 0.02)  # Close year bonus
                        match_reasons.append(f"Close year: {hist_year}")
                except (ValueError, TypeError):
                    pass
            
            best_matches.append({
                "hist_event": hist_event,
                "score": best_score,
                "reasons": match_reasons
            })
    
    # Sort by score and return the best match if it meets threshold
    if best_matches:
        best_matches.sort(key=lambda x: x["score"], reverse=True)
        best_match = best_matches[0]
        
        if best_match["score"] >= similarity_threshold:
            hist_event = best_match["hist_event"]
            confidence_score = best_match["score"]
            
            # Determine confidence level
            if confidence_score >= 0.9:
                confidence_level = "high"
            elif confidence_score >= 0.8:
                confidence_level = "medium"
            else:
                confidence_level = "low"
            
            return {
                "success": True,
                "message": f"Found fuzzy name match with {confidence_score:.2f} similarity",
                "hist_event_id": str(hist_event.get("HistoricalEventID", "")),
                "match_confidence": confidence_level,
                "confidence_score": confidence_score,
                "potential_matches": [{
                    "hist_event_id": str(hist_event.get("HistoricalEventID", "")),
                    "event_name": hist_event.get("EventName", ""),
                    "year": hist_event.get("year", hist_event.get("EventDate", "")[:4] if hist_event.get("EventDate") else ""),
                    "pcs_code": hist_event.get("PCSID", ""),
                    "confidence_score": int(confidence_score * 100),
                    "match_reasons": best_match["reasons"]
                }] + [
                    {
                        "hist_event_id": str(match["hist_event"].get("HistoricalEventID", "")),
                        "event_name": match["hist_event"].get("EventName", ""),
                        "year": match["hist_event"].get("year", match["hist_event"].get("EventDate", "")[:4] if match["hist_event"].get("EventDate") else ""),
                        "pcs_code": match["hist_event"].get("PCSID", ""),
                        "confidence_score": int(match["score"] * 100),
                        "match_reasons": match["reasons"]
                    }
                    for match in best_matches[1:5]  # Include up to 4 additional matches
                    if match["score"] >= 0.7  # Only include reasonable alternatives
                ],
                "event_description": submission_description,
                "match_type": "fuzzy_name"
            }
    
    return None


def load_historical_database(historical_db_path: str = None) -> List[Dict[str, Any]]:
    """
    Load historical events from database file (Excel or CSV).
    
    Args:
        historical_db_path: Path to the Historical Event DB file (.xlsx or .csv).
                          If None, uses the configured DATA_DIR path.
        
    Returns:
        List of dictionaries containing historical event data
        
    Raises:
        FileNotFoundError: If the database file doesn't exist
        Exception: For other file reading or parsing errors
    """
    if historical_db_path is None:
        historical_db_path = get_historical_db_path()
    
    start_time = time.time()
    
    # Convert to absolute path if it's relative
    db_path = Path(historical_db_path)
    
    if not db_path.is_absolute():
        # Get the project root (go up from agents/supervisor/tools/)
        project_root = Path(__file__).parent.parent.parent.parent
        db_path = project_root / db_path
    
    # Try CSV first (faster), then fall back to Excel
    csv_path = db_path.with_suffix('.csv')
    
    if csv_path.exists():
        file_to_read = csv_path
        use_csv = True
    elif db_path.exists():
        file_to_read = db_path
        use_csv = False
    else:
        # Provide detailed error message with path information for debugging
        error_msg = (
            f"Historical database file not found. "
            f"Searched for: {csv_path} (exists: {csv_path.exists()}) "
            f"and {db_path} (exists: {db_path.exists()}). "
            f"Original path: {historical_db_path}. "
            f"Current working directory: {Path.cwd()}. "
            f"Project root: {Path(__file__).parent.parent}"
        )
        raise FileNotFoundError(error_msg)
    
    # Cache disabled for debugging - load fresh every time
    try:
        # Read with pandas (much faster than openpyxl)
        if use_csv:
            print(f"[LOAD] Reading CSV file: {file_to_read}")
            df = pd.read_csv(file_to_read)
            print(f"[LOAD] CSV loaded: {len(df)} rows, columns: {list(df.columns)[:5]}")
        else:
            print(f"[LOAD] Reading Excel file: {file_to_read}")
            df = pd.read_excel(file_to_read, engine='openpyxl')
            print(f"[LOAD] Excel loaded: {len(df)} rows")
        
        # Convert to list of dictionaries
        events = []
        for idx, row in df.iterrows():
            # Convert row to dictionary and clean values
            row_data = {}
            has_data = False
            
            for col_name, value in row.items():
                # Handle NaN values
                if pd.isna(value):
                    row_data[col_name] = None
                else:
                    # Convert to string and clean
                    if isinstance(value, pd.Timestamp):
                        row_data[col_name] = value.strftime("%Y-%m-%d")
                    else:
                        cleaned_value = str(value).strip()
                        row_data[col_name] = cleaned_value if cleaned_value != 'nan' else None
                        if cleaned_value and cleaned_value != 'nan':
                            has_data = True
            
            # Only add rows that have valid data
            if has_data and row_data.get('HistoricalEventID'):
                # Add derived fields for easier matching
                event_name = row_data.get('EventName', '')
                if event_name:
                    row_data['normalized_name'] = event_name.lower().strip()
                    
                    # Extract hurricane name if it's a hurricane
                    hurricane_match = re.search(r'(?:hurricane\s+)?(\w+)(?:\s*,|\s*$)', event_name.lower())
                    if hurricane_match:
                        row_data['hurricane_name'] = hurricane_match.group(1).upper()
                
                # Add year from event name or date
                year_match = re.search(r'\b(19|20)\d{2}\b', event_name)
                if year_match:
                    row_data['year'] = year_match.group(0)
                elif row_data.get('EventDate'):
                    try:
                        row_data['year'] = row_data['EventDate'][:4]
                    except:
                        pass
                
                # Add source information
                row_data['source_row'] = idx + 2  # +2 because pandas is 0-indexed and we skip header
                row_data['source_file'] = str(file_to_read)
                
                events.append(row_data)
        
        # Cache disabled for debugging
        load_time = time.time() - start_time
        
        # Ensure loading completes within 2 seconds per event (performance requirement)
        if load_time > 2.0:
            print(f"Warning: Database loading took {load_time:.2f} seconds, which exceeds 2 second target")
        
        return events
        
    except Exception as e:
        raise Exception(f"Error reading historical database file {file_to_read}: {str(e)}")


def compare_to_existing_cedant_data(
    loss_data_id: str,
    new_records: List[Dict[str, Any]],
    cedant_data_path: str = None
) -> Dict[str, Any]:
    """
    Check differences between newly generated cedant records and existing data.
    
    This tool compares the newly generated records (from PopulateCedantData)
    with what's already in the Cedant Loss Data table for a given LossDataID.
    
    Args:
        loss_data_id: The LossDataID to check records for
        new_records: List of newly generated records from PopulateCedantData
        cedant_data_path: Path to cedant data file (Excel or CSV).
                         If None, uses the configured DATA_DIR path.
        
    Returns:
        Dictionary containing:
        - success: bool
        - existing_records: List of existing records for this LossDataID
        - new_records_summary: Summary of new records
        - differences: Detailed comparison showing what would change
        - additions: Records that would be added (not in existing data)
        - modifications: Records that would modify existing data
        - unchanged: Records that match existing data
    """
    if cedant_data_path is None:
        cedant_data_path = get_cedant_data_path()
    
    try:
        # Load existing cedant data
        cedant_path = Path(cedant_data_path)
        csv_path = cedant_path.with_suffix('.csv')
        
        # Try CSV first, then Excel
        if csv_path.exists():
            existing_records = _load_cedant_data_csv(csv_path, loss_data_id)
        elif cedant_path.exists():
            existing_records = _load_cedant_data_excel(cedant_path, loss_data_id)
        else:
            return {
                "success": False,
                "error": f"Cedant data file not found: {cedant_data_path}",
                "message": "Could not locate cedant data file"
            }
        
        # Analyze differences
        differences = _analyze_record_differences(existing_records, new_records)
        
        return {
            "success": True,
            "loss_data_id": loss_data_id,
            "existing_record_count": len(existing_records),
            "new_record_count": len(new_records),
            "existing_records": existing_records,
            "differences": differences,
            "summary": {
                "total_additions": len(differences["additions"]),
                "total_modifications": len(differences["modifications"]),
                "total_unchanged": len(differences["unchanged"]),
                "total_in_existing_only": len(differences["in_existing_only"])
            },
            "message": f"Compared {len(new_records)} new records against {len(existing_records)} existing records for LossDataID {loss_data_id}"
        }
        
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "message": f"Error checking cedant data differences: {str(e)}"
        }


def _load_cedant_data_csv(csv_path: Path, loss_data_id: str) -> List[Dict[str, Any]]:
    """Load existing cedant data from CSV file for a specific LossDataID."""
    records = []
    
    # Ensure absolute path - go up to project root from agents/supervisor/tools/
    if not csv_path.is_absolute():
        project_root = Path(__file__).parent.parent.parent.parent
        csv_path = project_root / csv_path
    
    with open(csv_path, 'r', newline='', encoding='utf-8') as csvfile:
        reader = csv.DictReader(csvfile)
        for row in reader:
            if str(row.get('LossDataID', '')).strip() == str(loss_data_id).strip():
                # Note: CSV column names have spaces: ' Original Loss Gross '
                original_loss_gross = (
                    row.get(' Original Loss Gross ') or 
                    row.get('Original Loss Gross') or 
                    row.get(' Original Loss Gross') or
                    ''
                )
                
                records.append({
                    "index_num": int(row.get('IndexNum', 0)),
                    "as_of_year": str(row.get('AsOfYear', '')).strip(),
                    "hist_event_id": str(row.get('HistEventID', '')).strip() or None,
                    "loss_year": str(row.get('LossYear', '')).strip(),
                    "loss_description": str(row.get('LossDescription', '')).strip(),
                    "original_loss_gross": _parse_loss_amount(original_loss_gross),
                    "loss_data_id": str(row.get('LossDataID', '')).strip()
                })
    
    return records


def _load_cedant_data_excel(excel_path: Path, loss_data_id: str) -> List[Dict[str, Any]]:
    """Load existing cedant data from Excel file for a specific LossDataID."""
    import pandas as pd
    
    # Ensure absolute path (go up from agents/supervisor/tools/)
    if not excel_path.is_absolute():
        project_root = Path(__file__).parent.parent.parent.parent
        excel_path = project_root / excel_path
    
    df = pd.read_excel(excel_path, engine='openpyxl')
    
    # Filter by LossDataID
    mask = df['LossDataID'].astype(str).str.strip() == str(loss_data_id).strip()
    filtered_df = df[mask]
    
    records = []
    for _, row in filtered_df.iterrows():
        # Try different column name variations for Original Loss Gross
        original_loss_gross = None
        for col_name in [' Original Loss Gross ', 'Original Loss Gross', ' Original Loss Gross']:
            if col_name in row.index:
                original_loss_gross = _parse_loss_amount(row.get(col_name))
                break
        
        records.append({
            "index_num": int(row.get('IndexNum', 0)),
            "as_of_year": str(row.get('AsOfYear', '')).strip(),
            "hist_event_id": str(row.get('HistEventID', '')).strip() if pd.notna(row.get('HistEventID')) else None,
            "loss_year": str(row.get('LossYear', '')).strip(),
            "loss_description": str(row.get('LossDescription', '')).strip(),
            "original_loss_gross": original_loss_gross,
            "loss_data_id": str(row.get('LossDataID', '')).strip()
        })
    
    return records


def _parse_loss_amount(value) -> Optional[float]:
    """Parse loss amount from various formats."""
    if pd.isna(value) or value is None or value == '':
        return None
    
    if isinstance(value, (int, float)):
        return float(value)
    
    # Remove commas, spaces, dollar signs
    value_str = str(value).strip()
    
    # Handle " - " or "-" as null/empty
    if value_str in ['-', '']:
        return None
    
    cleaned = re.sub(r'[,$\s]', '', value_str)
    
    # After cleaning, check if empty or just "-"
    if not cleaned or cleaned == '-':
        return None
    
    try:
        return float(cleaned)
    except (ValueError, TypeError):
        return None


def _analyze_record_differences(
    existing_records: List[Dict[str, Any]], 
    new_records: List[Dict[str, Any]]
) -> Dict[str, Any]:
    """
    Analyze differences between existing and new records.
    
    Compares records based on loss_description only as the key.
    If the same event (by description) exists with different values, it's a modification.
    """
    # Create lookup dictionaries keyed by loss_description only
    existing_lookup = {}
    for record in existing_records:
        key = str(record.get('loss_description', '')).strip().lower()
        existing_lookup[key] = record
    
    new_lookup = {}
    for record in new_records:
        key = str(record.get('loss_description', '')).strip().lower()
        new_lookup[key] = record
    
    # Categorize records
    additions = []  # In new but not in existing
    modifications = []  # In both but with differences
    unchanged = []  # In both and identical
    in_existing_only = []  # In existing but not in new
    
    # Check new records
    for key, new_record in new_lookup.items():
        if key not in existing_lookup:
            additions.append({
                "record": new_record,
                "reason": "New event not in existing data"
            })
        else:
            existing_record = existing_lookup[key]
            diff = _compare_records(existing_record, new_record)
            
            if diff["has_differences"]:
                modifications.append({
                    "existing": existing_record,
                    "new": new_record,
                    "differences": diff["differences"]
                })
            else:
                unchanged.append({
                    "record": new_record,
                    "note": "Matches existing data"
                })
    
    # Check for records only in existing
    for key, existing_record in existing_lookup.items():
        if key not in new_lookup:
            in_existing_only.append({
                "record": existing_record,
                "note": "Exists in current data but not in new submission"
            })
    
    return {
        "additions": additions,
        "modifications": modifications,
        "unchanged": unchanged,
        "in_existing_only": in_existing_only
    }


def _compare_records(existing: Dict[str, Any], new: Dict[str, Any]) -> Dict[str, Any]:
    """Compare two records and identify differences."""
    differences = []
    has_differences = False
    
    # Fields to compare
    compare_fields = [
        'loss_year',  # Now included since we match on description only
        'as_of_year',
        'hist_event_id',
        'original_loss_gross'
    ]
    
    for field in compare_fields:
        existing_val = existing.get(field)
        new_val = new.get(field)
        
        # Normalize for comparison
        if field == 'original_loss_gross':
            # Compare as floats with tolerance
            existing_float = float(existing_val) if existing_val is not None else 0.0
            new_float = float(new_val) if new_val is not None else 0.0
            
            if abs(existing_float - new_float) > 0.01:  # Allow small floating point differences
                differences.append({
                    "field": field,
                    "existing_value": existing_val,
                    "new_value": new_val,
                    "change_type": "modified"
                })
                has_differences = True
        elif field == 'hist_event_id':
            # Special handling for hist_event_id: treat "0", 0, null, and empty as equivalent (no match)
            def normalize_hist_id(val):
                if val is None or val == "" or str(val).strip() == "0":
                    return "0"
                return str(val).strip()
            
            existing_normalized = normalize_hist_id(existing_val)
            new_normalized = normalize_hist_id(new_val)
            
            if existing_normalized != new_normalized:
                differences.append({
                    "field": field,
                    "existing_value": existing_val,
                    "new_value": new_val,
                    "change_type": "modified"
                })
                has_differences = True
        else:
            # String comparison for other fields
            existing_str = str(existing_val).strip() if existing_val is not None else ""
            new_str = str(new_val).strip() if new_val is not None else ""
            
            if existing_str != new_str:
                differences.append({
                    "field": field,
                    "existing_value": existing_val,
                    "new_value": new_val,
                    "change_type": "modified"
                })
                has_differences = True
    
    return {
        "has_differences": has_differences,
        "differences": differences
    }