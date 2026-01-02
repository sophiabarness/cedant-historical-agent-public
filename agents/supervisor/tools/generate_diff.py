"""Generate diff functionality for comparing cedant data changes."""

from typing import Dict, Any, List, Optional
from pathlib import Path
import json


def generate_diff_report(
    loss_data_id: str,
    existing_records: List[Dict[str, Any]],
    new_records: List[Dict[str, Any]],
    program_id: str,
    as_of_year: str
) -> Dict[str, Any]:
    """
    Generate a comprehensive diff report comparing existing and new cedant records.
    
    Args:
        loss_data_id: The LossDataID being processed
        existing_records: List of existing records from cedant data
        new_records: List of newly generated records
        program_id: Program ID for context
        as_of_year: As Of Year for context
        
    Returns:
        Dictionary containing comprehensive diff report
    """
    try:
        # Analyze differences using the same logic as compare_to_existing_cedant_data
        from agents.supervisor.tools.populate_cedant_data import _analyze_record_differences
        
        differences = _analyze_record_differences(existing_records, new_records)
        
        # Generate summary statistics
        summary_stats = {
            "total_existing_records": len(existing_records),
            "total_new_records": len(new_records),
            "total_additions": len(differences["additions"]),
            "total_modifications": len(differences["modifications"]),
            "total_unchanged": len(differences["unchanged"]),
            "total_in_existing_only": len(differences["in_existing_only"]),
            "net_change": len(differences["additions"]) - len(differences["in_existing_only"])
        }
        
        # Generate detailed change descriptions
        change_descriptions = []
        
        # Additions
        for addition in differences["additions"]:
            record = addition["record"]
            change_descriptions.append({
                "type": "addition",
                "description": f"New event: {record.get('loss_description', 'Unknown')} ({record.get('loss_year', 'Unknown year')})",
                "loss_amount": record.get("original_loss_gross"),
                "hist_event_id": record.get("hist_event_id", "0"),
                "details": record
            })
        
        # Modifications
        for modification in differences["modifications"]:
            existing = modification["existing"]
            new = modification["new"]
            change_descriptions.append({
                "type": "modification",
                "description": f"Modified event: {new.get('loss_description', 'Unknown')}",
                "changes": modification["differences"],
                "existing_record": existing,
                "new_record": new
            })
        
        # Records only in existing (potential deletions)
        for existing_only in differences["in_existing_only"]:
            record = existing_only["record"]
            change_descriptions.append({
                "type": "potential_deletion",
                "description": f"Event in existing data but not in new submission: {record.get('loss_description', 'Unknown')}",
                "details": record,
                "note": "This event exists in current data but was not found in the new submission"
            })
        
        # Generate impact assessment
        impact_assessment = _generate_impact_assessment(differences, summary_stats)
        
        # Generate recommendations
        recommendations = _generate_recommendations(differences, summary_stats)
        
        return {
            "success": True,
            "loss_data_id": loss_data_id,
            "program_id": program_id,
            "as_of_year": as_of_year,
            "summary_stats": summary_stats,
            "differences": differences,
            "change_descriptions": change_descriptions,
            "impact_assessment": impact_assessment,
            "recommendations": recommendations,
            "generated_at": _get_current_timestamp(),
            "message": f"Generated diff report for LossDataID {loss_data_id} with {summary_stats['net_change']} net changes"
        }
        
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "message": f"Error generating diff report: {str(e)}"
        }


