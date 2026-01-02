"""Cedant data population activities for the temporal supervisor agent.

This module contains activities for populating cedant loss data records.
It handles:
- Loading Program ID to Loss Data ID mappings
- Creating new cedant records from catastrophe events and historical matches
- Calculating index numbers for records

Domain Context:
- Cedant Loss Data: The main database of loss events for insurance programs
- Loss Data ID: Unique identifier for a program's loss data
- Program ID: External identifier for insurance programs
- Index Number: Sequential number for records within a program (sorted by year ASC, loss DESC)
- Historical Event ID: Reference to standardized historical catastrophe events
"""

from pathlib import Path
from typing import Optional, Dict, List, Any

from temporalio import activity

from models.submission_pack import (
    CedantRecord,
    CatastropheEvent,
)
from agents.supervisor.tools.utils.data_loaders import (
    load_csv_file,
    load_excel_file,
)
from agents.supervisor.tools.utils.column_mapping import (
    find_header_row,
    map_column_names,
)
from shared.config import get_temporal_client, get_cedant_data_path, get_mapping_file_path


async def _retrieve_extraction_data_from_bridge_workflow(bridge_workflow_id: str) -> Dict[str, Any]:
    """Retrieve extraction data (historical_matches, as_of_year, etc.) from the bridge workflow."""
    try:
        client = await get_temporal_client()
        handle = client.get_workflow_handle(bridge_workflow_id)
        result = await handle.query("get_extraction_data")
        
        if result and isinstance(result, dict):
            return result
        return {}
    except Exception as e:
        print(f"Failed to retrieve extraction data from bridge workflow {bridge_workflow_id}: {str(e)}")
        return {}


