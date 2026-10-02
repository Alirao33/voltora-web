from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List

app = FastAPI(
    title="Voltora Smart E-Bike Battery Swap API",
    description="Backend engine supporting dual-mode locker routing, automatic non-subscriber fallback, dynamic pricing, and battery telemetry.",
    version="2.0.0"
)

# CORS configuration for frontend communication
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- In-Memory State & Databases ---

admin_credentials = {
    "key": "karachi2026",
    "otp": "882109"
}

pricing_formula = {
    "grid_tariff": 65.0,
    "fixed_overhead": 30.0,
    "lfp_wear": 6.0,
    "margin_multiplier": 1.20
}

stations_db = [
    {"id": "STN-KHI-01", "name": "Clifton Block 2 Locker", "lat": 24.8211, "lng": 67.0294, "charged_stock": 8, "total_slots": 10},
    {"id": "STN-KHI-02", "name": "Gulshan-e-Iqbal Hub", "lat": 24.9180, "lng": 67.0971, "charged_stock": 3, "total_slots": 12},
    {"id": "STN-KHI-03", "name": "Saddar Empress Locker", "lat": 24.8607, "lng": 67.0211, "charged_stock": 1, "total_slots": 10}
]

lockers_db = [
    {"station_id": "STN-KHI-03", "slot": 4, "is_private": True, "assigned_rider_id": "RDR-9021", "pack_inside": "VOLT-0554"},
    {"station_id": "STN-KHI-01", "slot": 2, "is_private": False, "assigned_rider_id": None, "pack_inside": "VOLT-0821"},
    {"station_id": "STN-KHI-02", "slot": 1, "is_private": False, "assigned_rider_id": None, "pack_inside": "VOLT-0412"}
]

batteries_db = [
    {"pack_id": "VOLT-0821", "soc": 92, "soh": 92, "temp": 38.5, "score": 88.5, "status": "Normal"},
    {"pack_id": "VOLT-0412", "soc": 45, "soh": 78, "temp": 41.0, "score": 74.2, "status": "Warning"},
    {"pack_id": "VOLT-0199", "soc": 12, "soh": 62, "temp": 56.2, "score": 48.0, "status": "Lockout"},
    {"pack_id": "VOLT-0554", "soc": 98, "soh": 95, "temp": 36.0, "score": 94.0, "status": "Normal"}
]

recent_swaps = [
    {"id": "ORD-9021", "rider": "Tariq Mahmood (#RDR-9021)", "cost": "117.79 PKR"},
    {"id": "ORD-9022", "rider": "Delivery Partner (#RDR-4402)", "cost": "357.35 PKR"}
]

# --- Request Models ---

class AdminLoginRequest(BaseModel):
    role: str
    admin_key: str
    otp_code: str

class DedicatedAssignRequest(BaseModel):
    station_id: str
    slot_number: int
    rider_id: str

class SwapRequest(BaseModel):
    rider_id: str
    station_id: str
    returned_pack_id: str

class SmartSwapRequest(BaseModel):
    rider_id: str
    current_lat: float = 24.8607
    current_lng: float = 67.0211
    returned_pack_id: str

class MaintenanceRequest(BaseModel):
    action: str

class PricingFormulaRequest(BaseModel):
    grid_tariff: float
    fixed_overhead: float
    lfp_wear: float
    margin_multiplier: float

class RefundRequest(BaseModel):
    order_id: str
    reason: Optional[str] = "Customer Satisfaction"

# --- API Routes ---

@app.post("/api/admin/login")
def admin_login(payload: AdminLoginRequest):
    if payload.admin_key == admin_credentials["key"] and payload.otp_code == admin_credentials["otp"]:
        return {"status": "success", "role": payload.role}
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid credentials or 2FA OTP code."
    )

@app.get("/api/admin/stats")
def get_dashboard_stats():
    charged_stock_count = sum(s["charged_stock"] for s in stations_db)
    total_slots_count = sum(s["total_slots"] for s in stations_db)
    flagged_count = len([b for b in batteries_db if b["status"] in ["Warning", "Lockout"]])

    return {
        "total_revenue_pkr": 148920,
        "active_stations": len(stations_db),
        "charged_stock": f"{charged_stock_count} / {total_slots_count} Packs",
        "flagged_packs": f"{flagged_count} Packs"
    }

