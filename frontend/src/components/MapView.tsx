import { GoogleMap, Marker, LoadScript } from '@react-google-maps/api';
import type { SearchResult, ComparisonSummary } from '../types/api';

interface Props {
  results: SearchResult[];
  comparisonSummary?: ComparisonSummary;
  selectedCityId: number | null;
  onCitySelect: (id: number) => void;
}

const MAP_CENTER = { lat: 40.4, lng: -3.7 }; // Spain center
const MAP_CONTAINER_STYLE = { width: '100%', height: '100%' };

function confidenceToColor(confidence: number): string {
  // 0 → red (hsl 0), 0.5 → yellow (hsl 60), 1 → green (hsl 120)
  const hue = Math.round(confidence * 120);
  return `hsl(${hue}, 90%, 45%)`;
}

export function MapView({ results, comparisonSummary, selectedCityId, onCitySelect }: Props) {
  const apiKey = import.meta.env.VITE_GOOGLE_MAPS_JS_KEY ?? '';
  const addedSet = new Set(comparisonSummary?.added_cities ?? []);

  return (
    <LoadScript googleMapsApiKey={apiKey} loadingElement={<div style={{ height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>Loading map…</div>}>
      <GoogleMap
        mapContainerStyle={MAP_CONTAINER_STYLE}
        center={MAP_CENTER}
        zoom={6}
        options={{ streetViewControl: false, mapTypeControl: false }}
      >
        {results.map(result => {
          const isSelected = result.city_id === selectedCityId;
          const isAdded = addedSet.has(result.city_id);
          const color = confidenceToColor(result.overall_confidence);
          const label = isAdded ? `★ ${result.city_name}` : result.city_name;

          return (
            <Marker
              key={result.city_id}
              position={{ lat: result.lat, lng: result.lon }}
              title={label}
              label={{
                text: isAdded ? '★' : '',
                color: '#fff',
                fontSize: '14px',
              }}
              icon={{
                path: google.maps.SymbolPath.CIRCLE,
                fillColor: color,
                fillOpacity: 0.85,
                strokeColor: isSelected ? '#1d4ed8' : '#fff',
                strokeWeight: isSelected ? 3 : 1.5,
                scale: isSelected ? 14 : 10,
              }}
              onClick={() => onCitySelect(result.city_id)}
            />
          );
        })}
      </GoogleMap>
    </LoadScript>
  );
}
