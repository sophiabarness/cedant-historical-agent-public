"""
Submission pack processing tools that integrate with Temporal activities.

These tools serve as wrappers around Temporal activities to provide
a consistent interface for the LLM-based agent system.
"""

from typing import Dict, Any
from pathlib import Path

from models.submission_pack import FileLocatorInput, FileLocatorOutput
from shared.config import get_submission_packs_dir


def locate_submission_pack(input_data: FileLocatorInput) -> FileLocatorOutput:
    """
    Locate submission pack file based on Program ID.
    
    Args:
        input_data: FileLocatorInput containing program_id and directory path
        
    Returns:
        FileLocatorOutput with file location results
    """
    try:
        # Use config default if not provided
        submission_packs_dir = input_data.submission_packs_directory
        if submission_packs_dir is None:
            submission_packs_dir = get_submission_packs_dir()
        
        directory = Path(submission_packs_dir)
        
        if not directory.exists():
            return FileLocatorOutput(
                success=False,
                error_message=f"Submission packs directory not found: {directory}"
            )
        
        # Search for files starting with the program ID (recursively)
        program_id = str(input_data.program_id)
        matching_files = []
        
        for file_path in directory.rglob("*"):
            if file_path.is_file() and file_path.name.startswith(program_id):
                file_type = None
                suffix = file_path.suffix.lower()
                if suffix in ['.xlsx', '.xlsm']:
                    file_type = 'excel'
                
                if file_type:
                    matching_files.append({
                        'path': str(file_path),
                        'name': file_path.name,
                        'type': file_type
                    })
        
        if not matching_files:
            return FileLocatorOutput(
                success=False,
                error_message=f"No submission pack found for Program ID: {program_id}"
            )
        
        matching_files.sort(key=lambda item: item['name'])
        # Return the first match (assuming 1:1 mapping as per requirements)
        first_match = matching_files[0]
        return FileLocatorOutput(
            success=True,
            file_path=first_match['path'],
            file_name=first_match['name'],
            file_type=first_match['type']
        )
        
    except Exception as e:
        return FileLocatorOutput(
            success=False,
            error_message=f"Error locating submission pack: {str(e)}"
        )


def locate_submission_pack_tool(program_id: str, submission_packs_directory: str = None) -> Dict[str, Any]:
    """
    Tool wrapper for LocateSubmissionPack functionality.
    
    This function provides a tool interface that locates submission pack files
    based on Program ID.
    
    Args:
        program_id: The Program ID to search for (e.g., '153300', '154516')
        submission_packs_directory: Directory path containing submission packs.
                                   If None, uses DATA_DIR/Submission Packs.
        
    Returns:
        Dict containing the location results in tool-compatible format
    """
    try:
        # Use config default if not provided
        if submission_packs_directory is None:
            submission_packs_directory = get_submission_packs_dir()
        
        # Create the proper input model
        input_data = FileLocatorInput(
            program_id=program_id,
            submission_packs_directory=submission_packs_directory
        )
        
        # Execute the function
        result: FileLocatorOutput = locate_submission_pack(input_data)
        
        # Convert result to tool-compatible format
        if result.success:
            return {
                "success": True,
                "file_path": result.file_path,
                "file_name": result.file_name,
                "file_type": result.file_type,
                "result": f"Successfully located submission pack: {result.file_name} at {result.file_path}"
            }
        else:
            return {
                "success": False,
                "error": result.error_message,
                "result": f"Failed to locate submission pack: {result.error_message}"
            }
            
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "result": f"Error locating submission pack: {str(e)}"
        }