def _generate_impact_assessment(differences: Dict[str, Any], summary_stats: Dict[str, Any]) -> Dict[str, Any]:
    """
    Generate impact assessment based on the differences found.
    
    Args:
        differences: Analyzed differences from _analyze_record_differences
        summary_stats: Summary statistics
        
    Returns:
        Dictionary containing impact assessment
    """
    impact = {
        "severity": "low",
        "risk_factors": [],
        "financial_impact": {
            "total_new_losses": 0.0,
            "total_modified_losses": 0.0,
            "total_potential_deletions": 0.0
        },
        "data_quality_concerns": []
    }
    
    # Calculate financial impact
    for addition in differences["additions"]:
        amount = addition["record"].get("original_loss_gross", 0)
        if amount:
            impact["financial_impact"]["total_new_losses"] += float(amount)
    
    for modification in differences["modifications"]:
        new_amount = modification["new"].get("original_loss_gross", 0)
        existing_amount = modification["existing"].get("original_loss_gross", 0)
        if new_amount and existing_amount:
            impact["financial_impact"]["total_modified_losses"] += abs(float(new_amount) - float(existing_amount))
    
    for existing_only in differences["in_existing_only"]:
        amount = existing_only["record"].get("original_loss_gross", 0)
        if amount:
            impact["financial_impact"]["total_potential_deletions"] += float(amount)
    
    # Assess severity
    total_changes = summary_stats["total_additions"] + summary_stats["total_modifications"]
    if total_changes > 50:
        impact["severity"] = "high"
        impact["risk_factors"].append("Large number of changes (>50)")
    elif total_changes > 20:
        impact["severity"] = "medium"
        impact["risk_factors"].append("Moderate number of changes (>20)")
    
    # Check for high-value changes
    if impact["financial_impact"]["total_new_losses"] > 10000000:  # $10M
        impact["severity"] = "high"
        impact["risk_factors"].append("High-value new losses (>$10M)")
    
    if impact["financial_impact"]["total_potential_deletions"] > 5000000:  # $5M
        impact["severity"] = "high"
        impact["risk_factors"].append("High-value potential deletions (>$5M)")
    
    # Data quality concerns
    unmatched_events = len([a for a in differences["additions"] if a["record"].get("hist_event_id") == "0"])
    if unmatched_events > 0:
        impact["data_quality_concerns"].append(f"{unmatched_events} events could not be matched to historical data")
    
    return impact


def _generate_recommendations(differences: Dict[str, Any], summary_stats: Dict[str, Any]) -> List[str]:
    """
    Generate recommendations based on the analysis.
    
    Args:
        differences: Analyzed differences
        summary_stats: Summary statistics
        
    Returns:
        List of recommendation strings
    """
    recommendations = []
    
    # High-level recommendations
    if summary_stats["total_additions"] > 0:
        recommendations.append(f"Review {summary_stats['total_additions']} new events for accuracy and completeness")
    
    if summary_stats["total_modifications"] > 0:
        recommendations.append(f"Validate {summary_stats['total_modifications']} modified events to ensure changes are correct")
    
    if summary_stats["total_in_existing_only"] > 0:
        recommendations.append(f"Investigate {summary_stats['total_in_existing_only']} events that exist in current data but not in new submission")
    
    # Specific recommendations based on unmatched events
    unmatched_additions = [a for a in differences["additions"] if a["record"].get("hist_event_id") == "0"]
    if unmatched_additions:
        recommendations.append(f"Consider manual review of {len(unmatched_additions)} unmatched events for potential historical matches")
    
    # Data quality recommendations
    if summary_stats["total_modifications"] > summary_stats["total_additions"]:
        recommendations.append("High number of modifications detected - verify data extraction accuracy")
    
    # Backup recommendation
    if summary_stats["net_change"] != 0:
        recommendations.append("Create backup of existing data before applying changes")
    
    return recommendations


def _get_current_timestamp() -> str:
    """Get current timestamp in ISO format."""
    from datetime import datetime
    return datetime.now().isoformat()


def export_diff_report(
    diff_report: Dict[str, Any],
    output_path: Optional[str] = None,
    format: str = "json"
) -> Dict[str, Any]:
    """
    Export diff report to file.
    
    Args:
        diff_report: The diff report to export
        output_path: Optional output file path. If None, generates default path
        format: Export format ("json" or "txt")
        
    Returns:
        Dictionary with export results
    """
    try:
        if not output_path:
            # Generate default filename
            loss_data_id = diff_report.get("loss_data_id", "unknown")
            program_id = diff_report.get("program_id", "unknown")
            timestamp = _get_current_timestamp().replace(":", "-").replace(".", "-")
            
            if format == "json":
                output_path = f"diff_report_{program_id}_{loss_data_id}_{timestamp}.json"
            else:
                output_path = f"diff_report_{program_id}_{loss_data_id}_{timestamp}.txt"
        
        output_file = Path(output_path)
        
        if format == "json":
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(diff_report, f, indent=2, default=str)
        else:
            # Generate text format
            text_content = _format_diff_report_as_text(diff_report)
            with open(output_file, 'w', encoding='utf-8') as f:
                f.write(text_content)
        
        return {
            "success": True,
            "output_path": str(output_file),
            "format": format,
            "file_size": output_file.stat().st_size,
            "message": f"Diff report exported to {output_file}"
        }
        
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "message": f"Error exporting diff report: {str(e)}"
        }


