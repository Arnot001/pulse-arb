def build_signal(
    source,
    signal_type,
    course=None,
    race_time=None,
    horse=None,
    impact=0,
    severity="INFO",
    confidence="MEDIUM",
    reason="",
):
    return {
        "source": source,
        "type": signal_type,
        "course": course,
        "race_time": race_time,
        "horse": horse,
        "impact": impact,
        "severity": severity,
        "confidence": confidence,
        "reason": reason,
    }


def signal_summary(signals):
    return {
        "total": len(signals),
        "positive": len([s for s in signals if s.get("impact", 0) > 0]),
        "negative": len([s for s in signals if s.get("impact", 0) < 0]),
        "warnings": len([
            s for s in signals
            if s.get("severity") in ("WARNING", "HIGH")
        ]),
    }