@activity.defn
async def populate_cedant_data(args: Dict[str, Any]) -> Dict[str, Any]:
    """
    Temporal Activity for populating cedant loss data with extracted information.
    
    This activity loads existing Cedant Loss Data, maps Program ID to Loss Data ID,
    calculates Index Numbers, and generates records without
    directly writing to the actual Cedant Loss Data.xlsx file.
    
    Historical matches and as_of_year are automatically retrieved from the bridge 
    workflow's data store using the bridge_workflow_id (injected by the workflow).
    
    Args:
        args: Dict containing:
            - program_id: Program ID for the submission pack
            - as_of_year: (Optional) As Of Year - if not provided, retrieved from bridge workflow
            - bridge_workflow_id: Workflow ID to retrieve data from (injected automatically)
        
    Returns:
        Dict with processing results and diff report
    """
    # Extract arguments from dict (workflow passes args=[tool_args])
    program_id = args.get("program_id")
    as_of_year = args.get("as_of_year")
    bridge_workflow_id = args.get("bridge_workflow_id")
    
    # Use defaults for file paths from config
    cedant_data_path = get_cedant_data_path()
    mapping_file_path = get_mapping_file_path()
    
    activity.logger.info(f"Populating cedant data for Program ID: {program_id}")
    
    # Validate required inputs
    if not program_id:
        return {
            "success": False,
            "error": "Program ID is required",
            "error_message": "Program ID is required"
        }
    
    if not bridge_workflow_id:
        return {
            "success": False,
            "error": "bridge_workflow_id is required (should be injected by workflow)",
            "error_message": "bridge_workflow_id is required. This is an internal error."
        }
    
    # Retrieve extraction data from bridge workflow's data store
    activity.logger.info(f"Retrieving extraction data from bridge workflow: {bridge_workflow_id}")
    extraction_data = await _retrieve_extraction_data_from_bridge_workflow(bridge_workflow_id)
    
    # Get as_of_year from bridge workflow if not provided in args
    if not as_of_year:
        as_of_year = extraction_data.get("as_of_year")
        if as_of_year:
            activity.logger.info(f"Retrieved as_of_year from bridge workflow: {as_of_year}")
    
    if not as_of_year:
        return {
            "success": False,
            "error": "As Of Year is required",
            "error_message": "As Of Year not found in args or bridge workflow data store"
        }
    
    # Get historical_matches from extraction data
    historical_matches = extraction_data.get("historical_matches", [])
    
    if not historical_matches:
        return {
            "success": False,
            "error": "Could not retrieve historical_matches from bridge workflow",
            "error_message": "historical_matches not found in bridge workflow - ensure HistoricalMatcher ran successfully"
        }
    
    activity.logger.info(f"Retrieved {len(historical_matches)} historical matches from bridge workflow")
    
    if not isinstance(historical_matches, list):
        return {
            "success": False,
            "error": "historical_matches must be a list",
            "error_message": f"Invalid historical_matches type: {type(historical_matches)}"
        }
    
    try:
        # Extract events from historical_matches (each item has event_data and historical_match)
        events = []
        for match_item in historical_matches:
            if isinstance(match_item, dict):
                # Get event_data from the match item
                actual_event = match_item.get("event_data", {})
                
                event = CatastropheEvent(
                    loss_year=actual_event.get("loss_year", ""),
                    loss_description=actual_event.get("loss_description", ""),
                    original_loss_gross=float(actual_event.get("original_loss_gross", 0)) if actual_event.get("original_loss_gross") else 0.0,
                    source_worksheet=actual_event.get("source_worksheet", ""),
                    source_row=int(actual_event.get("source_row", 0)) if actual_event.get("source_row") else 0
                )
                events.append(event)
            elif isinstance(match_item, CatastropheEvent):
                events.append(match_item)
        
        # Convert historical_matches dicts to a usable format
        # HistoricalMatcher returns: {"event_data": {...}, "historical_match": {"success": true, "hist_event_id": "...", "potential_matches": [...]}}
        matches = []
        if historical_matches and isinstance(historical_matches, list):
            for match_dict in historical_matches:
                if isinstance(match_dict, dict):
                    # Handle nested structure from HistoricalMatcher
                    hist_match = match_dict.get("historical_match", match_dict)
                    
                    # Create a simple object-like wrapper for the match
                    class MatchWrapper:
                        def __init__(self, d):
                            self.success = d.get("success", False)
                            self.hist_event_id = d.get("hist_event_id")
                            self.corrected_year = None
                            # If there's a PCS match, extract the year from the historical DB
                            # This handles cases where extracted loss_year is off by 1
                            potential_matches = d.get("potential_matches", [])
                            if potential_matches and self.hist_event_id:
                                for pm in potential_matches:
                                    if pm.get("hist_event_id") == self.hist_event_id:
                                        # Check if this was a PCS code match for year correction
                                        match_reasons = pm.get("match_reasons", [])
                                        has_pcs_match = any("PCS code" in reason for reason in match_reasons)
                                        if has_pcs_match and pm.get("year"):
                                            self.corrected_year = pm.get("year")
                                        break
                    matches.append(MatchWrapper(hist_match))
        
        # Step 1: Load Program ID to Loss Data ID mapping
        loss_data_id = await _get_loss_data_id(program_id, mapping_file_path)
        if not loss_data_id:
            return {
                "success": False,
                "error": f"Program ID {program_id} not found in Loss Data ProgramID Map",
                "error_message": f"Program ID {program_id} not found in Loss Data ProgramID Map"
            }
        
        activity.logger.info(f"Mapped Program ID {program_id} to Loss Data ID: {loss_data_id}")
        
        # Step 2: Create new records from events and historical matches
        new_records = []
        for i, event in enumerate(events):
            # Find corresponding historical match
            hist_match = None
            if i < len(matches):
                hist_match = matches[i]
            
            # Determine loss_year: use corrected year from historical DB if available (PCS match with year off by 1)
            loss_year = event.loss_year
            if hist_match and hist_match.corrected_year:
                loss_year = hist_match.corrected_year
                activity.logger.info(f"Using corrected year {loss_year} from historical DB for {event.loss_description}")
            
            # Create cedant record
            record = CedantRecord(
                loss_data_id=loss_data_id,
                index_num=0,  # Will be calculated after sorting
                as_of_year=as_of_year,
                hist_event_id=hist_match.hist_event_id if hist_match and hist_match.success else None,
                loss_year=loss_year,
                loss_description=event.loss_description or "",
                original_loss_gross=event.original_loss_gross or 0.0,
                source_info=f"Source: {event.source_worksheet}, Row: {event.source_row}"
            )
            new_records.append(record)
        
        # Step 3: Calculate Index Numbers (sort by year ASC, loss DESC)
        new_records = _calculate_index_numbers(new_records)
        
        activity.logger.info(f"Generated {len(new_records)} new records for Loss Data ID: {loss_data_id}")
        
        # Convert records to serializable format
        all_records = []
        for record in new_records:
            all_records.append({
                "loss_data_id": record.loss_data_id,
                "index_num": record.index_num,
                "as_of_year": record.as_of_year,
                "hist_event_id": record.hist_event_id,
                "loss_year": record.loss_year,
                "loss_description": record.loss_description,
                "original_loss_gross": record.original_loss_gross,
                "source_info": record.source_info
            })
        
        # Store cedant_records in bridge workflow for CompareToExistingCedantData to retrieve
        if bridge_workflow_id and all_records:
            try:
                client = await get_temporal_client()
                handle = client.get_workflow_handle(bridge_workflow_id)
                await handle.signal("store_extraction_data", {
                    "type": "cedant_records",
                    "value": all_records
                })
                activity.logger.info(f"Stored {len(all_records)} cedant_records in bridge workflow {bridge_workflow_id}")
            except Exception as e:
                activity.logger.warning(f"Failed to store cedant_records in bridge workflow: {str(e)}")
        
        return {
            "success": True,
            "records_count": len(new_records),
            "all_records": all_records,
            "loss_data_id": loss_data_id,
            "program_id": program_id,
            "as_of_year": as_of_year
        }
        
    except Exception as e:
        activity.logger.error(f"Error populating cedant data: {str(e)}")
        return {
            "success": False,
            "error": f"Error populating cedant data: {str(e)}",
            "error_message": f"Error populating cedant data: {str(e)}"
        }


