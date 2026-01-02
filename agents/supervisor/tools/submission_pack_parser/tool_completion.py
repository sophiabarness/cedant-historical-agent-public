"""
Tool completion prompts for the Submission Pack Parser Agent.

These prompts guide the agent through the systematic extraction workflow.
"""

SUBMISSION_PACK_PARSER_TOOL_COMPLETION_PROMPT = """### The '{current_tool}' tool completed with result: {dynamic_result}

=== DETERMINE NEXT TOOL (Submission Pack Parser Workflow) ===

CURRENT STATE: {current_tool} just completed

EXTRACT CONTEXT FROM RESULT:
- success: Check if dynamic_result has "success": true/false
- error_message: Check if there's an error in the result
- file_path: Extract from dynamic_result for next tool

ERROR HANDLING:
IF the tool failed (success: false or error present):
  → ANALYZE the error and determine if recovery is possible
  → Consider what might have gone wrong and what alternatives exist
  → NEXT: question (ask user for help/clarification)
  → Example: {{"next": "question", "tool": null, "args": {{}}, "response": "The tool encountered an issue. Let me analyze what happened and suggest next steps."}}

NEXT TOOL BASED ON CURRENT STATE (if successful):

IF current_tool == "LocateSubmissionPack":
  → NEXT: ExtractAsOfYear
  → Extract file_path from the LocateSubmissionPack result
  → Example: {{"next": "confirm", "tool": "ExtractAsOfYear", "args": {{"file_path": "<file_path_from_result>"}}, "response": "Now extracting the As Of Year from the located submission pack file."}}

IF current_tool == "ExtractAsOfYear":
  → NEXT: SheetIdentifier
  → Extract file_path from previous results
  → Example: {{"next": "confirm", "tool": "SheetIdentifier", "args": {{"file_path": "<file_path_from_result>"}}, "response": "Now identifying catastrophe data sheets in the submission pack."}}

IF current_tool == "SheetIdentifier":
  → NEXT: LLMExtractCatastropheData
  → Extract file_path from previous results and sheet_names from SheetIdentifier result
  → The SheetIdentifier result contains "sheets_to_extract" array - typically use only the first/recommended sheet
  → Example: {{"next": "confirm", "tool": "LLMExtractCatastropheData", "args": {{"file_path": "<file_path_from_result>", "sheet_names": ["Cat Losses"]}}, "response": "Now extracting catastrophe events from the identified sheet: Cat Losses"}}
  → CRITICAL: Use the first/recommended sheet from "sheets_to_extract" unless there's a specific reason to include multiple

IF current_tool == "LLMExtractCatastropheData":
  → NEXT: None (extraction complete)
  → DATA STORAGE: The full Events array has been automatically stored in the central workflow
  → The Supervisor Agent can access the complete data via the central workflow query
  → DO NOT copy the full events array in your response - provide a summary instead
  → REQUIRED FORMAT: {{"next": "done", "tool": null, "args": {{}}, "response": {{"success": true, "extracted_count": <count>, "extraction_approach": "...", "notes": [...], "error_message": "", "data_stored": true, "data_location": "central_workflow"}}}}
  → The "response" field should contain a summary with extracted_count and metadata
  → The full events data is available in the central workflow via get_extraction_data query

CRITICAL INSTRUCTIONS:
- ALWAYS check for errors first before proceeding with normal workflow
- If there's an error, analyze it and provide helpful guidance to the user
- When successful, proceed to the next logical tool in the workflow
- For LLMExtractCatastropheData completion: Provide summary only, full data is stored in central workflow
- Return ONLY valid JSON. Do NOT call {current_tool} again - it already completed.

DATA AVAILABILITY NOTE:
All extraction data (AsOfYear and Events) is automatically stored in the central workflow.
The Supervisor Agent can retrieve this data using the get_extraction_data query without 
requiring it to be passed through conversation history. This ensures reliable data transfer
for large datasets (150+ events) that would be unreliable to copy through LLM responses."""


def generate_submission_pack_parser_tool_completion_prompt(current_tool: str, dynamic_result: dict, previous_results: dict = None) -> str:
    """Generate tool completion prompt for Submission Pack Parser Agent with context injection."""
    # Inject previous tool results for context
    context_data = {}
    if previous_results:
        # Extract AsOfYear from previous results
        if "ExtractAsOfYear" in previous_results:
            as_of_year_result = previous_results["ExtractAsOfYear"]
            if as_of_year_result.get("success") and as_of_year_result.get("as_of_year"):
                context_data["as_of_year"] = as_of_year_result["as_of_year"]
        
        # Extract events summary from previous results (don't copy full array)
        if "LLMExtractCatastropheData" in previous_results:
            events_result = previous_results["LLMExtractCatastropheData"]
            if events_result.get("success") and events_result.get("events"):
                events = events_result["events"]
                context_data["events_summary"] = {
                    "total_count": len(events),
                    "sample_events": events[:3] if len(events) > 3 else events,
                    "extraction_approach": events_result.get("extraction_approach", ""),
                    "notes": events_result.get("notes", [])
                }
    
    # Format the prompt with context injection
    base_prompt = SUBMISSION_PACK_PARSER_TOOL_COMPLETION_PROMPT.format(
        current_tool=current_tool, 
        dynamic_result=dynamic_result
    )
    
    # Add context injection if available
    if context_data:
        context_section = f"\n\n=== WORKFLOW CONTEXT (Previous Tool Results) ===\n"
        if "as_of_year" in context_data:
            context_section += f"As Of Year: {context_data['as_of_year']}\n"
        if "events_summary" in context_data:
            events_info = context_data["events_summary"]
            context_section += f"Events Extracted: {events_info['total_count']} events\n"
            context_section += f"Extraction Approach: {events_info['extraction_approach']}\n"
            if events_info.get("sample_events"):
                context_section += f"Sample Events: {events_info['sample_events']}\n"
        context_section += "\nNOTE: Full event data is stored in workflow state and will be automatically passed to supervisor.\n"
        
        base_prompt = base_prompt + context_section
    
    return base_prompt