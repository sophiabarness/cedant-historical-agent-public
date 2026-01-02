"""
Historical Event Matching Activities

This module contains Temporal activities for matching catastrophe events with the
Historical Event Database. It provides primary matching using event name and year,
and secondary matching with PCS codes when available.

Domain: Historical event matching and confidence scoring for catastrophe loss events.
"""

import re
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List

from temporalio import activity

from models.submission_pack import (
    HistoricalMatchInput,
    HistoricalMatchOutput,
    HistoricalEvent,
    CatastropheEvent,
)
from agents.supervisor.tools.utils.data_loaders import detect_csv_delimiter
from agents.supervisor.tools.utils.column_mapping import map_column_names, validate_required_columns
from agents.supervisor.tools.utils.fuzzy_matching import (
    calculate_fuzzy_match_score,
    extract_storm_name,
)
from shared.config import get_historical_db_path


@activity.defn
async def match_historical_events(input_data: HistoricalMatchInput) -> HistoricalMatchOutput:
    """
    Temporal Activity for matching catastrophe events with historical event database.
    
    This activity loads the Historical Event DB.xlsx file, performs primary matching using
    event name and year, and secondary matching with PCS codes when available.
    
    Args:
        input_data: HistoricalMatchInput containing event and database path
        
    Returns:
        HistoricalMatchOutput with match results and confidence scoring
    """
    activity.logger.info(f"Matching historical event: {input_data.event.loss_description} ({input_data.event.loss_year})")
    
    try:
        # Check if historical database file exists
        db_path = Path(input_data.historical_db_path)
        if not db_path.exists():
            return HistoricalMatchOutput(
                success=False,
                error_message=f"Historical Event DB not found at: {input_data.historical_db_path}"
            )
        
        # Load historical events from CSV
        file_extension = db_path.suffix.lower()
        if file_extension != '.csv':
            return HistoricalMatchOutput(
                success=False,
                error_message=f"Unsupported historical database format: {file_extension}. Only .csv is supported."
            )
        
        historical_events = await _load_historical_events_from_csv(db_path)
        
        if not historical_events:
            return HistoricalMatchOutput(
                success=False,
                error_message="No historical events found in database or database is empty"
            )
        
        activity.logger.info(f"Loaded {len(historical_events)} historical events from database")
        
        # Perform matching
        matches = _find_historical_matches(input_data.event, historical_events)
        
        # Determine best match and confidence
        if not matches:
            activity.logger.info("No historical matches found")
            return HistoricalMatchOutput(
                success=True,
                hist_event_id=None,
                match_confidence="none",
                potential_matches=[]
            )
        
        # Sort matches by confidence score (highest first)
        matches.sort(key=lambda x: x.get('confidence_score', 0), reverse=True)
        
        best_match = matches[0]
        confidence_score = best_match.get('confidence_score', 0)
        
        # Only return exact matches (threshold set to capture strong name+year matches)
        if confidence_score >= 90:
            match_confidence = "exact"
            hist_event_id = best_match['hist_event_id']
            activity.logger.info(f"Exact match found: {hist_event_id} (score: {confidence_score})")
        else:
            # Don't return partial matches - only exact matches
            match_confidence = "none"
            hist_event_id = None
            activity.logger.info(f"No exact match found (best score: {confidence_score})")
        
        # Prepare potential matches for user selection
        # Only include matches with confidence >= 80 to reduce noise
        # If exact match found (90+), show top 3; otherwise show top 5 above threshold
        potential_matches = []
        threshold = 80
        max_matches = 3 if hist_event_id else 5
        
        for match in matches:
            if match.get('confidence_score', 0) >= threshold and len(potential_matches) < max_matches:
                potential_matches.append({
                    'hist_event_id': match['hist_event_id'],
                    'event_name': match['event_name'],
                    'year': match['year'],
                    'event_date': match.get('event_date'),
                    'pcs_code': match.get('pcs_code'),
                    'confidence_score': match.get('confidence_score', 0),
                    'match_reasons': match.get('match_reasons', [])
                })
        
        return HistoricalMatchOutput(
            success=True,
            hist_event_id=hist_event_id,
            match_confidence=match_confidence,
            potential_matches=potential_matches
        )
        
    except Exception as e:
        activity.logger.error(f"Error matching historical events: {str(e)}")
        return HistoricalMatchOutput(
            success=False,
            error_message=f"Error matching historical events: {str(e)}"
        )