# Helper functions for Program ID to Loss Data ID mapping

async def _get_loss_data_id(program_id: str, mapping_file_path: str) -> Optional[str]:
    """Load Program ID to Loss Data ID mapping."""
    mapping_path = Path(mapping_file_path)
    if not mapping_path.exists():
        activity.logger.error(f"Mapping file not found: {mapping_file_path}")
        return None
    
    # Determine file type and load accordingly
    file_extension = mapping_path.suffix.lower()
    
    if file_extension == '.csv':
        return await _get_loss_data_id_from_csv(program_id, mapping_path)
    elif file_extension in ['.xlsx', '.xls']:
        return await _get_loss_data_id_from_excel(program_id, mapping_path)
    else:
        activity.logger.error(f"Unsupported mapping file format: {file_extension}")
        return None


async def _get_loss_data_id_from_csv(program_id: str, mapping_path: Path) -> Optional[str]:
    """Load Program ID to Loss Data ID mapping from CSV file."""
    try:
        reader, error = load_csv_file(mapping_path)
        if error:
            activity.logger.error(f"Error loading CSV mapping file: {error}")
            return None
        
        fieldnames = reader.fieldnames or []
        
        # Create case-insensitive column mapping
        expected_mappings = {
            'program_id': ['program id', 'programid', 'program_id'],
            'loss_data_id': ['loss data id', 'lossdataid', 'loss_data_id', 'data id']
        }
        
        column_mapping = map_column_names(fieldnames, expected_mappings)
        
        if 'program_id' not in column_mapping or 'loss_data_id' not in column_mapping:
            activity.logger.error(f"Could not find required columns in CSV. Found: {fieldnames}")
            return None
        
        program_id_col = column_mapping['program_id']
        loss_data_id_col = column_mapping['loss_data_id']
        
        # Search for the Program ID
        program_id_str = str(program_id).strip()
        
        for row in reader:
            row_program_id = str(row.get(program_id_col, '')).strip()
            if row_program_id == program_id_str:
                loss_data_id = str(row.get(loss_data_id_col, '')).strip()
                return loss_data_id if loss_data_id else None
        
        return None
        
    except Exception as e:
        activity.logger.error(f"Error reading CSV mapping file: {str(e)}")
        return None


async def _get_loss_data_id_from_excel(program_id: str, mapping_path: Path) -> Optional[str]:
    """Load Program ID to Loss Data ID mapping from Excel file."""
    workbook, worksheet, error = load_excel_file(mapping_path)
    if error:
        activity.logger.error(f"Error loading Excel mapping file: {error}")
        return None
    
    try:
        # Find header row and column mappings
        expected_columns = {
            'program_id': ['program id', 'programid', 'program_id', 'id'],
            'loss_data_id': ['loss data id', 'lossdataid', 'loss_data_id', 'data id']
        }
        
        header_row, column_mappings = find_header_row(worksheet, expected_columns, min_required_fields=2)
        
        if not header_row or 'program_id' not in column_mappings or 'loss_data_id' not in column_mappings:
            workbook.close()
            activity.logger.error("Could not find required columns (Program ID, Loss Data ID) in mapping file")
            return None
        
        # Search for the Program ID
        program_id_str = str(program_id).strip()
        max_row = worksheet.max_row or 0
        
        for row_num in range(header_row + 1, max_row + 1):
            program_id_cell = worksheet.cell(row=row_num, column=column_mappings['program_id'])
            row_program_id = str(program_id_cell.value).strip() if program_id_cell.value else ""
            
            if row_program_id == program_id_str:
                loss_data_id_cell = worksheet.cell(row=row_num, column=column_mappings['loss_data_id'])
                loss_data_id = str(loss_data_id_cell.value).strip() if loss_data_id_cell.value else ""
                workbook.close()
                return loss_data_id if loss_data_id else None
        
        workbook.close()
        return None
        
    except Exception as e:
        activity.logger.error(f"Error reading Excel mapping file: {str(e)}")
        if workbook:
            workbook.close()
        return None


