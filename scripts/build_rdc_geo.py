"""
Construit frontend/public/geo/rdc-provinces.json (contours des 26 provinces de la RDC) à partir de
geoBoundaries COD ADM1 (licence ODbL 1.0) :
    https://github.com/wmgeolab/geoBoundaries/raw/9469f09/releaseData/gbOpen/COD/ADM1/geoBoundaries-COD-ADM1_simplified.geojson

Usage : python scripts/build_rdc_geo.py <fichier geojson téléchargé> [--tolerance 0.01]
Simplification Douglas-Peucker + arrondi des coordonnées : ~1,1 Mo -> ~150 Ko.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

OUT = Path(__file__).resolve().parents[1] / "frontend" / "public" / "geo" / "rdc-provinces.json"

# Code ISO 3166-2 -> nom utilisé par les opérateurs et dans frontend/lib/geo.ts
ISO_TO_NAME = {
    "CD-KN": "Kinshasa", "CD-BC": "Kongo-Central", "CD-KG": "Kwango", "CD-KL": "Kwilu", "CD-MN": "Mai-Ndombe",
    "CD-KS": "Kasaï", "CD-KC": "Kasaï-Central", "CD-KE": "Kasaï-Oriental", "CD-LO": "Lomami", "CD-SA": "Sankuru",
    "CD-MA": "Maniema", "CD-SK": "Sud-Kivu", "CD-NK": "Nord-Kivu", "CD-IT": "Ituri", "CD-HU": "Haut-Uele",
    "CD-BU": "Bas-Uele", "CD-TO": "Tshopo", "CD-TU": "Tshuapa", "CD-MO": "Mongala", "CD-NU": "Nord-Ubangi",
    "CD-SU": "Sud-Ubangi", "CD-EQ": "Équateur", "CD-HL": "Haut-Lomami", "CD-LU": "Lualaba",
    "CD-HK": "Haut-Katanga", "CD-TA": "Tanganyika",
}


def _dist(p, a, b) -> float:
    """Distance du point p au segment [a, b] (degrés, suffisant à cette échelle)."""
    (x, y), (x1, y1), (x2, y2) = p, a, b
    dx, dy = x2 - x1, y2 - y1
    if dx == dy == 0:
        return ((x - x1) ** 2 + (y - y1) ** 2) ** 0.5
    t = max(0.0, min(1.0, ((x - x1) * dx + (y - y1) * dy) / (dx * dx + dy * dy)))
    return ((x - x1 - t * dx) ** 2 + (y - y1 - t * dy) ** 2) ** 0.5


def simplify(points: list, tol: float) -> list:
    """Douglas-Peucker itératif (pas de récursion profonde sur les longs contours)."""
    keep = [False] * len(points)
    keep[0] = keep[-1] = True
    stack = [(0, len(points) - 1)]
    while stack:
        i, j = stack.pop()
        best, idx = 0.0, -1
        for k in range(i + 1, j):
            d = _dist(points[k], points[i], points[j])
            if d > best:
                best, idx = d, k
        if best > tol:
            keep[idx] = True
            stack += [(i, idx), (idx, j)]
    return [p for p, k in zip(points, keep) if k]


def simplify_ring(ring: list, tol: float) -> list | None:
    out = [[round(x, 3), round(y, 3)] for x, y in simplify(ring, tol)]
    return out if len(out) >= 4 else None   # anneau fermé : au moins 3 sommets + retour au départ


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("source")
    ap.add_argument("--tolerance", type=float, default=0.01)
    args = ap.parse_args()

    src = json.loads(Path(args.source).read_text(encoding="utf-8"))
    features = []
    for f in src["features"]:
        iso = f["properties"]["shapeISO"]
        geom = f["geometry"]
        polys = geom["coordinates"] if geom["type"] == "MultiPolygon" else [geom["coordinates"]]
        out = []
        for poly in polys:
            rings = [r for r in (simplify_ring(r, args.tolerance) for r in poly) if r]
            if rings:
                out.append(rings)
        features.append({"type": "Feature", "properties": {"name": ISO_TO_NAME[iso], "iso": iso},
                         "geometry": {"type": "MultiPolygon", "coordinates": out}})
    assert len(features) == 26, f"{len(features)} provinces au lieu de 26"

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({
        "type": "FeatureCollection",
        "attribution": "geoBoundaries (wmgeolab, William & Mary), COD ADM1, licence ODbL 1.0",
        "features": features,
    }, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"{OUT} : {len(features)} provinces, {OUT.stat().st_size / 1024:.0f} Ko")


if __name__ == "__main__":
    main()
