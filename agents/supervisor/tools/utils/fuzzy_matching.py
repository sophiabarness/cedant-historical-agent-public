"""Fuzzy matching utilities for event name matching."""

import re
from typing import Tuple, List
from fuzzywuzzy import fuzz


def calculate_fuzzy_match_score(event_description: str, hist_event_name: str) -> Tuple[int, List[str]]:
    """
    Calculate fuzzy match score between event descriptions using multiple algorithms.
    
    Args:
        event_description: Description from the catastrophe event
        hist_event_name: Name from the historical event
        
    Returns:
        Tuple of (match_score, list_of_reasons)
    """
    match_score = 0
    reasons = []
    
    # Preprocess names to extract core hurricane/storm names
    clean_event = extract_storm_name(event_description)
    clean_hist = extract_storm_name(hist_event_name)
    
    # Test both original and cleaned names
    test_pairs = [
        (event_description, hist_event_name, "original"),
        (clean_event, clean_hist, "cleaned"),
        (clean_event, hist_event_name, "mixed")
    ]
    
    best_overall_score = 0
    best_pair_type = ""
    
    for event_name, hist_name, pair_type in test_pairs:
        # Multiple fuzzy matching algorithms
        partial_ratio = fuzz.partial_ratio(event_name, hist_name)
        token_sort_ratio = fuzz.token_sort_ratio(event_name, hist_name)
        token_set_ratio = fuzz.token_set_ratio(event_name, hist_name)
        
        # Use the best score from different algorithms
        best_fuzzy_score = max(partial_ratio, token_sort_ratio, token_set_ratio)
        
        if best_fuzzy_score > best_overall_score:
            best_overall_score = best_fuzzy_score
            best_pair_type = pair_type
    
    # Score based on best match found
    if best_overall_score >= 85:
        match_score += 35
        reasons.append(f"High fuzzy match (score: {best_overall_score}, type: {best_pair_type})")
    elif best_overall_score >= 75:
        match_score += 30
        reasons.append(f"Good fuzzy match (score: {best_overall_score}, type: {best_pair_type})")
    elif best_overall_score >= 65:
        match_score += 25
        reasons.append(f"Moderate fuzzy match (score: {best_overall_score}, type: {best_pair_type})")
    elif best_overall_score >= 50:
        match_score += 15
        reasons.append(f"Weak fuzzy match (score: {best_overall_score}, type: {best_pair_type})")
    elif best_overall_score >= 40:
        match_score += 10
        reasons.append(f"Very weak fuzzy match (score: {best_overall_score}, type: {best_pair_type})")
    
    # Additional scoring for token set matching (good for hurricane names)
    token_set_score = fuzz.token_set_ratio(clean_event, clean_hist)
    if token_set_score >= 70:
        match_score += 5
        reasons.append(f"Strong token set match on cleaned names: {token_set_score}")
    
    return match_score, reasons


def extract_storm_name(name: str) -> str:
    """
    Extract the core storm name from a full event description.
    
    Args:
        name: Full event description
        
    Returns:
        Cleaned storm name
    """
    # Handle historical DB format like "6-Jul-21; Tropical Storm Elsa" - take the part after semicolon
    if '; ' in name:
        parts = name.split('; ')
        # Use the longer/more descriptive part (usually after the semicolon)
        name = max(parts, key=len)
    
    # Remove PCS CAT prefix (e.g., "PCS CAT 2044 Isaias" -> "Isaias")
    name = re.sub(r'^pcs\s*cat\s*\d+\s*', '', name, flags=re.IGNORECASE)
    
    # Remove common prefixes (full names and abbreviations)
    # HU = Hurricane, TS = Tropical Storm, WS = Winter Storm
    # Also handle "HU - Name" format with dash
    name = re.sub(r'^(hurricane|tropical storm|winter storm|storm|hu|ts|ws)\s*[-]?\s*', '', name, flags=re.IGNORECASE)
    
    # Remove dates and extra info (anything after comma or parentheses, but NOT semicolon since we handled it)
    name = re.split(r'[,(]', name)[0].strip()
    
    # Remove trailing date patterns
    name = re.sub(r'\s+\d{1,2}[/-]\d{1,2}[/-]\d{2,4}.*$', '', name)
    name = re.sub(r'\s+\d{4}.*$', '', name)
    
    return name.strip()
