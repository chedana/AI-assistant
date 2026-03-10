import L from 'leaflet';
import { MapContainer, TileLayer, Marker, Popup, useMap } from 'react-leaflet';
import { useEffect } from 'react';
import type { ListingData } from '../types/chat';

// Create a custom modern marker icon using DivIcon
const createCustomIcon = (price: number) => {
  return L.divIcon({
    className: 'custom-map-marker',
    html: `
      <div class="flex items-center justify-center bg-emerald-600 text-white px-2.5 py-1.5 rounded-xl shadow-xl border-2 border-white/20 font-bold text-xs whitespace-nowrap transform -translate-x-1/2 -translate-y-1/2 hover:scale-110 transition-transform active:scale-95 hover:bg-emerald-500 ring-2 ring-black/10">
        £${(price / 1000).toFixed(1)}k
      </div>
    `,
    iconSize: [0, 0], 
    iconAnchor: [0, 0],
  });
};

// Internal component to handle automatic map bounds fitting
function FitBounds({ listings }: { listings: ListingData[] }) {
  const map = useMap();

  useEffect(() => {
    // Collect all valid lat/lon points
    const points = listings
      .filter(l => typeof l.lat === 'number' && typeof l.lon === 'number')
      .map(l => [l.lat!, l.lon!] as [number, number]);

    if (points.length > 0) {
      const bounds = L.latLngBounds(points);
      map.fitBounds(bounds, { 
        padding: [50, 50], 
        maxZoom: 16,
        animate: true,
        duration: 1
      });
    }
  }, [listings, map]);

  return null;
}

interface MapViewProps {
  listings: ListingData[];
  onListingClick?: (listing: ListingData) => void;
}

export default function MapView({ listings, onListingClick }: MapViewProps) {
  // Defensive check: extract listings with valid coordinates
  const validListings = listings.filter(
    (l) => typeof l.lat === 'number' && typeof l.lon === 'number'
  );

  // If no listings have lat/lon, show a helpful message instead of a blank map
  if (validListings.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center h-full w-full bg-[#0a0a0a] text-neutral-500 p-8 text-center animate-fade-in-up">
        <div className="w-16 h-16 rounded-full bg-white/5 flex items-center justify-center mb-6">
          <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" className="opacity-40">
            <path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z" />
            <circle cx="12" cy="10" r="3" />
          </svg>
        </div>
        <p className="text-sm font-bold text-text mb-1">No Location Data Found</p>
        <p className="text-xs max-w-xs leading-relaxed opacity-60">
          The property listings in this search don't have geographic coordinates available to display on the map.
        </p>
      </div>
    );
  }

  return (
    <div className="w-full h-full relative group">
      {/* Inline styles for Leaflet UI elements to match dark theme */}
      <style>{`
        .leaflet-container {
          background: #0a0a0a !important;
          width: 100%;
          height: 100%;
          font-family: inherit;
        }
        .leaflet-popup-content-wrapper {
          background: #141414 !important;
          color: #f8fafc !important;
          border-radius: 16px !important;
          padding: 0 !important;
          overflow: hidden !important;
          border: 1px solid #262626 !important;
          box-shadow: 0 10px 25px -5px rgba(0, 0, 0, 0.5) !important;
        }
        .leaflet-popup-content {
          margin: 0 !important;
          width: 260px !important;
        }
        .leaflet-popup-tip {
          background: #141414 !important;
          border: 1px solid #262626;
        }
        .leaflet-control-zoom {
          border: 1px solid #262626 !important;
          border-radius: 12px !important;
          overflow: hidden !important;
          margin-top: 20px !important;
          margin-left: 20px !important;
        }
        .leaflet-control-zoom-in, .leaflet-control-zoom-out {
          background: #141414 !important;
          color: #f8fafc !important;
          border-bottom: 1px solid #262626 !important;
          width: 36px !important;
          height: 36px !important;
          line-height: 36px !important;
          transition: background 0.2s;
        }
        .leaflet-control-zoom-in:hover, .leaflet-control-zoom-out:hover {
          background: #262626 !important;
          color: #10b981 !important;
        }
        .leaflet-bar a.leaflet-disabled {
          background: #0a0a0a !important;
          color: #404040 !important;
        }
      `}</style>
      
      <MapContainer
        center={[51.505, -0.09]}
        zoom={13}
        scrollWheelZoom={true}
        zoomControl={true}
        attributionControl={false}
        className="w-full h-full z-0"
      >
        <TileLayer
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors &copy; <a href="https://carto.com/attributions">CARTO</a>'
          url="https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png"
        />
        
        {validListings.map((listing, idx) => (
          <Marker
            key={`${listing.url}-${idx}`}
            position={[listing.lat!, listing.lon!]}
            icon={createCustomIcon(listing.price_pcm)}
          >
            <Popup closeButton={false} offset={[0, -10]}>
              <div className="flex flex-col group/popup">
                <div className="h-32 w-full overflow-hidden bg-neutral-800">
                  {listing.image_url ? (
                    <img 
                      src={listing.image_url} 
                      alt={listing.title} 
                      className="w-full h-full object-cover transition-transform group-hover/popup:scale-110 duration-700"
                    />
                  ) : (
                    <div className="w-full h-full flex items-center justify-center text-neutral-600">
                      <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><rect x="3" y="3" width="18" height="18" rx="2" ry="2"/><circle cx="8.5" cy="8.5" r="1.5"/><polyline points="21 15 16 10 5 21"/></svg>
                    </div>
                  )}
                </div>
                <div className="p-4">
                  <div className="text-[10px] uppercase tracking-widest text-emerald-500 font-bold mb-1">
                    {listing.property_type || 'Property'}
                  </div>
                  <div className="text-sm font-bold truncate text-white mb-2 leading-tight">
                    {listing.title}
                  </div>
                  <div className="flex items-center justify-between mb-4">
                    <div className="text-white font-black text-base">
                      £{listing.price_pcm.toLocaleString()} <span className="text-[10px] text-neutral-500 font-normal uppercase tracking-tighter">pcm</span>
                    </div>
                    <div className="flex gap-2 text-[11px] font-bold text-neutral-400">
                      <span>{listing.bedrooms} <span className="text-[9px] font-medium opacity-60">BD</span></span>
                      <span>{listing.bathrooms} <span className="text-[9px] font-medium opacity-60">BA</span></span>
                    </div>
                  </div>
                  <button 
                    onClick={(e) => {
                      e.stopPropagation();
                      onListingClick?.(listing);
                    }}
                    className="w-full bg-emerald-600 hover:bg-emerald-500 text-white text-[11px] font-black uppercase tracking-widest py-2.5 rounded-lg transition-all shadow-lg shadow-emerald-900/20 active:scale-[0.98]"
                  >
                    Details
                  </button>
                </div>
              </div>
            </Popup>
          </Marker>
        ))}
        
        <FitBounds listings={validListings} />
      </MapContainer>
    </div>
  );
}
