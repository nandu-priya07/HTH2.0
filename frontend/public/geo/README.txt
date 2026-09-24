The Explorer map boundary file is Natural Earth 1:110m Admin 0 country geography,
from https://github.com/nvkelso/natural-earth-vector/blob/master/geojson/ne_110m_admin_0_countries.geojson.
Natural Earth data is public domain. It supplies polygon geometry and country metadata only;
all displayed metrics and ranked locations are calculated from the selected chat dataset.

Admin-1 state/province features are loaded lazily by the backend boundary provider from
the bundled Natural Earth 1:50m public-domain layer:
https://github.com/nvkelso/natural-earth-vector/blob/master/geojson/ne_50m_admin_1_states_provinces.geojson
When a country/subdivision is not in that layer, the provider falls back to the official
geoBoundaries gbOpen API for that parent country and admin level. Its attribution and
license are returned with the map data and shown in the Explorer. For private deployments,
set QUERYLENS_ADMIN_BOUNDARIES_GEOJSON to a local GeoJSON FeatureCollection with admin-1
features. The provider joins by subdivision and parent country; it never creates replacement
geometry.
