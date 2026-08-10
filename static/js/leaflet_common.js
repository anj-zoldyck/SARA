/**
 * Leaflet Common Utilities
 * Shared functions for initializing Leaflet maps across the application
 */

// Initialize a basic read-only map with a marker at given coordinates
// Returns the map instance for further customization if needed
function initReadOnlyMap(elementId, lat, lng, zoom = 16) {
    if (!lat || !lng) {
        console.error('initReadOnlyMap: Invalid coordinates provided');
        return null;
    }

    const map = L.map(elementId).setView([lat, lng], zoom);

    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
        maxZoom: 19,
        attribution: '&copy; OpenStreetMap'
    }).addTo(map);

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
