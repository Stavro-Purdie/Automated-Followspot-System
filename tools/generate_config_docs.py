#!/usr/bin/env python3
"""Generate Markdown documentation from JSON Schema files.

Auto-generates configuration documentation from JSON Schema definitions.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

SCHEMA_DIR = Path(__file__).resolve().parent.parent / "config" / "schemas"
OUTPUT_DIR = Path(__file__).resolve().parent.parent / "docs" / "config"


def load_schema(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text())


def type_to_str(prop: Dict[str, Any]) -> str:
    """Convert a JSON Schema property to a human-readable type string."""
    if "type" not in prop:
        if "enum" in prop:
            return f"enum[{', '.join(str(v) for v in prop['enum'])}]"
        return "any"
    
    t = prop["type"]
    if isinstance(t, list):
        t = t[0]
    
    if t == "array":
        items = prop.get("items", {})
        item_type = type_to_str(items) if isinstance(items, dict) else "any"
        return f"array[{item_type}]"
    elif t == "object":
        return "object"
    elif t == "string":
        if "format" in prop:
            return f"string ({prop['format']})"
        if "enum" in prop:
            return f"enum[{', '.join(str(v) for v in prop['enum'])}]"
        if "pattern" in prop:
            return f"string (pattern: {prop['pattern']})"
        return "string"
    elif t == "integer":
        constraints = []
        if "minimum" in prop:
            constraints.append(f"min: {prop['minimum']}")
        if "maximum" in prop:
            constraints.append(f"max: {prop['maximum']}")
        return f"integer ({', '.join(constraints)})" if constraints else "integer"
    elif t == "number":
        constraints = []
        if "minimum" in prop:
            constraints.append(f"min: {prop['minimum']}")
        if "maximum" in prop:
            constraints.append(f"max: {prop['maximum']}")
        return f"number ({', '.join(constraints)})" if constraints else "number"
    elif t == "boolean":
        return "boolean"
    return t


def format_description(prop: Dict[str, Any]) -> str:
    """Format property description with constraints."""
    parts = []
    if "description" in prop:
        parts.append(prop["description"])
    
    if "minimum" in prop or "maximum" in prop:
        constraints = []
        if "minimum" in prop:
            constraints.append(f"min: {prop['minimum']}")
        if "maximum" in prop:
            constraints.append(f"max: {prop['maximum']}")
        parts.append(f"Range: {', '.join(constraints)}")
    
    if "enum" in prop:
        parts.append(f"Allowed values: {', '.join(str(v) for v in prop['enum'])}")
    
    if "format" in prop:
        parts.append(f"Format: {prop['format']}")
    
    return " ".join(parts) if parts else ""


def generate_property_table(props: Dict[str, Any], required: List[str], indent: int = 0) -> List[str]:
    """Generate a markdown table for object properties."""
    lines = []
    indent_str = "  " * indent
    
    # Table header
    lines.append(f"{indent_str}| Property | Type | Required | Description |")
    lines.append(f"{indent_str}|----------|------|----------|-------------|")
    
    for prop_name, prop_schema in sorted(props.items()):
        prop_type = type_to_str(prop_schema)
        is_required = "✅" if prop_name in required else "❌"
        desc = format_description(prop_schema)
        
        # Escape pipe characters in description
        desc = desc.replace("|", "\\|")
        
        lines.append(f"{indent_str}| {prop_name} | {prop_type} | {is_required} | {desc} |")
        
        # Handle nested objects
        if prop_schema.get("type") == "object" and "properties" in prop_schema:
            nested_required = prop_schema.get("required", [])
            lines.extend(generate_property_table(prop_schema["properties"], nested_required, indent + 1))
        elif prop_schema.get("type") == "array" and isinstance(prop_schema.get("items"), dict) and prop_schema["items"].get("type") == "object":
            nested_props = prop_schema["items"].get("properties", {})
            nested_required = prop_schema["items"].get("required", [])
            lines.append(f"{indent_str}  *Array items:*")
            lines.extend(generate_property_table(nested_props, nested_required, indent + 2))
    
    return lines


def generate_schema_doc(schema: Dict[str, Any], title: str) -> str:
    """Generate markdown documentation from a JSON Schema."""
    lines = []
    
    # Title
    lines.append(f"# {title}")
    lines.append("")
    
    if "description" in schema:
        lines.append(schema["description"])
        lines.append("")
    
    # Required fields
    required = schema.get("required", [])
    
    # Properties
    properties = schema.get("properties", {})
    
    if properties:
        lines.append("## Properties")
        lines.append("")
        lines.extend(generate_property_table(properties, schema.get("required", [])))
        lines.append("")
    
    # Required fields summary
    if required:
        lines.append("## Required Fields")
        lines.append("")
        for req in sorted(required):
            lines.append(f"- **{req}**")
        lines.append("")
    
    return "\n".join(lines)


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    
    schema_files = [
        ("front_array_config.schema.json", "Front Array Camera Configuration"),
        ("roof_array_config.schema.json", "Roof Array Camera Configuration"),
        ("spotlight_config.schema.json", "Spotlight Configuration"),
        ("reid_config.schema.json", "ReID Configuration"),
    ]
    
    for schema_file, title in schema_files:
        schema_path = SCHEMA_DIR / schema_file
        if not schema_path.exists():
            print(f"⚠️  Schema not found: {schema_path}")
            continue
        
        schema = load_schema(schema_path)
        doc = generate_schema_doc(schema, title)
        
        output_file = OUTPUT_DIR / f"{schema_file.replace('.schema.json', '')}.md"
        output_file.write_text(doc)
        print(f"✅ Generated {output_file}")
    
    # Also generate a summary index
    index_lines = [
        "# Configuration Reference",
        "",
        "Auto-generated from JSON Schema definitions.",
        "",
        "## Configuration Files",
        "",
    ]
    
    for _, title in schema_files:
        anchor = title.lower().replace(" ", "-")
        index_lines.append(f"- [{title}]({anchor}.md)")
    
    index_path = OUTPUT_DIR / "index.md"
    index_path.write_text("\n".join(index_lines))
    print(f"✅ Generated {index_path}")
    
    print("\n✅ Documentation generation complete!")


if __name__ == "__main__":
    main()