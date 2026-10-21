"""Ordinary calls shared by runtime fixtures; execution follows graph edges."""
def normal_call(node_id, type_key, description, **options):
    return {"id": node_id, "definition_id": type_key,
            "display_name": node_id, "description": description, **options}
