"""
Tool completion prompts for the Supervisor Agent.

These prompts guide the agent on what to do after each tool completes successfully.

IMPORTANT: Extraction data (AsOfYear, Events, HistoricalMatches) is automatically stored 
in the workflow's data store. Activities retrieve this data automatically - the LLM 
doesn't need to pass it explicitly.
"""

SUPERVISOR_TOOL_COMPLETION_PROMPT = """### The '{current_tool}' tool completed with result: {dynamic_result}

=== DETERMINE NEXT TOOL (Supervisor Agent Workflow) ===

CURRENT STATE: {current_tool} just completed

EXTRACT CONTEXT FROM RESULT:
- success: Check if dynamic_result has "success": true/false
- error_message: Check if there's an error in the result

ERROR HANDLING:
IF the tool failed (success: false or error present):
  → ANALYZE the error and determine if it can be recovered
  → Common errors and solutions:
    - Submission pack parsing failed: Ask user to verify file or try different approach
    - Event processing failed: Check data format or ask for user guidance
    - Data population failed: Verify database access or data integrity
    - Historical matching failed: Check historical database availability
  → NEXT: question (ask user for help/clarification)
  → Example: {{"next": "question", "tool": null, "args": {{}}, "response": "The {current_tool} tool failed with error: [error_message]. This might be because [analysis]. Could you please [suggested_action]?"}}

NEXT TOOL BASED ON CURRENT STATE (if successful):

IF current_tool == "SubmissionPackParserAgent":
  → NEXT: HistoricalMatcher
  → Extract program_id from previous results
  → NOTE: Events are automatically retrieved from the workflow's data store - no need to pass them
  → Example: {{"next": "confirm", "tool": "HistoricalMatcher", "args": {{"program_id": "153214"}}, "response": "Processing extracted events with historical matching."}}

IF current_tool == "HistoricalMatcher":
  → NEXT: PopulateCedantData
  → Extract program_id from previous results
  → NOTE: Historical matches AND as_of_year are automatically retrieved from the workflow's data store
  → Example: {{"next": "confirm", "tool": "PopulateCedantData", "args": {{"program_id": "153214"}}, "response": "Populating Cedant Loss Data with matched events."}}

IF current_tool == "PopulateCedantData":
  → NEXT: CompareToExistingCedantData
  → Extract loss_data_id from result
  → Use "USE_PREVIOUS_RESULT" for new_records
  → Example: {{"next": "confirm", "tool": "CompareToExistingCedantData", "args": {{"loss_data_id": "534129", "new_records": "USE_PREVIOUS_RESULT"}}, "response": "Comparing new records against existing Cedant data."}}

IF current_tool == "CompareToExistingCedantData":
  → NEXT: None (workflow complete)
  → Example: {{"next": "done", "tool": null, "args": {{}}, "response": "Workflow complete! Successfully processed submission pack."}}

CRITICAL INSTRUCTIONS:
- ALWAYS check for errors first before proceeding with normal workflow
- If there's an error, analyze it and provide helpful guidance to the user
- When successful, proceed to the next logical tool in the workflow
- Return ONLY valid JSON. Do NOT call {current_tool} again - it already completed.

DATA STORAGE NOTE:
The workflow automatically stores and retrieves extraction data (AsOfYear, Events, HistoricalMatches) 
between tools. Activities retrieve this data automatically - you don't need to pass it explicitly."""


def generate_supervisor_tool_completion_prompt(current_tool: str, dynamic_result: dict) -> str:
    """Generate tool completion prompt for Supervisor Agent."""
    return SUPERVISOR_TOOL_COMPLETION_PROMPT.format(
        current_tool=current_tool, 
        dynamic_result=dynamic_result
    )
