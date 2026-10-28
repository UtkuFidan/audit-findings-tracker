"""Accessible colours (Okabe-Ito based), shared by every chart so risk colours stay consistent."""

RISK_ORDER = ["Critical", "High", "Medium", "Low"]
RISK_COLOURS = {
    "Critical": "#9B1B4D",
    "High": "#D55E00",
    "Medium": "#E0A100",
    "Low": "#0072B2",
}

STATUS_ORDER = ["Open", "In progress", "Overdue", "Implemented", "Validated", "Risk accepted"]

NEUTRAL = "#5B6770"
ACCENT = "#0072B2"
HEATMAP_SCALE = [[0.0, "#F4F7FA"], [0.5, "#7FB2D6"], [1.0, "#0B3C5D"]]