async def _load_historical_events_from_csv(db_path: Path) -> List[HistoricalEvent]:
    """Load historical events from CSV file."""
    import csv
    
    historical_events = []
    
    try:
        with open(db_path, 'r', newline='', encoding='utf-8') as csvfile:
            # Detect delimiter
            delimiter = detect_csv_delimiter(db_path)
            
            reader = csv.DictReader(csvfile, delimiter=delimiter)
            
            # Expected columns with flexible matching
            fieldnames = reader.fieldnames or []
            
            # Define expected column patterns
            expected_columns = {
                'HistEventID': ['historicaleventid', 'histeventid', 'hist_event_id', 'eventid', 'event_id'],
                'EventName': ['eventname', 'event_name', 'name'],
                'Year': ['year'],
                'EventDate': ['eventdate', 'event_date', 'date'],
                'PCSCode': ['pcsid', 'pcs_id', 'pcscode', 'pcs_code', 'pcs']
            }
            
            # Create case-insensitive column mapping
            column_mapping = map_column_names(fieldnames, expected_columns)
            
            # Check for required columns
            required_fields = ['HistEventID', 'EventName']
            is_valid, missing_fields = validate_required_columns(column_mapping, required_fields)
            if not is_valid:
                activity.logger.error(f"Missing required columns in historical database: {missing_fields}")
                activity.logger.error(f"Available columns: {fieldnames}")
                activity.logger.error(f"Column mapping: {column_mapping}")
                return []
            
            row_num = 1
            for row in reader:
                row_num += 1
                
                hist_event_id = str(row.get(column_mapping['HistEventID'], '')).strip()
                event_name = str(row.get(column_mapping['EventName'], '')).strip()
                
                # Extract year from EventDate or Year column
                year = None
                if 'Year' in column_mapping:
                    year = str(row.get(column_mapping['Year'], '')).strip()
                
                if not year and 'EventDate' in column_mapping:
                    event_date_value = str(row.get(column_mapping['EventDate'], '')).strip()
                    if event_date_value:
                        # Try 4-digit year first (e.g., "2012-08-26" or "08/26/2012")
                        year_match = re.search(r'(\d{4})', event_date_value)
                        if year_match:
                            year = year_match.group(1)
                        else:
                            # Try 2-digit year (e.g., "8/26/12" -> extract last 2 digits)
                            two_digit_match = re.search(r'(\d{1,2})/(\d{1,2})/(\d{2})$', event_date_value)
                            if two_digit_match:
                                two_digit_year = int(two_digit_match.group(3))
                                # Convert 2-digit to 4-digit (assume 2000s for 00-99)
                                year = str(2000 + two_digit_year) if two_digit_year < 100 else str(two_digit_year)
                
                if not hist_event_id or not event_name or not year:
                    continue  # Skip incomplete rows
                
                pcs_code = None
                if 'PCSCode' in column_mapping:
                    pcs_code = str(row.get(column_mapping['PCSCode'], '')).strip()
                    if not pcs_code:
                        pcs_code = None
                
                event_date = None
                if 'EventDate' in column_mapping:
                    event_date = str(row.get(column_mapping['EventDate'], '')).strip()
                    if not event_date:
                        event_date = None
                
                historical_events.append(HistoricalEvent(
                    hist_event_id=hist_event_id,
                    event_name=event_name,
                    year=year,
                    pcs_code=pcs_code,
                    event_date=event_date,
                    source_row=row_num
                ))
        
        activity.logger.info(f"Loaded {len(historical_events)} historical events from CSV")
        return historical_events
        
    except Exception as e:
        activity.logger.error(f"Error loading historical events from CSV: {str(e)}")
        return []


