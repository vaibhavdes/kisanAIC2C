"""Adds one public example farm to each live node, through the public API, so anyone can open a filled-in farm.

Each farm is typical of its region: a black-soil soybean field in Yavatmal (Maharashtra), an irrigated rice-wheat
field in Ludhiana (Punjab) and a clay soybean field in Pato Branco (Paraná). Soil values are typical of each region's
soil-test results, not a real farmer's report. The script is idempotent: a farm that already exists is left alone.

Usage: python services/api/scripts/seed_public_farms.py [in-mh|in-north|br-pr ...]
"""
import json
import math
import sys
import urllib.request

OWNER = "dev-kisanai-field-examples"  # anonymous device id that owns the example farms
TIMEOUT = 300

NODES = {
    "in-mh": ("https://kisanai-in-mh-313370978552.asia-south1.run.app", "mr-IN", {
        "name": "Zadgaon soybean field", "village": "Zadgaon", "district": "Yavatmal",
        "state_code": "MH", "state_name": "Maharashtra", "country_code": "IN", "center": (20.4210, 78.0550), "hectares": 2.0,
        "water_access": "rainfed", "soil_type": "black", "previous_crop": "soybean",
        # Typical Soil Health Card result for Yavatmal black soils (Vertisols)
        "soil": {"ph": 7.9, "ec_ds_m": 0.28, "organic_carbon_percent": 0.42, "nitrogen_kg_ha": 188, "phosphorus_kg_ha": 13.5,
                 "potassium_kg_ha": 395, "sulphur_ppm": 9.2, "zinc_ppm": 0.52, "iron_ppm": 5.1, "copper_ppm": 1.6,
                 "manganese_ppm": 8.4, "boron_ppm": 0.46},
        "lab": "Soil Health Card, Yavatmal",
    }),
    "in-north": ("https://kisanai-in-north-313370978552.asia-south2.run.app", "hi-IN", {
        "name": "Ludhiana rice-wheat field", "village": None, "district": "Ludhiana",
        "state_code": "PB", "state_name": "Punjab", "country_code": "IN", "center": (30.8820, 75.7250), "hectares": 2.5,
        "water_access": "irrigated", "soil_type": "alluvial", "previous_crop": "rice",
        # Typical Soil Health Card result for central Punjab alluvial loams
        "soil": {"ph": 8.1, "ec_ds_m": 0.35, "organic_carbon_percent": 0.38, "nitrogen_kg_ha": 210, "phosphorus_kg_ha": 24,
                 "potassium_kg_ha": 185, "sulphur_ppm": 11.5, "zinc_ppm": 0.58, "iron_ppm": 7.2, "copper_ppm": 0.9,
                 "manganese_ppm": 6.5, "boron_ppm": 0.55},
        "lab": "Soil Health Card, Ludhiana",
    }),
    "br-pr": ("https://kisanai-br-pr-313370978552.southamerica-east1.run.app", "pt-BR", {
        "name": "Lavoura de soja - Pato Branco", "village": None, "district": "Pato Branco",
        "state_code": "PR", "state_name": "Paraná", "country_code": "BR", "center": (-26.2400, -52.7000), "hectares": 3.0,
        "water_access": "rainfed", "soil_type": "clay", "previous_crop": "wheat",
        # Typical lab result for south-west Paraná clay soils (Latossolo/Nitossolo)
        "soil": {"ph": 5.6, "clay_percent": 60, "organic_matter_g_dm3": 38, "phosphorus_mehlich_mg_dm3": 4.5, "potassium_mg_dm3": 58},
        "lab": "Laboratório de solos (exemplo)",
    }),
}


def call(base, method, path, body=None):
    request = urllib.request.Request(base + path, method=method, data=json.dumps(body).encode() if body is not None else None,
                                     headers={"X-Actor-Id": OWNER, "Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
        text = response.read().decode()
        return json.loads(text) if text else None


def square(center, hectares):
    """Corner coordinates of a square field of the given area around its centre."""
    lat, lon = center
    half = math.sqrt(hectares * 10000) / 2
    dlat, dlon = half / 111320, half / (111320 * math.cos(math.radians(lat)))
    return [[lat + dlat, lon - dlon], [lat + dlat, lon + dlon], [lat - dlat, lon + dlon], [lat - dlat, lon - dlon]]


def seed(key):
    base, locale, spec = NODES[key]
    existing = next((f for f in call(base, "GET", "/api/v1/farms") if f["name"] == spec["name"] and f.get("is_mine")), None)
    if existing:
        print(f"{key}: '{spec['name']}' already exists ({existing['id']})")
        return
    farm = call(base, "POST", "/api/v1/farms", {
        "name": spec["name"], "country_code": spec["country_code"], "state_code": spec["state_code"], "state_name": spec["state_name"],
        "district": spec["district"], "village": spec["village"], "boundary_coordinates": square(spec["center"], spec["hectares"]),
        "area_value": spec["hectares"], "area_unit": "hectare",
        "location": {"latitude": spec["center"][0], "longitude": spec["center"][1], "source": "farmer", "confirmed": True},
        "water_access": spec["water_access"], "soil_type": spec["soil_type"], "previous_crop": spec["previous_crop"],
        "crop_status": "planning", "visibility": "public",
    })
    print(f"{key}: farm {farm['id']}")
    call(base, "POST", f"/api/v1/farms/{farm['id']}/soil", {"values": spec["soil"], "lab_name": spec["lab"], "source": "manual", "confirmed": True})
    call(base, "POST", f"/api/v1/farms/{farm['id']}/evidence/refresh")
    crops = call(base, "GET", f"/api/v1/farms/{farm['id']}/crop-recommendations?locale={locale}")
    print(f"{key}: {len(crops.get('sow_now', []))} crops to sow now, {len(crops.get('upcoming', []))} upcoming")
    plan = call(base, "POST", f"/api/v1/farms/{farm['id']}/advisories", {"goal": "crop_plan", "locale": locale})
    print(f"{key}: plan {plan['id']} with {len(plan.get('actions', []))} steps")


if __name__ == "__main__":
    for node in sys.argv[1:] or list(NODES):
        seed(node)
