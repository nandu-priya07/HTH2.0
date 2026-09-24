from .geo_resolver import GeoBoundaryProvider, GeoResolver

def build_map_data(df, rows, dimension, profile):
    resolver = GeoResolver()
    boundary_provider=GeoBoundaryProvider(resolver)
    names = [r[dimension] for r in rows]
    entity_type=next((c["entity_type"] for c in profile["geographic_columns"] if c["column"]==dimension),"location")
    resolved, unresolved = resolver.resolve_geometry_names(names) if entity_type == "country" else ({}, len(names))
    resolved_admin={}
    boundary_features=[]
    if entity_type != "country":
        for row in rows:
            parent_values=row.get("parents") or {}
            parent_names=list(parent_values.values())
            boundary=boundary_provider.resolve_boundary(
                entity_type=entity_type,
                name=row.get("entity",row[dimension]),
                parent_name=parent_names[-1] if parent_names else None,
                parent_country=parent_names[0] if parent_names else None,
            )
            if boundary:
                props=boundary.get("properties") or {}
                resolved_admin[row.get("location",row[dimension])] = {
                    "geometry_name":boundary["name"],
                    "parent_name":boundary.get("parent"),
                    "boundary_source":boundary.get("boundary_source"),
                }
                boundary_features.append(boundary)
        unresolved=len(names)-len(resolved_admin)
    locations=[]
    for row in rows:
        geometry = resolved.get(row[dimension]) if entity_type == "country" else resolved_admin.get(row.get("location",row[dimension]))
        if geometry:
            locations.append({"name":row[dimension],"location":row.get("location",row[dimension]),"parents":row.get("parents",{}),"entity_type":entity_type,"metric":row["metric"],"rank":row["rank"],"contribution":row["contribution"],**geometry})
    # For non-country geographies, use only coordinates actually supplied by the dataset.
    if not locations:
        coords, coordinate_unresolved = resolver.resolve_dataset_coordinates(df, dimension, names)
        if entity_type == "country":
            unresolved=coordinate_unresolved
        for row in rows:
            point=coords.get(row[dimension])
            if point: locations.append({"name":row[dimension],"location":row.get("location",row[dimension]),"parents":row.get("parents",{}),"entity_type":entity_type,"metric":row["metric"],"rank":row["rank"],"contribution":row["contribution"],**point})
    return locations, unresolved, boundary_features