# Helper functions for record processing

def _calculate_index_numbers(records: List[CedantRecord]) -> List[CedantRecord]:
    """Calculate Index Numbers by sorting records by As Of Year ASC, loss DESC."""
    # Sort by As Of Year (ascending), then by original loss gross (descending)
    sorted_records = sorted(records, key=lambda r: (r.as_of_year, -r.original_loss_gross))
    
    # Assign index numbers
    for i, record in enumerate(sorted_records, 1):
        record.index_num = i
    
    return sorted_records


@activity.defn
async def compare_to_existing_cedant_data(args: Dict[str, Any]) -> Dict[str, Any]:
    """
    Temporal Activity for comparing new cedant records against existing data.
    
    This activity wraps the synchronous compare_to_existing_cedant_data function from
    agents/supervisor/tools/populate_cedant_data.py.
    
    Args:
        args: Dict containing:
            - loss_data_id: LossDataID to check records for
            - new_records: Array of newly generated records from PopulateCedantData (or USE_PREVIOUS_RESULT)
            - bridge_workflow_id: (Optional) Workflow ID to retrieve cedant_records from
            - cedant_data_path: (Optional) Path to cedant data file
        
    Returns:
        Dict with comparison results including additions, modifications, unchanged records
    """
    from agents.supervisor.tools.populate_cedant_data import compare_to_existing_cedant_data as sync_compare
    
    loss_data_id = args.get("loss_data_id")
    new_records = args.get("new_records", [])
    bridge_workflow_id = args.get("bridge_workflow_id")
    
    # Use default if path is None or not provided
    cedant_data_path = args.get("cedant_data_path") or get_cedant_data_path()
    
    activity.logger.info(f"Checking cedant data diff for Loss Data ID: {loss_data_id}")
    
    # Validate required inputs
    if not loss_data_id:
        return {
            "success": False,
            "error": "loss_data_id is required",
            "error_message": "loss_data_id is required"
        }
    
    # Handle USE_PREVIOUS_RESULT placeholder - retrieve from bridge workflow
    if isinstance(new_records, str) and new_records == "USE_PREVIOUS_RESULT":
        if bridge_workflow_id:
            activity.logger.info(f"Retrieving cedant_records from bridge workflow: {bridge_workflow_id}")
            try:
                client = await get_temporal_client()
                handle = client.get_workflow_handle(bridge_workflow_id)
                result = await handle.query("get_extraction_data")
                
                if result and isinstance(result, dict):
                    new_records = result.get("cedant_records", [])
                    if new_records:
                        activity.logger.info(f"Retrieved {len(new_records)} cedant_records from bridge workflow")
                    else:
                        return {
                            "success": False,
                            "error": "cedant_records not found in bridge workflow",
                            "error_message": "cedant_records not found - ensure PopulateCedantData ran successfully"
                        }
                else:
                    return {
                        "success": False,
                        "error": "Could not retrieve data from bridge workflow",
                        "error_message": "Failed to query bridge workflow for cedant_records"
                    }
            except Exception as e:
                activity.logger.error(f"Failed to retrieve cedant_records from bridge workflow: {str(e)}")
                return {
                    "success": False,
                    "error": f"Failed to retrieve cedant_records: {str(e)}",
                    "error_message": f"Failed to retrieve cedant_records from bridge workflow: {str(e)}"
                }
        else:
            return {
                "success": False,
                "error": "new_records placeholder requires bridge_workflow_id",
                "error_message": "Provide bridge_workflow_id to retrieve cedant_records from bridge workflow"
            }
    
    if not new_records or not isinstance(new_records, list):
        return {
            "success": False,
            "error": "new_records must be a non-empty list",
            "error_message": f"Invalid new_records: {type(new_records)}"
        }
    
    try:
        # Call the synchronous function
        result = sync_compare(
            loss_data_id=loss_data_id,
            new_records=new_records,
            cedant_data_path=cedant_data_path
        )
        
        activity.logger.info(f"Comparison completed: {result.get('message', 'No message')}")
        return result
        
    except Exception as e:
        activity.logger.error(f"Error comparing cedant data: {str(e)}")
        return {
            "success": False,
            "error": str(e),
            "error_message": f"Error comparing cedant data: {str(e)}"
        }
