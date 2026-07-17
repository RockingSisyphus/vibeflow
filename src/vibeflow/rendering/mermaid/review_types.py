from __future__ import annotations

from dataclasses import dataclass

REVIEW_COLUMNS_MAX_FRAGMENT_WIDTH = 3200.0
DETAIL_PANEL_COLUMN_GAP = 56.0
DETAIL_PANEL_ROW_GAP = 36.0
DETAIL_PANEL_TITLE_HEIGHT = 40.0
FRAGMENT_FRAME_PADDING = 10.0
REVIEW_COLUMNS_STYLE = (
    "<style>.review-title{font-family:Arial,sans-serif;font-size:22px;font-weight:800;fill:#0f172a}"
    ".review-panel-frame{fill:#ffffff;fill-opacity:.94;stroke:#334155;stroke-width:2}"
    ".review-title-bar{fill:#dbeafe;stroke:#334155;stroke-width:2}</style>"
)
DETAIL_PANEL_STYLE = (
    "<style>.review-title{font-family:Arial,sans-serif;font-size:20px;font-weight:800;fill:#0f172a}"
    ".review-panel-frame{fill:#ffffff;fill-opacity:.94;stroke:#475569;stroke-width:2}"
    ".review-title-bar{fill:#e0f2fe;stroke:#475569;stroke-width:2}"
    ".review-panel-guide{stroke:#64748b;stroke-width:1.5;stroke-dasharray:6 4;fill:none}</style>"
)
PLACEHOLDER_STYLE = (
    "<style>.placeholder-title{font-family:Arial,sans-serif;font-size:16px;font-weight:700;fill:#111827}"
    ".placeholder-text{font-family:Arial,sans-serif;font-size:14px;fill:#4b5563}"
    ".placeholder-box{fill:#f9fafb;stroke:#d1d5db;stroke-width:1}</style>"
)

@dataclass(frozen=True)
class _SvgFragment:
    title: str
    svg_text: str
    width: float
    height: float