def _find_historical_matches(event: CatastropheEvent, historical_events: List[HistoricalEvent]) -> List[Dict[str, Any]]:
    """
    Find potential matches for a catastrophe event in the historical database.
    
    Args:
        event: CatastropheEvent to match
        historical_events: List of historical events to search
        
    Returns:
        List of potential matches with confidence scores
    """
    matches = []
    
    if not event.loss_year or not event.loss_description:
        return matches  # Cannot match without basic information
    
    event_year = event.loss_year.strip()
    event_description = event.loss_description.strip().lower()
    
    for hist_event in historical_events:
        match_score = 0
        match_reasons = []
        
        # Primary matching: Year and Date
        year_matched = False
        if hist_event.year == event_year:
            match_score += 40
            match_reasons.append(f"Year match: {event_year}")
            year_matched = True
        elif abs(int(hist_event.year) - int(event_year)) <= 1:
            # Allow 1 year difference for edge cases
            match_score += 30
            match_reasons.append(f"Year close match: {hist_event.year} vs {event_year}")
            year_matched = True
        
        # Primary matching: Event name
        hist_event_name = hist_event.event_name.lower()
        
        # Extract core storm names for better matching
        event_core = extract_storm_name(event_description)
        hist_core = extract_storm_name(hist_event_name)
        
        # Check if extracted names are too generic (prevent false matches)
        # Don't filter short names if they look like hurricane names (3 chars, all letters)
        generic_terms = {'winter storm', 'storm', 'hurricane', 'tropical storm', 'windstorm', 'hail', 'tornado', 'flood', 'fire', 'wind', 'scs', 'sscs', ''}
        
        def is_generic(name):
            if name in generic_terms:
                return True
            # Allow 3-letter hurricane names (all alphabetic)
            if len(name) == 3 and name.isalpha():
                return False
            # Block very short non-hurricane names
            if len(name) < 3:
                return True
            return False
        
        event_is_generic = is_generic(event_core)
        hist_is_generic = is_generic(hist_core)
        
        # Exact name match (but not if both are generic)
        if (event_description == hist_event_name or 
            (event_core == hist_core and not (event_is_generic and hist_is_generic))):
            match_score += 60
            match_reasons.append("Exact name match")
        # Substring matching - check if it's a strong match (hurricane name in description)
        # Use word boundaries to avoid false matches like "ian" in "victorian"
        elif (not event_is_generic and not hist_is_generic and
              (event_description in hist_event_name or hist_event_name in event_description or
               (event_core and hist_core and len(event_core) > 3 and len(hist_core) > 3 and (
                   event_core == hist_core or 
                   re.search(r'\b' + re.escape(event_core) + r'\b', hist_core) or
                   re.search(r'\b' + re.escape(hist_core) + r'\b', event_core))))):
            # If the event description is short (likely just the hurricane name), give higher score
            if len(event_description) <= 15 or len(event_core) <= 15:
                match_score += 50
                match_reasons.append("Strong partial name match")
            else:
                match_score += 35
                match_reasons.append("Partial name match")
        else:
            # Enhanced fuzzy matching for event names
            fuzzy_match_score, fuzzy_reasons = calculate_fuzzy_match_score(event_description, hist_event_name)
            match_score += fuzzy_match_score
            match_reasons.extend(fuzzy_reasons)
        
        # Secondary matching: PCS code (very high priority)
        # Extract PCS code from description
        event_pcs = None
        # Try to extract from description (e.g., "PCS 1713", "PCS #1713", "(PCS 1713)", "PCS CAT 2044")
        pcs_match = re.search(r'pcs\s*(?:cat\s*)?#?\s*(\d{4})', event_description, re.IGNORECASE)
        if pcs_match:
            event_pcs = pcs_match.group(1)
        
        if event_pcs and hist_event.pcs_code:
            # Historical PCS codes are in format "YYYY-NNNN", extract the NNNN part
            hist_pcs_match = re.search(r'-(\d{4})', hist_event.pcs_code)
            if hist_pcs_match:
                hist_pcs = hist_pcs_match.group(1)
                if event_pcs.strip() == hist_pcs:
                    match_score += 60  # Very high score for PCS match
                    match_reasons.append(f"PCS code exact match: {event_pcs}")
                    # PCS match is very reliable - if year was off, boost score to compensate
                    if not year_matched:
                        match_score += 35  # Boost to reach 95+ threshold even without year match
                        match_reasons.append("PCS code match compensates for year mismatch")
            # Also try exact match for full code
            elif event_pcs.strip() == hist_event.pcs_code.strip():
                match_score += 60
                match_reasons.append(f"PCS code exact match: {event_pcs}")
                if not year_matched:
                    match_score += 35
                    match_reasons.append("PCS code match compensates for year mismatch")
        
        # Only include matches with reasonable scores (raised threshold to reduce false positives)
        if match_score >= 50:
            matches.append({
                'hist_event_id': hist_event.hist_event_id,
                'event_name': hist_event.event_name,
                'year': hist_event.year,
                'event_date': hist_event.event_date,
                'pcs_code': hist_event.pcs_code,
                'confidence_score': match_score,
                'match_reasons': match_reasons,
                'source_row': hist_event.source_row
            })
    
    return matches


