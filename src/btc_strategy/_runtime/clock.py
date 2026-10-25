"""Exact original calendar router without experiment-driver imports."""
def forecast_year(day):
    return min(2025, max(2018, int(day[:4]) + int(day.endswith('-12-31'))))