@app.get("/api/admin/swaps")
def get_recent_swaps():
    return {"swaps": recent_swaps}

@app.post("/api/admin/lockers/assign-private")
def assign_private_locker(payload: DedicatedAssignRequest):
    locker = next((l for l in lockers_db if l["station_id"] == payload.station_id and l["slot"] == payload.slot_number), None)
    if locker:
        locker["is_private"] = True
        locker["assigned_rider_id"] = payload.rider_id
    else:
        lockers_db.append({
            "station_id": payload.station_id,
            "slot": payload.slot_number,
            "is_private": True,
            "assigned_rider_id": payload.rider_id,
            "pack_inside": "VOLT-0554"
        })
    return {
        "status": "success",
        "message": f"Slot {payload.slot_number} reserved for Rider {payload.rider_id}."
    }

@app.post("/api/rider/swap-dedicated")
def execute_dedicated_swap(payload: SwapRequest):
    locker = next((l for l in lockers_db if l["assigned_rider_id"] == payload.rider_id and l["is_private"]), None)
    if not locker:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No dedicated locker subscription found for this rider."
        )

    return {
        "status": "success",
        "mode": "SUBSCRIBED_DEDICATED",
        "station_id": locker["station_id"],
        "slot": locker["slot"],
        "released_pack": locker["pack_inside"]
    }

@app.post("/api/rider/swap")
def execute_public_swap(payload: SwapRequest):
    return {
        "status": "success",
        "mode": "PUBLIC_NEAREST",
        "station_id": payload.station_id,
        "slot": 2,
        "released_pack": "VOLT-0821",
        "cost_pkr": 117.79
    }

@app.post("/api/rider/smart-swap")
def execute_smart_swap(payload: SmartSwapRequest):
    subscribed_locker = next(
        (l for l in lockers_db if l["assigned_rider_id"] == payload.rider_id and l["is_private"]),
        None
    )

    if subscribed_locker:
        return {
            "status": "success",
            "routing_mode": "SUBSCRIBED_DEDICATED",
            "station_id": subscribed_locker["station_id"],
            "slot_number": subscribed_locker["slot"],
            "released_pack": subscribed_locker["pack_inside"],
            "message": f"Subscribed VIP Access: Unlocked private Door {subscribed_locker['slot']:02d}."
        }

    available_stations = [s for s in stations_db if s["charged_stock"] > 0]
    if not available_stations:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="All nearby swapping stations currently depleted."
        )

    nearest = min(
        available_stations,
        key=lambda s: ((s["lat"] - payload.current_lat)**2 + (s["lng"] - payload.current_lng)**2)
    )

    return {
        "status": "success",
        "routing_mode": "PUBLIC_NEAREST_FALLBACK",
        "station_id": nearest["id"],
        "station_name": nearest["name"],
        "slot_number": 2,
        "released_pack": "VOLT-0821",
        "message": f"Non-subscribed user automatically routed to nearest station: {nearest['name']} (Door 02)."
    }

@app.post("/api/admin/batteries/{pack_id}/maintenance")
def update_battery_health(pack_id: str, payload: MaintenanceRequest):
    battery = next((b for b in batteries_db if b["pack_id"] == pack_id), None)
    if not battery:
        raise HTTPException(status_code=404, detail="Pack not found.")
    
    battery["status"] = "Warning" if payload.action == "FLAG_MAINTENANCE" else "Lockout"
    return {"status": "success", "pack_id": pack_id, "new_status": battery["status"]}

@app.post("/api/admin/pricing")
def update_pricing_formula(payload: PricingFormulaRequest):
    pricing_formula.update(payload.dict())
    return {"status": "success", "updated_formula": pricing_formula}

@app.post("/api/admin/refund")
def process_refund(payload: RefundRequest):
    return {
        "status": "success",
        "order_id": payload.order_id,
        "refund_amount_pkr": 357.35,
        "gateway": "Raast Sandbox"
    }