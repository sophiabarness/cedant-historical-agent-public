"""Prompt templates for catastrophe loss extraction.

These prompts can be optimized using GEPA or other optimization frameworks.
"""

# Default data extraction prompt instructions
DEFAULT_DATA_EXTRACTION_INSTRUCTIONS = """Your task: Extract ALL catastrophe events with accurate gross loss amounts.

For each event, identify:
1. loss_year: The year the catastrophe occurred (extract from date if needed)
2. loss_description: The event name/description. Look for columns with headers (note that the header may not be in the first row) like:
   - "Cat", "Cat Description", "Storm Family", "Event Description", "Loss Description", "Peril", "Event Name"
   - PRIORITY ORDER: "Cat" (highest priority if it contains event names), "Storm Family", "Cat Description", "Event Description"
   - CRITICAL ABBREVIATIONS: "HU" = Hurricane, "TS" = Tropical Storm, "WS" = Wind Storm
   - CRITICAL: Loss descriptions should be TEXT-BASED event names, often using FIRST NAMES (e.g., "Hurricane Ida", "Sally", "Zeta", "Ian")
   - Catastrophe events are commonly named with first names (Sally, Ian, Ida, Helene, etc.) or disaster types (Storm, Hail, Wind/Hail)
   - DO NOT use columns with only NUMERIC values (like claim counts, dollar amounts, percentages)
   - Good examples: "Hurricane Irma", "Sally", "Zeta", "Ian", "Helene", "HU Ida", "TS Alberto", "Tropical Storm", "Wind/Hail", "PCS 1711", "Cat 41"
   - Bad examples: "123", "5000000", "45.2", "100%"
3. original_loss_gross: The GROSS loss amount using smart column selection (see rules below)

CRITICAL - Loss Amount Selection Rules:
The sheet may have multiple loss-related columns. Apply these rules IN ORDER:

A. If ONE column contains the combined total (e.g., "Total Loss & ALAE", "Loss and ALAE", "Gross Loss Incurred", "Total Incurred"):
   → Use that column directly (DO NOT sum multiple columns)

B. If SEPARATE columns exist for loss components (e.g., "Case Incurred Loss" AND "LAE", or "Incurred Loss" AND "ALAE"):
   → Sum these columns to get the total
   → Example: If row has "Case Incurred Loss: 100000" and "LAE: 25000", return 125000

C. Preference order for loss types (highest to lowest priority):
   1. GROSS loss (e.g., "Gross Loss", "Gross Incurred", "Gross Total Incurred Loss/LAE")
   2. INCURRED loss (e.g., "Total Incurred", "Incurred", "Case Incurred Loss") 
   3. TOTAL loss (e.g., "Total Loss", "Total Loss & ALAE")
   4. COMBINED loss (e.g., "Combined Total")
   5. NET loss (e.g., "Net Loss", "Net Incurred") - only if gross not available
   6. ULTIMATE loss (e.g., "Ultimate Loss", "Ultimate") - ABSOLUTE LAST RESORT
   
   CRITICAL: If any loss column contains "Inured" or "Inuring" (e.g., "Net of Inuring", "Inuring Losses"), PRIORITIZE IT over other columns
   CRITICAL: If you see BOTH "Incurred" AND "Ultimate" columns, ALWAYS use "Incurred" (not "Ultimate")

D. Prefer GRAND TOTALS over subcategories:
   - If you see columns for regions/sources (e.g., "FL Loss", "CA Loss", "Wind Loss", "Flood Loss"):
     Look for a "Total" or "Combined" column that sums these
   - If no total column exists, sum the subcategory columns
   - Avoid using subcategory values unless they represent the only loss data

Important guidelines:
- Skip header rows and total/summary rows (rows that aggregate multiple events)
- Extract the year from date fields if needed (e.g., "2020-01-10 00:00:00" → "2020")
- PCS NUMBER YEAR RULE: If the event name is a PCS number (format "PCS XXXX"), the loss_year MUST correspond to the first 2 digits of the PCS ID:
  - PCS 1721 → loss_year = 2017
  - PCS 2053 → loss_year = 2020
  - PCS 1912 → loss_year = 2019
  - The first 2 digits represent the year (17=2017, 20=2020, 19=2019, etc.)
- Loss amounts should be numbers, not formulas or text
- Multi-row headers are common - identify where actual data starts
- If a cell contains both a formula and a calculated value, use the calculated value
- ABBREVIATIONS: "HU" = Hurricane, "TS" = Tropical Storm, "WS" = Wind Storm
- Event names often use FIRST NAMES: Sally, Ian, Ida, Zeta, Alberto, Gordon, Helene, etc.
- CRITICAL: Extract ALL events regardless of loss amount size. Include events with small losses (e.g., $5000) as well as large ones.
- CRITICAL: Extract events even if ID/reference fields contain "none", "N/A", or are empty - these are still valid events
- DO NOT filter out events based on data sparsity or missing values in non-essential columns (ID fields, notes, etc.)

Return a JSON array with a "column_analysis" field explaining your column selection:
[
  {
    "loss_year": "2020",
    "loss_description": "Hurricane Sally",
    "original_loss_gross": 61331232.59,
    "source_row": 30,
    "column_analysis": "Used 'Total Loss & ALAE' column directly (contains combined total)"
  },
  {
    "loss_year": "2019",
    "loss_description": "Hurricane Dorian",
    "original_loss_gross": 8900000.00,
    "source_row": 28,
    "column_analysis": "Summed 'Incurred Loss' (8000000) + 'ALAE' (900000)"
  }
]

Extract ALL events you can identify. Be thorough and ensure loss amounts accurately reflect gross loss using the rules above."""


def load_data_extraction_instructions(custom_instructions: str = None) -> str:
    """Load data extraction instructions (default or custom).
    
    Priority order:
    1. custom_instructions (if provided)
    2. DEFAULT instructions (baseline)
    """
    # Use custom instructions if explicitly provided (not None and not empty)
    if custom_instructions is not None and custom_instructions:
        return custom_instructions
    
    return DEFAULT_DATA_EXTRACTION_INSTRUCTIONS

