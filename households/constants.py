OSM_TO_DB_BARANGAY_NAME = {
    "San Jose": "San Jose (Poblacion)",
    "Dila-dila": "Dila-Dila",
}

# PAGASA Tropical Cyclone Wind Signal (TCWS) thresholds, 10-minute sustained wind speed in km/h
# Source: PAGASA TCWS system (revised March 2022)
TCWS_THRESHOLDS = [
    (39, 61, 1),    # Signal No. 1: 39-61 km/h
    (62, 88, 2),    # Signal No. 2: 62-88 km/h
    (89, 117, 3),   # Signal No. 3: 89-117 km/h
    (118, 184, 4),  # Signal No. 4: 118-184 km/h
    (185, float('inf'), 5),  # Signal No. 5: 185+ km/h (super typhoon range)
]

def get_tcws_signal(wind_speed_kmh):
    """Returns the TCWS signal number (1-5) for a given wind speed, or None if below Signal 1 threshold."""
    for lower, upper, signal in TCWS_THRESHOLDS:
        if lower <= wind_speed_kmh <= upper:
            return signal
    return None  # below 39 km/h — no active signal
