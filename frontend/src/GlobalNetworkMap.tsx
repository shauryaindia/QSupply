import { useEffect, useRef } from "react";
import * as L from "leaflet";
import "leaflet/dist/leaflet.css";
import type {
  CandidateRoute,
  NetworkResponse,
} from "./api/client";
import type { components } from "./api/generated";

type NetworkNode = components["schemas"]["NetworkNode"];
type ShipmentPosition = components["schemas"]["ShipmentPositionResponse"];

const modeColors: Record<string, string> = {
  road: "#77899b",
  rail: "#b88233",
  sea: "#2788bb",
  air: "#8060b7",
};

const markerSymbols: Record<string, string> = {
  port: "⚓",
  airport: "✈",
  rail_terminal: "▰",
  warehouse: "▦",
  factory: "◆",
  destination: "●",
  multimodal_hub: "✦",
  city: "●",
  other: "•",
};

/** Split geographic polylines at the antimeridian to avoid map-spanning chords. */
export function splitAtAntimeridian(
  points: [number, number][],
): [number, number][][] {
  if (points.length < 2) return points.length ? [[...points]] : [];
  const segments: [number, number][][] = [[points[0]]];
  for (let index = 1; index < points.length; index += 1) {
    const previous = points[index - 1];
    const next = points[index];
    const longitudeDelta = next[1] - previous[1];
    if (Math.abs(longitudeDelta) <= 180) {
      segments[segments.length - 1].push(next);
      continue;
    }
    const crossesEastward = longitudeDelta < -180;
    const unwrappedLongitude = next[1] + (crossesEastward ? 360 : -360);
    const boundary = crossesEastward ? 180 : -180;
    const fraction = (boundary - previous[1]) / (unwrappedLongitude - previous[1]);
    const crossingLatitude = previous[0] + (next[0] - previous[0]) * fraction;
    segments[segments.length - 1].push([crossingLatitude, boundary]);
    segments.push([
      [crossingLatitude, -boundary],
      next,
    ]);
  }
  return segments;
}

function locationIcon(kind: string, selected: boolean): L.DivIcon {
  const symbol = markerSymbols[kind] ?? markerSymbols.other;
  return L.divIcon({
    className: "global-node-icon",
    html: `<span class="global-node-marker ${selected ? "selected" : ""} kind-${kind}">${symbol}</span>`,
    iconSize: [24, 24],
    iconAnchor: [12, 12],
  });
}

function movementIcon(mode: string | null): L.DivIcon {
  const symbol = mode === "air" ? "✈" : mode === "rail" ? "🚆" : mode === "road" ? "🚚" : "🚢";
  return L.divIcon({
    className: "shipment-position-icon",
    html: `<span aria-label="Simulated shipment marker">${symbol}</span>`,
    iconSize: [34, 34],
    iconAnchor: [17, 17],
  });
}

export default function GlobalNetworkMap({
  network,
  routes,
  selectedRouteId,
  disruptedLinkIds,
  modeFilters,
  movement,
  selectedLocation,
  onSelectLocation,
}: {
  network: NetworkResponse;
  routes: CandidateRoute[];
  selectedRouteId: string | null;
  disruptedLinkIds: string[];
  modeFilters: Set<string>;
  movement: ShipmentPosition | null;
  selectedLocation: NetworkNode | null;
  onSelectLocation: (location: NetworkNode) => void;
}) {
  const container = useRef<HTMLDivElement>(null);
  const map = useRef<L.Map | null>(null);
  const layers = useRef<L.LayerGroup | null>(null);

  useEffect(() => {
    if (!container.current) return;
    const instance = L.map(container.current, {
      minZoom: 1.5,
      maxZoom: 9,
      zoomControl: true,
      worldCopyJump: true,
    }).setView([28, 25], 2);
    L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
      maxZoom: 19,
      attribution:
        '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
    }).addTo(instance);
    const group = L.layerGroup().addTo(instance);
    map.current = instance;
    layers.current = group;
    const resize = window.setTimeout(() => instance.invalidateSize(), 0);
    return () => {
      window.clearTimeout(resize);
      instance.remove();
      map.current = null;
      layers.current = null;
    };
  }, []);

  useEffect(() => {
    const instance = map.current;
    const group = layers.current;
    if (!instance || !group) return;
    group.clearLayers();
    const disrupted = new Set(disruptedLinkIds);

    network.links.forEach((link) => {
      if (!modeFilters.has(link.mode)) return;
      const coordinates = link.geometry as [number, number][];
      if (coordinates.length < 2) return;
      splitAtAntimeridian(coordinates).forEach((segment) =>
        L.polyline(segment, {
          color: disrupted.has(link.id) ? "#d54646" : modeColors[link.mode] ?? "#77899b",
          opacity: disrupted.has(link.id) ? 0.9 : 0.38,
          weight: disrupted.has(link.id) ? 3 : 1.5,
          dashArray: disrupted.has(link.id) ? "8 7" : undefined,
        })
          .bindTooltip(
            `${link.mode.toUpperCase()} · ${link.distance_km?.toLocaleString() ?? "—"} km · ${link.capacity ?? "unbounded"} ${link.capacity_unit}${disrupted.has(link.id) ? " · scenario constrained" : ""}`,
          )
          .addTo(group),
      );
    });

    for (const route of routes) {
      const selected = route.id === selectedRouteId;
      if (!selected && routes.length > 4) continue;
      route.legs.forEach((leg) => {
        if (!modeFilters.has(leg.mode)) return;
        splitAtAntimeridian(leg.geometry as [number, number][]).forEach((segment) =>
          L.polyline(segment, {
            color: selected ? "#0a9b8e" : modeColors[leg.mode] ?? "#77899b",
            opacity: selected ? 0.96 : 0.42,
            weight: selected ? 5 : 2.5,
            dashArray: selected ? undefined : "5 6",
          })
            .bindTooltip(`${selected ? "Selected route" : "Alternative route"} · ${leg.mode}`)
            .addTo(group),
        );
      });
    }

    for (const node of network.nodes) {
      if (node.latitude == null || node.longitude == null) continue;
      const marker = L.marker([node.latitude, node.longitude], {
        icon: locationIcon(node.kind, selectedLocation?.id === node.id),
        keyboard: true,
        title: `${node.label} · ${node.kind.replaceAll("_", " ")}`,
      });
      marker.bindTooltip(
        `${node.label}${node.country_name ? `, ${node.country_name}` : ""} · ${node.kind.replaceAll("_", " ")}`,
      );
      marker.on("click", () => onSelectLocation(node));
      marker.addTo(group);
    }

    if (movement) {
      L.marker(movement.position, {
        icon: movementIcon(movement.current_mode),
        zIndexOffset: 1000,
        title: `Simulated shipment ${movement.status}`,
      })
        .bindTooltip(`Simulated shipment · ${movement.status.replaceAll("_", " ")}`)
        .addTo(group);
    }
  }, [
    network,
    routes,
    selectedRouteId,
    disruptedLinkIds,
    modeFilters,
    movement,
    selectedLocation,
    onSelectLocation,
  ]);

  return (
    <div
      className="global-map-frame"
      ref={container}
      role="application"
      aria-label="Interactive synthetic global logistics map"
    />
  );
}
