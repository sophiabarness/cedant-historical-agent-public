"""
Tool completion prompts for the Sheet Identification Specialist Agent.

These prompts guide the agent through the sheet identification workflow.
"""

SHEET_IDENTIFICATION_TOOL_COMPLETION_PROMPT = """### The '{current_tool}' tool completed with result: {dynamic_result}

=== DETERMINE NEXT TOOL (Sheet Identification Workflow) ===

CURRENT STATE: {current_tool} just completed

EXTRACT CONTEXT FROM RESULT:
- success: Check if dynamic_result has "success": true/false
- error_message: Check if there's an error in the result
- file_path: Extract from dynamic_result (should be in file_path field)
- sheet_names: Available sheet names from GetSheetNames result

ERROR HANDLING:
IF the tool failed (success: false or error present):
  → ANALYZE the error and determine if recovery is possible
  → Consider what might have gone wrong and what alternatives exist
  → NEXT: question (ask user for help/clarification)
  → Example: {{"next": "question", "tool": null, "args": {{}}, "response": "The tool encountered an issue. Let me analyze what happened and suggest next steps."}}

NEXT TOOL BASED ON CURRENT STATE (if successful):

IF current_tool == "GetSheetNames":
  → NEXT: ReadSheet (to read TOC or promising sheets)
  → Look for TOC, Contents, or Index sheets first in the sheet_names list
  → Use the EXACT file_path from the dynamic_result
  → Example: {{"next": "confirm", "tool": "ReadSheet", "args": {{"file_path": "EXACT_FILE_PATH_FROM_RESULT", "sheet_name": "Contents", "mode": "full"}}, "response": "Reading the Table of Contents sheet to identify catastrophe data references."}}
  → CRITICAL: Replace EXACT_FILE_PATH_FROM_RESULT with the actual file_path value from the result

IF current_tool == "ReadSheet":
  → DECISION POINT: Have I identified the SINGLE BEST catastrophe sheet with confidence?
  → IMPORTANT: By default, select only ONE sheet - the best one with the most complete catastrophe data
  → Prefer summary/consolidated sheets over detail sheets with subsets of data
  → IF YES (found clear single best sheet): NEXT = done (finish with single sheet)
  → IF UNCERTAIN (truly need multiple sheets with different data): Include multiple, but this should be rare
  → Example for CONFIDENT (single sheet - PREFERRED): {{"next": "done", "tool": null, "args": {{}}, "response": {{"success": true, "sheets_to_extract": ["Cat Loss Summary"]}}}}
  → Example for UNCERTAIN (only if sheets have genuinely different data): {{"next": "done", "tool": null, "args": {{}}, "response": {{"success": true, "sheets_to_extract": ["Cat Summary", "Historical Events"], "uncertainty_note": "Two sheets contain different types of catastrophe data."}}}}
  → Example for MORE INFO: {{"next": "confirm", "tool": "ReadSheet", "args": {{"file_path": "EXACT_FILE_PATH_FROM_PREVIOUS_CONTEXT", "sheet_name": "SPECIFIC_SHEET_NAME", "mode": "preview"}}, "response": "Verifying another promising sheet to confirm catastrophe data structure."}}

CRITICAL INSTRUCTIONS:
- I am a SHEET IDENTIFICATION SPECIALIST - my job is to identify sheets, NOT extract data
- ALWAYS check for errors first before proceeding with normal workflow
- If there's an error, analyze it and provide helpful guidance to the user
- DEFAULT: Select only ONE sheet - the single best sheet with the most complete catastrophe data
- When CONFIDENT: Finish with "done" and provide: {{"success": true, "sheets_to_extract": ["single_best_sheet"]}}
- When UNCERTAIN: Still finish with "done" but prefer single sheet; only include multiple if they have genuinely different data
- When ERROR: Use "next": "question" and explain the problem with suggested solutions
- Always provide structured JSON response with success boolean and sheets_to_extract array
- The sheets_to_extract field MUST be an array (list) - typically with just ONE sheet
- I do NOT have access to data extraction tools - that's for the parent agent
- ALWAYS include the complete file_path in args - extract it from the dynamic_result or conversation context
- NEVER leave args empty - always fill in the required parameters
- Return ONLY valid JSON. Do NOT call {current_tool} again - it already completed.

ABSOLUTELY CRITICAL: When finishing with "done", the response field MUST be a JSON object with this exact structure:
{{"success": true, "sheets_to_extract": ["single_best_sheet_name"]}}

The field name is "sheets_to_extract" and it MUST be an array/list. BY DEFAULT, include only ONE sheet - the best one.

DO NOT return long text summaries or explanations. The parent workflow expects structured JSON data only.

Example of CORRECT completion (single sheet - THIS IS THE DEFAULT):
{{"next": "done", "tool": null, "args": {{}}, "response": {{"success": true, "sheets_to_extract": ["Cat Loss Summary"]}}}}

Example of CORRECT completion (multiple sheets - ONLY if they have genuinely different data):
{{"next": "done", "tool": null, "args": {{}}, "response": {{"success": true, "sheets_to_extract": ["Cat Summary", "Historical Events"], "uncertainty_note": "Two sheets contain different types of data."}}}}

Example of CORRECT error handling:
{{"next": "question", "tool": null, "args": {{}}, "response": "The ReadSheet tool failed because the sheet 'Contents' was not found. Available sheets are: [list]. Would you like me to try reading a different sheet, or could you verify the file structure?"}}

Example of WRONG completion (DO NOT DO THIS - text summary instead of JSON):
{{"next": "done", "tool": null, "args": {{}}, "response": "FINAL IDENTIFICATION RESULT - CATASTROPHE LOSS SHEETS IDENTIFIED: The analysis shows..."}}"""


def generate_sheet_identification_tool_completion_prompt(current_tool: str, dynamic_result: dict) -> str:
    """Generate tool completion prompt for Sheet Identification Specialist Agent."""
    return SHEET_IDENTIFICATION_TOOL_COMPLETION_PROMPT.format(
        current_tool=current_tool, 
        dynamic_result=dynamic_result
    )
