/**
 * Leaflet Common Utilities
 * Shared functions for initializing Leaflet maps across the application
 */

// Centralized tile layer configuration
// NOTE: Using MapTiler (OSM-based, 256x256 XYZ) instead of Esri or CARTO.
// - CARTO now requires an API key for their basemaps.cartocdn.com endpoint (policy change), which would cause "API KEY REQUIRED" watermarks.
// - Esri World Street Map lacks detailed local POI data (e.g., Santa Rita Town Plaza, San Matias Covered Court) that was visible under OSM-based tiles.
// - MapTiler provides OSM-based tiles with strong Philippine local mapping coverage, free tier with registered API key, and no anonymous-access risk.
// The API key is loaded from environment variables (MAPTILER_API_KEY) and injected via window.MAPTILER_API_KEY, not hardcoded.
const LEAFLET_TILE_CONFIG = {
    url: `https://api.maptiler.com/maps/streets-v2/{z}/{x}/{y}.png?key=${window.MAPTILER_API_KEY}`,
    options: {
        attribution: '\u003ca href="https://www.maptiler.com/copyright/" target="_blank"\u003e© MapTiler\u003c/a\u003e \u003ca href="https://www.openstreetmap.org/copyright" target="_blank"\u003e© OpenStreetMap contributors\u003c/a\u003e',
        maxZoom: 20
    }
};

// MSWDO Office coordinates for route preview
const MSWDO_OFFICE_COORDS = [15.000328483552574, 120.61805645102072];

// Show offline error message on a map container
function showMapOfflineError(mapElementId, message = null) {
    const mapElement = document.getElementById(mapElementId);
    if (!mapElement) return;

    // Remove existing error message if any
    hideMapOfflineError(mapElementId);

    const errorMessage = message || 'Map unavailable — an internet connection is required to view maps. Please connect to WiFi or a mobile hotspot with active internet access, then refresh the page.';

    const errorDiv = document.createElement('div');
    errorDiv.id = `${mapElementId}-offline-error`;
    errorDiv.className = 'map-offline-error';
    errorDiv.innerHTML = `
        <div class="map-offline-error-content">
            <i class="bi bi-wifi-off"></i>
            <p>${errorMessage}</p>
        </div>
    `;

    // Insert error message before the map element
    mapElement.parentNode.insertBefore(errorDiv, mapElement);
}

// Hide offline error message from a map container
function hideMapOfflineError(mapElementId) {
    const errorDiv = document.getElementById(`${mapElementId}-offline-error`);
    if (errorDiv) {
        errorDiv.remove();
    }
}

// Show route offline error message
function showRouteOfflineError(routeInfoElementId) {
    const routeInfo = document.getElementById(routeInfoElementId);
    if (!routeInfo) return;

    routeInfo.classList.add('show', 'route-error');
    routeInfo.innerHTML = '<i class="bi bi-wifi-off"></i> Route preview unavailable — requires an internet connection.';
}

// Hide route offline error message
function hideRouteOfflineError(routeInfoElementId) {
    const routeInfo = document.getElementById(routeInfoElementId);
    if (!routeInfo) return;

    routeInfo.classList.remove('route-error');
}

// Initialize a basic read-only map with a marker at given coordinates
// Returns the map instance for further customization if needed
// zoom parameter: 16-18 for single-pin views (close-up), 13-15 for multi-pin views (wider area)
function initReadOnlyMap(elementId, lat, lng, zoom = 17) {
    if (!lat || !lng) {
        console.error('initReadOnlyMap: Invalid coordinates provided');
        return null;
    }

    const map = L.map(elementId).setView([lat, lng], zoom);

    const tileLayer = L.tileLayer(LEAFLET_TILE_CONFIG.url, LEAFLET_TILE_CONFIG.options);

    // Detect tile loading errors (offline, network failure)
    tileLayer.on('tileerror', function(error) {
        console.error('Tile loading error:', error);
        showMapOfflineError(elementId);
    });

    // Hide error if tiles start loading successfully
    tileLayer.on('load', function() {
        hideMapOfflineError(elementId);
    });

    tileLayer.addTo(map);

    // Default blue marker icon
    const markerIcon = L.divIcon({
        className: 'custom-div-icon',
        html: `
            <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="#0d47a1" width="32px" height="32px">
                <path d="M12 2C8.13 2 5 5.13 5 9c0 5.25 7 13 7 13s7-7.75 7-13c0-3.87-3.13-7-7-7zm0 9.5c-1.38 0-2.5-1.12-2.5-2.5s1.12-2.5 2.5-2.5 2.5 1.12 2.5 2.5-1.12 2.5-2.5 2.5z"/>
                <path d="M0 0h24v24H0z" fill="none"/>
            </svg>`,
        iconSize: [32, 32],
        iconAnchor: [16, 32],
        popupAnchor: [0, -32]
    });

    L.marker([lat, lng], { icon: markerIcon }).addTo(map);

    // Fix leaflet map not loading fully inside some wrappers/modals
    setTimeout(function() {
        map.invalidateSize();
    }, 100);

    return map;
}

// Add route preview from MSWDO Office to a destination
// Requires Leaflet Routing Machine to be loaded
// Returns the routing control instance for cleanup if needed
function addRoutePreview(map, destLat, destLng, routeInfoElementId = null) {
    if (!map || !destLat || !destLng) {
        console.error('addRoutePreview: Invalid parameters');
        return null;
    }

    // Remove existing routing control if any
    if (map._routingControl) {
        map.removeControl(map._routingControl);
    }

    // Hide any previous route error
    if (routeInfoElementId) {
        hideRouteOfflineError(routeInfoElementId);
    }

    // Create new route using OSRM
    const routingControl = L.Routing.control({
        waypoints: [
            L.latLng(MSWDO_OFFICE_COORDS[0], MSWDO_OFFICE_COORDS[1]),
            L.latLng(destLat, destLng)
        ],
        router: L.Routing.osrmv1({
            serviceUrl: 'https://router.project-osrm.org/route/v1'
        }),
        routeWhileDragging: false,
        addWaypoints: false,
        draggableWaypoints: false,
        fitSelectedRoutes: true,
        showAlternatives: false,
        lineOptions: {
            styles: [{ color: '#0d47a1', weight: 5, opacity: 0.7 }]
        },
        createMarker: function() { return null; }  // Don't show routing markers
    });

    // Detect routing errors (offline, network failure)
    routingControl.on('routingerror', function(error) {
        console.error('Routing error:', error);
        if (routeInfoElementId) {
            showRouteOfflineError(routeInfoElementId);
        }
    });

    // Update route info banner on successful route
    routingControl.on('routesfound', function() {
        if (routeInfoElementId) {
            const routeInfo = document.getElementById(routeInfoElementId);
            if (routeInfo) {
                routeInfo.classList.add('show');
                routeInfo.classList.remove('route-error');
                routeInfo.innerHTML = '<i class="bi bi-signpost"></i> Route preview from MSWDO Office to selected location';
            }
        }
    });

    routingControl.addTo(map);

    // Store reference for cleanup
    map._routingControl = routingControl;

    return routingControl;
}

// Remove route preview from a map
function removeRoutePreview(map) {
    if (map && map._routingControl) {
        map.removeControl(map._routingControl);
        map._routingControl = null;
    }
}