def _format_diff_report_as_text(diff_report: Dict[str, Any]) -> str:
    """Format diff report as human-readable text."""
    lines = []
    
    # Header
    lines.append("=" * 80)
    lines.append("CEDANT DATA DIFF REPORT")
    lines.append("=" * 80)
    lines.append(f"Program ID: {diff_report.get('program_id', 'Unknown')}")
    lines.append(f"Loss Data ID: {diff_report.get('loss_data_id', 'Unknown')}")
    lines.append(f"As Of Year: {diff_report.get('as_of_year', 'Unknown')}")
    lines.append(f"Generated: {diff_report.get('generated_at', 'Unknown')}")
    lines.append("")
    
    # Summary
    summary = diff_report.get("summary_stats", {})
    lines.append("SUMMARY")
    lines.append("-" * 40)
    lines.append(f"Existing Records: {summary.get('total_existing_records', 0)}")
    lines.append(f"New Records: {summary.get('total_new_records', 0)}")
    lines.append(f"Additions: {summary.get('total_additions', 0)}")
    lines.append(f"Modifications: {summary.get('total_modifications', 0)}")
    lines.append(f"Unchanged: {summary.get('total_unchanged', 0)}")
    lines.append(f"In Existing Only: {summary.get('total_in_existing_only', 0)}")
    lines.append(f"Net Change: {summary.get('net_change', 0)}")
    lines.append("")
    
    # Impact Assessment
    impact = diff_report.get("impact_assessment", {})
    lines.append("IMPACT ASSESSMENT")
    lines.append("-" * 40)
    lines.append(f"Severity: {impact.get('severity', 'Unknown').upper()}")
    
    financial = impact.get("financial_impact", {})
    lines.append(f"Total New Losses: ${financial.get('total_new_losses', 0):,.2f}")
    lines.append(f"Total Modified Losses: ${financial.get('total_modified_losses', 0):,.2f}")
    lines.append(f"Total Potential Deletions: ${financial.get('total_potential_deletions', 0):,.2f}")
    
    risk_factors = impact.get("risk_factors", [])
    if risk_factors:
        lines.append("Risk Factors:")
        for factor in risk_factors:
            lines.append(f"  - {factor}")
    
    concerns = impact.get("data_quality_concerns", [])
    if concerns:
        lines.append("Data Quality Concerns:")
        for concern in concerns:
            lines.append(f"  - {concern}")
    lines.append("")
    
    # Recommendations
    recommendations = diff_report.get("recommendations", [])
    if recommendations:
        lines.append("RECOMMENDATIONS")
        lines.append("-" * 40)
        for i, rec in enumerate(recommendations, 1):
            lines.append(f"{i}. {rec}")
        lines.append("")
    
    # Detailed Changes
    changes = diff_report.get("change_descriptions", [])
    if changes:
        lines.append("DETAILED CHANGES")
        lines.append("-" * 40)
        
        additions = [c for c in changes if c["type"] == "addition"]
        modifications = [c for c in changes if c["type"] == "modification"]
        deletions = [c for c in changes if c["type"] == "potential_deletion"]
        
        if additions:
            lines.append("ADDITIONS:")
            for change in additions:
                lines.append(f"  + {change['description']}")
                if change.get("loss_amount"):
                    lines.append(f"    Amount: ${change['loss_amount']:,.2f}")
                lines.append(f"    Historical Match: {change.get('hist_event_id', '0')}")
                lines.append("")
        
        if modifications:
            lines.append("MODIFICATIONS:")
            for change in modifications:
                lines.append(f"  ~ {change['description']}")
                for diff in change.get("changes", []):
                    lines.append(f"    {diff['field']}: {diff['existing_value']} -> {diff['new_value']}")
                lines.append("")
        
        if deletions:
            lines.append("POTENTIAL DELETIONS:")
            for change in deletions:
                lines.append(f"  - {change['description']}")
                lines.append(f"    Note: {change.get('note', '')}")
                lines.append("")
    
    return "\n".join(lines)