@activity.defn
async def match_single_event_activity(input_data: dict) -> dict:
    """
    Activity to match a single catastrophe event with historical database.
    
    Args:
        input_data: Dict containing:
            - event_data: Single event data dictionary with loss_description, loss_year, etc.
            - historical_db_path: Path to historical database (defaults to CSV)
            
    Returns:
        Dict containing match results with success status, match details, and confidence
    """
    try:
        # Extract arguments from input dict
        event_data = input_data.get('event_data')
        historical_db_path = input_data.get('historical_db_path') or get_historical_db_path()
        
        # Validate input
        if not event_data or not isinstance(event_data, dict):
            raise ValueError("event_data must be a non-empty dictionary")
        
        if not event_data.get('loss_description'):
            raise ValueError("loss_description is required")
        
        loss_description = event_data.get('loss_description', 'Unknown')
        loss_year = event_data.get('loss_year', '')
        
        activity.logger.info(f"Matching event: {loss_description} ({loss_year})")
        
        # Create CatastropheEvent object
        event = CatastropheEvent(
            loss_year=loss_year,
            loss_description=loss_description,
            original_loss_gross=event_data.get('original_loss_gross', 0.0),
            source_worksheet=event_data.get('source_worksheet', ''),
            source_row=event_data.get('source_row', 0)
        )
        
        # Create input and call matching function
        match_input = HistoricalMatchInput(
            event=event,
            historical_db_path=historical_db_path
        )
        
        match_result = await match_historical_events(match_input)
        
        # Convert to dict format for workflow
        result = {
            'success': match_result.success,
            'hist_event_id': match_result.hist_event_id,
            'match_confidence': match_result.match_confidence,
            'potential_matches': match_result.potential_matches,
            'error': match_result.error_message if not match_result.success else None,
            'processed_at': datetime.now().isoformat(),
            'event_description': loss_description
        }
        
        if match_result.hist_event_id:
            activity.logger.info(f"✓ Match found: {match_result.hist_event_id} (confidence: {match_result.match_confidence})")
        else:
            activity.logger.info(f"✗ No match found for: {loss_description}")
        
        return result
        
    except ValueError as ve:
        activity.logger.error(f"Validation error: {str(ve)}")
        return {
            "success": False,
            "error": str(ve),
            "error_type": "validation_error",
            "processed_at": datetime.now().isoformat()
        }
    except Exception as e:
        activity.logger.error(f"Error matching event: {str(e)}")
        return {
            "success": False,
            "error": str(e),
            "error_type": "processing_error",
            "processed_at": datetime.now().isoformat()
        }
