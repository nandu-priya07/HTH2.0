from .geo_resolver import GeoResolver

def build_map_data(df, rows, dimension, profile):
    resolver = GeoResolver()
    names = [r[dimension] for r in rows]
    entity_type=next((c["entity_type"] for c in profile["geographic_columns"] if c["column"]==dimension),"location")
    resolved, unresolved = resolver.resolve_geometry_names(names) if entity_type == "country" else ({}, len(names))
    locations=[]
    for row in rows:
        geometry = resolved.get(row[dimension])
        if geometry:
            locations.append({"name":row[dimension],"entity_type":entity_type,"metric":row["metric"],"rank":row["rank"],"contribution":row["contribution"],**geometry})
    # For non-country geographies, use only coordinates actually supplied by the dataset.
    if not locations:
        coords, unresolved = resolver.resolve_dataset_coordinates(df, dimension, names)
        for row in rows:
            point=coords.get(row[dimension])
            if point: locations.append({"name":row[dimension],"entity_type":entity_type,"metric":row["metric"],"rank":row["rank"],"contribution":row["contribution"],**point})
    return locations, unresolved
