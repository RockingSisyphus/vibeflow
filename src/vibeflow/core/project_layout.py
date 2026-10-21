"""Default directory purposes shared by governance and architecture output."""

DIRECTORY_PURPOSES = {"nodes": "Business Node declarations and implementations", "base_lib": "Independent BaseLib resources",
    "plugins": "Atomic Plugin packages", "docs": "Documentation", "tests": "Tests", "runs": "Execution outputs",
    "vibeflow-preview": "Generated preview history", ".git": "Version control", ".venv": "Python environment",
    "node_modules": "JavaScript dependencies", "__pycache__": "Python bytecode cache",
    "build": "Generated build outputs", "dist": "Generated distributions"}
ROOT_DIRECTORY_PURPOSES = {**DIRECTORY_PURPOSES, "configs": "Workflow and NodesetType declarations",
    "scripts": "Author-provided launch and maintenance commands", "adapters": "Host API adapters",
    "assets": "Application assets", "web": "Browser application"}
