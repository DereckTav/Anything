"""Data shape validators for URBANLENS backend responses."""


def validate_layer_data(data: dict):
    assert "zoning" in data, "Missing 'zoning' key"
    assert "environment" in data, "Missing 'environment' key"
    assert "safety" in data, "Missing 'safety' key"
    assert "activity_311" in data, "Missing 'activity_311' key"

    assert isinstance(data["zoning"]["far"], (int, float)), "FAR must be numeric"
    assert data["zoning"]["district"] is not None, "District must be non-null"

    assert isinstance(data["environment"]["aqi"], int), "AQI must be int"
    valid_aqi = {
        "Good", "Moderate", "Unhealthy for Sensitive Groups",
        "Unhealthy", "Very Unhealthy", "Hazardous",
    }
    assert data["environment"]["aqi_category"] in valid_aqi, "Unknown AQI category"

    assert data["safety"]["flood_risk"] in {"High Risk", "Low Risk"}, "Invalid flood_risk value"
    assert isinstance(data["activity_311"]["complaints"], list), "Complaints must be a list"
    print("✓ layer_data valid")


def validate_ar_labels(labels: list):
    valid_sources = {"PLUTO", "311", "PARKS", "SAFETY", "AQI"}
    valid_positions = {"top-left", "top-right", "mid-left", "mid-right", "bottom-left", "bottom-right"}
    for i, label in enumerate(labels):
        assert set(label.keys()) == {"source", "text", "position"}, (
            f"Label {i} has wrong keys: {label.keys()}"
        )
        assert label["source"] in valid_sources, f"Label {i} unknown source: {label['source']}"
        assert label["position"] in valid_positions, f"Label {i} unknown position: {label['position']}"
        assert len(label["text"]) > 0, f"Label {i} has empty text"
    print(f"✓ ar_labels valid ({len(labels)} labels)")


def validate_report(report: dict):
    assert "id" in report and report["id"].startswith("CS-"), "ID must start with 'CS-'"
    assert isinstance(report.get("narrative"), list), "narrative must be a list"
    assert len(report["narrative"]) > 0, "narrative must have entries"
    for i, entry in enumerate(report["narrative"]):
        assert "timestamp" in entry, f"narrative[{i}] missing timestamp"
        assert "text" in entry, f"narrative[{i}] missing text"
    assert 0 <= float(report.get("score", -1)) <= 10, "score must be 0-10"
    assert len(report.get("verdict", "")) > 0, "verdict must be non-empty"
    print("✓ report valid")


if __name__ == "__main__":
    # Example test data
    sample_layer = {
        "zoning": {"district": "R7A", "far": 4.0, "description": "High-density residential"},
        "environment": {"canopy_pct": 18, "aqi": 42, "aqi_category": "Good"},
        "safety": {"flood_risk": "Low Risk", "emergency_response_min": 3.5},
        "activity_311": {"complaints": [{"type": "NOISE", "description": "Loud construction"}]},
    }
    validate_layer_data(sample_layer)

    sample_labels = [
        {"source": "PLUTO", "text": "R7-2 Zoning", "position": "top-left"},
        {"source": "311", "text": "3x Noise", "position": "mid-right"},
    ]
    validate_ar_labels(sample_labels)

    sample_report = {
        "id": "CS-A1B2",
        "narrative": [{"timestamp": "00:05", "text": "Looking at a residential block..."}],
        "score": 6.5,
        "verdict": "Solid residential area with good transit access.",
    }
    validate_report(sample_report)
