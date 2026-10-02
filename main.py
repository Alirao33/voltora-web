from fastapi import FastAPI, HTTPException, status
from pydantic import BaseModel
from typing import Optional

app = FastAPI()

class SmartSwapRequest(BaseModel):
    rider_id: str
    current_lat: float
    current_lng: float
    returned_pack_id: str

# Mock Locker & Station Databases
lockers_db = [
    {"station_id": "STN-KHI-03", "slot": 4, "is_private": True, "assigned_rider_id": "RDR-9021", "pack_inside": "VOLT-0554"}
]

stations_db = [
    {"id": "STN-KHI-01", "name": "Clifton Block 2 Locker", "lat": 24.8211, "lng": 67.0294, "charged_stock": 8},
    {"id": "STN-KHI-02", "name": "Gulshan-e-Iqbal Hub", "lat": 24.9180, "lng": 67.0971, "charged_stock": 3},
    {"id": "STN-KHI-03", "name": "Saddar Empress Locker", "lat": 24.8607, "lng": 67.0211, "charged_stock": 1}
]

@app.post("/api/rider/smart-swap")
def execute_smart_swap(payload: SmartSwapRequest):
    # Step 1: Check if rider has a dedicated/subscribed locker
    subscribed_locker = next(
        (l for l in lockers_db if l["assigned_rider_id"] == payload.rider_id and l["is_private"]), 
        None
    )

    if subscribed_locker:
        # OPTION 1: Subscribed Customer -> Route directly to dedicated locker
        return {
            "mode": "SUBSCRIBED_DEDICATED",
            "station_id": subscribed_locker["station_id"],
            "slot_number": subscribed_locker["slot"],
            "message": f"Welcome back! Unlocking your dedicated Door {subscribed_locker['slot']:02d}.",
            "status": "UNLOCKED"
        }

    # OPTION 2: Non-Subscribed Customer -> Automatically route to nearest station with stock
    available_stations = [s for s in stations_db if s["charged_stock"] > 0]
    
    if not available_stations:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, 
            detail="No charged batteries available across nearby stations."
        )

    # Simplified nearest station check (Euclidean distance on lat/lng)
    nearest_station = min(
        available_stations,
        key=lambda s: ((s["lat"] - payload.current_lat)**2 + (s["lng"] - payload.current_lng)**2)
    )

    return {
        "mode": "PUBLIC_NEAREST_FALLBACK",
        "station_id": nearest_station["id"],
        "station_name": nearest_station["name"],
        "slot_number": 2,  # Randomly assigned open public slot
        "message": f"No private locker found. Automatically routed to nearest station: {nearest_station['name']}.",
        "status": "UNLOCKED"
    }