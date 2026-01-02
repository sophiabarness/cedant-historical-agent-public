"""
Temporal activities for sheet identification tools.

These activities wrap the sheet identification tools to make them available
for use in Temporal workflows while maintaining determinism.
"""

from typing import Dict, Any
from temporalio import activity
from models.submission_pack import GetSheetNamesInput, GetSheetNamesOutput, ReadSheetInput, ReadSheetOutput


@activity.defn
async def get_sheet_names_activity(input_data: GetSheetNamesInput) -> Dict[str, Any]:
    """
    Activity wrapper for getting sheet names from an Excel file.
    
    Args:
        input_data: GetSheetNamesInput containing file path
        
    Returns:
        Dict containing sheet names and metadata
    """
    activity.logger.info(f"Getting sheet names from: {input_data.file_path}")
    
    try:
        # Import inside activity to avoid non-deterministic imports in workflow context
        from agents.supervisor.tools.submission_pack_parser.tools.sheet_identification.tools import SHEET_IDENTIFICATION_TOOL_HANDLERS
        
        handler = SHEET_IDENTIFICATION_TOOL_HANDLERS["GetSheetNames"]
        result = handler(input_data.file_path)
        
        if result.get("success"):
            activity.logger.info(f"Found {len(result.get('sheet_names', []))} sheets")
        else:
            activity.logger.error(f"Failed to get sheet names: {result.get('error_message')}")
        
        return result
        
    except Exception as e:
        activity.logger.error(f"Error in get_sheet_names_activity: {e}")
        return {
            "success": False,
            "sheet_names": [],
            "total_sheets": 0,
            "file_path": input_data.file_path,
            "file_size_mb": None,
            "error_message": f"Activity error: {str(e)}"
        }


@activity.defn
async def read_sheet_activity(input_data: ReadSheetInput) -> Dict[str, Any]:
    """
    Activity wrapper for reading sheet content from an Excel file.
    
    Args:
        input_data: ReadSheetInput containing file path, sheet name, and mode
        
    Returns:
        Dict containing sheet content and metadata
    """
    activity.logger.info(f"Reading sheet '{input_data.sheet_name}' from: {input_data.file_path} (mode: {input_data.mode})")
    
    try:
        # Import inside activity to avoid non-deterministic imports in workflow context
        from agents.supervisor.tools.submission_pack_parser.tools.sheet_identification.tools import SHEET_IDENTIFICATION_TOOL_HANDLERS
        
        handler = SHEET_IDENTIFICATION_TOOL_HANDLERS["ReadSheet"]
        result = handler(input_data.file_path, input_data.sheet_name, input_data.mode)
        
        if result.get("success"):
            activity.logger.info(f"Read {result.get('rows_returned', 0)} rows from sheet '{input_data.sheet_name}'")
        else:
            activity.logger.error(f"Failed to read sheet '{input_data.sheet_name}': {result.get('error_message')}")
        
        return result
        
    except Exception as e:
        activity.logger.error(f"Error in read_sheet_activity: {e}")
        return {
            "success": False,
            "sheet_name": input_data.sheet_name,
            "headers": [],
            "data_rows": [],
            "total_rows": 0,
            "total_columns": 0,
            "filtered_columns": 0,
            "filtered_rows": 0,
            "error_message": f"Activity error: {str(e)}"
        }