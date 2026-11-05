"""Dependency-free reports built from persisted global optimization results."""

from __future__ import annotations

from typing import Any


def global_report_lines(record: dict[str, Any]) -> list[str]:
    result = record["result"]
    lines = [
        "QSUPPLY - SYNTHETIC GLOBAL OPTIMIZATION SUMMARY",
        f"Run: {record['id']}",
        f"Created: {record['created_at']}",
        f"Scenario: {record['scenario_id'] or 'Baseline network'}",
        f"Weights: {record['weights']}",
        f"Method: {result['algorithm']}",
        f"Search scope: {result['optimality_scope']}",
        "",
        "EXECUTIVE SUMMARY",
        f"Joint recovery feasible: {'yes' if result['recovery_feasible'] else 'no'}",
    ]
    snapshot = result.get("scenario_snapshot")
    if snapshot:
        lines.append(f"Scenario snapshot: {snapshot['name']} ({snapshot['id']})")
        lines.append(f"Scenario inputs: {snapshot}")
    baseline = result["baseline"]["metrics"]
    lines.extend(
        [
            f"Baseline total cost: {baseline['total_cost']:.2f} synthetic cost units",
            f"Baseline delivery time: {baseline['delivery_time']:.2f} shipment-days (summed)",
            f"Baseline carbon: {baseline['carbon_kg']:.2f} kgCO2e synthetic estimate",
            f"Baseline resilience exposure: {baseline['resilience_exposure']:.3f} synthetic score",
        ]
    )
    recovery = result.get("recovery")
    if recovery:
        metrics = recovery["metrics"]
        lines.extend(
            [
                f"Scenario total cost: {metrics['total_cost']:.2f} synthetic cost units",
                f"Scenario delivery time: {metrics['delivery_time']:.2f} shipment-days (summed)",
                f"Scenario carbon: {metrics['carbon_kg']:.2f} kgCO2e synthetic estimate",
                f"Scenario resilience exposure: {metrics['resilience_exposure']:.3f} synthetic score",
                f"Cost impact vs baseline: {metrics['total_cost'] - baseline['total_cost']:+.2f}",
                f"Time impact vs baseline: {metrics['delivery_time'] - baseline['delivery_time']:+.2f} shipment-days",
                f"Carbon impact vs baseline: {metrics['carbon_kg'] - baseline['carbon_kg']:+.2f} kgCO2e",
            ]
        )
    elif result.get("failure_reason"):
        lines.append(f"Recovery unavailable: {result['failure_reason']}")

    for plan_name in ("baseline", "recovery"):
        plan = result.get(plan_name)
        if not plan:
            continue
        lines.extend(["", f"{plan_name.upper()} SELECTED ROUTES"])
        for shipment_id, route in plan["routes"].items():
            lines.append(
                f"{shipment_id}: {route['id']} | modes={' / '.join(route['modes'])} | "
                f"distance={route['distance_km']:.1f} km | time={route['transit_time']:.2f} days | "
                f"cost={route['freight_cost']:.2f} | carbon={route['carbon_kg']:.2f} kgCO2e | "
                f"transfers={route['transfer_count']} | exposure={route['resilience_exposure']:.3f}"
            )
            for leg in route["legs"]:
                lines.append(
                    f"  {leg['link_id']} [{leg['mode']}]: {leg['distance_km']:.1f} km; "
                    f"{leg['transit_time']:.2f} days; cost {leg['freight_cost']:.2f}; "
                    f"carbon {leg['carbon_kg']:.2f} kgCO2e; capacity {leg['capacity']}"
                )
        carbon_by_mode: dict[str, float] = {}
        for route in plan["routes"].values():
            for leg in route["legs"]:
                carbon_by_mode[leg["mode"]] = carbon_by_mode.get(leg["mode"], 0.0) + leg["carbon_kg"]
        lines.append(f"Carbon by mode (kgCO2e estimate): {carbon_by_mode}")

    lines.extend(
        [
            "",
            "METHODOLOGY AND LIMITATIONS",
            "Synthetic demonstration network and shipment inputs only; no live operational data.",
            "Route generation is bounded. Assignment is exact only over generated candidate routes.",
            "Carbon values use synthetic per-load-unit link factors; not a regulatory accounting method.",
            "Transfer/handling costs, customs rules beyond explicit delay overlays, and route reliability are not modeled.",
            "QSupply deterministic decision assistance; no LLM-generated claims are included.",
        ]
    )
    return lines


def _pdf_text(value: str) -> bytes:
    safe = value.encode("cp1252", errors="replace").decode("cp1252")
    escaped = safe.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
    return f"({escaped})".encode("cp1252", errors="replace")


def global_report_pdf(record: dict[str, Any]) -> bytes:
    """Build a simple paginated text PDF without adding a runtime dependency."""
    lines = [line for source in global_report_lines(record) for line in (source[i : i + 105] for i in range(0, max(len(source), 1), 105))]
    pages = [lines[index : index + 48] for index in range(0, len(lines), 48)] or [[]]
    objects: dict[int, bytes] = {
        1: b"<< /Type /Catalog /Pages 2 0 R >>",
        3: b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    }
    page_ids = []
    for page_index, page_lines in enumerate(pages):
        page_id = 4 + page_index * 2
        content_id = page_id + 1
        page_ids.append(page_id)
        commands = [b"BT", b"/F1 9 Tf", b"50 760 Td", b"13 TL"]
        for line in page_lines:
            commands.extend([_pdf_text(line), b" Tj", b"T*"])
        commands.append(b"ET")
        content = b"\n".join(commands)
        objects[page_id] = (
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            f"/Resources << /Font << /F1 3 0 R >> >> /Contents {content_id} 0 R >>"
        ).encode("ascii")
        objects[content_id] = b"<< /Length " + str(len(content)).encode("ascii") + b" >>\nstream\n" + content + b"\nendstream"
    kids = " ".join(f"{page_id} 0 R" for page_id in page_ids)
    objects[2] = f"<< /Type /Pages /Kids [{kids}] /Count {len(page_ids)} >>".encode("ascii")
    object_count = max(objects) + 1
    output = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = [0] * object_count
    for object_id in range(1, object_count):
        offsets[object_id] = len(output)
        output.extend(f"{object_id} 0 obj\n".encode("ascii"))
        output.extend(objects[object_id])
        output.extend(b"\nendobj\n")
    xref_offset = len(output)
    output.extend(f"xref\n0 {object_count}\n".encode("ascii"))
    output.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        output.extend(f"{offset:010} 00000 n \n".encode("ascii"))
    output.extend(
        f"trailer\n<< /Size {object_count} /Root 1 0 R >>\nstartxref\n{xref_offset}\n%%EOF\n".encode("ascii")
    )
    return bytes(output)
