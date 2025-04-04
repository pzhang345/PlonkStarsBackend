import asyncio
from api.location.generate import add_coord, check_multiple_street_views
from api.map.map import haversine
from models import MapBound, db, Bound, SVLocation
from utils import coord_at, float_equals


def map_max_distance(map):
    lat1 = map.start_latitude
    lng1 = map.start_longitude
    lat2 = map.end_latitude
    lng2 = map.end_longitude
    # Define the corners of the rectangle
    corners = [
        (lat1, lng1),
        (lat1, lng2),
        (lat2, lng1),
        (lat2, lng2)
    ]
    
    # Initialize the maximum distance
    max_dist = 0
    
    # Compare the distances between all pairs of corners
    for i in range(4):
        for j in range(i + 1, 4):
            lat1, lng1 = corners[i]
            lat2, lng2 = corners[j]
            dist = haversine(lat1, lng1, lat2, lng2)
            max_dist = max(max_dist, dist)
    
    map.max_distance = max(max_dist,1)

def get_bound(data):
    if "start" in data and "end" in data:
        s_lat,s_lng = get_point(data.get("start"))
        e_lat,e_lng = get_point(data.get("end"))
    elif "s_lat" in data and "s_lng" in data and "e_lat" in data and "e_lng" in data:
        s_lat, s_lng, e_lat, e_lng = data.get("s_lat"),data.get("s_lng"),data.get("e_lat"),data.get("e_lng")
    else:
        s_lat,s_lng = get_point(data)
        e_lat,e_lng = get_point(data)
    
    if s_lat == None or s_lng == None or e_lat == None or e_lng == None:
        raise Exception("please provided these arguments: start and end")
    
    if not (s_lat <= e_lat and s_lng <= e_lng):
        raise Exception("invalid input")
    
    return (s_lat,s_lng),(e_lat,e_lng)

def get_point(data):
    if "lat" in data and "lng" in data:
        lat,lng = data.get("lat"),data.get("lng")
    else:
        lat,lng = data
        
    if lat == None or lng == None:
        raise Exception("please provided these arguments: lat and lng")
    
    if not (-90 <= lat <= 90 and -180 <= lng <= 180):
        raise Exception("invalid input")
    
    return lat,lng

def map_add_bound(map,s_lat,s_lng,e_lat,e_lng,weight): 
    bound = Bound.query.filter(
        coord_at(Bound.start_latitude,s_lat),
        coord_at(Bound.start_longitude,s_lng),
        coord_at(Bound.end_latitude,e_lat),
        coord_at(Bound.end_longitude,e_lng)
    ).first()
    
    if not bound:
        bound = Bound(
            start_latitude=s_lat,
            start_longitude=s_lng,
            end_latitude=e_lat,
            end_longitude=e_lng
        )
        
        if SVLocation.query.filter(s_lat <= SVLocation.latitude,SVLocation.latitude <= e_lat,
                                   s_lng <= SVLocation.longitude,SVLocation.longitude <= e_lng).count() == 0:
            if float_equals(s_lat,e_lat) and float_equals(s_lng,e_lng):
                status = asyncio.run(check_multiple_street_views(bound,1))
            else:
                status = asyncio.run(check_multiple_street_views(bound,300))
            
            if status["status"] == "None":
                return {"error":"No street views found"},400
        
            add_coord(status["lat"],status["lng"])
            
            if float_equals(s_lat,e_lat) and float_equals(s_lng,e_lng) and (s_lng != status["lng"] or s_lat != status["lat"]):
                return map_add_bound(map,status["lat"],status["lng"],status["lat"],status["lng"],weight)
        
        db.session.add(bound)
        db.session.commit()
    
    if MapBound.query.filter_by(bound_id=bound.id,map_id=map.id).first():
        return {"error":"Bound already added"},400
    
    if float_equals(map.max_distance,-1):
        map.start_latitude=s_lat
        map.start_longitude=s_lng
        map.end_latitude=e_lat
        map.end_longitude=e_lng
        map_max_distance(map)
    
    change = False
    
    if s_lat < map.start_latitude:
        map.start_latitude = s_lat
        change = True
        
    if s_lng < map.start_longitude:
        map.start_longitude = s_lng
        change = True
    
    if map.end_latitude < e_lat:
         map.end_latitude = e_lat
         change = True
    
    if map.end_longitude < e_lng:
        map.end_longitude = e_lng
        change = True
    
    if change:
        map_max_distance(map)
    
    conn = MapBound(
        bound_id = bound.id,
        map_id = map.id,
        weight=weight
    )
    map.total_weight = map.total_weight + weight
    
    db.session.add(conn)
    db.session.commit()
    return {**bound.to_json(),"id":conn.id},200

def map_remove_bound(map,s_lat,s_lng,e_lat,e_lng):
    bound = Bound.query.filter(
        coord_at(Bound.start_latitude,s_lat),
        coord_at(Bound.start_longitude,s_lng),
        coord_at(Bound.end_latitude,e_lat),
        coord_at(Bound.end_longitude,e_lng)
    ).first()
    if not bound:
        raise Exception("Cannot find bound")
    
    mapbound = MapBound.query.filter_by(bound_id=bound.id,map_id=map.id).first()
    if not mapbound:
        raise Exception("Cannot find map bound")
    
    weight = mapbound.weight
    map.total_weight -= weight
    
    db.session.delete(mapbound)
    db.session.flush()
    if float_equals(bound.start_latitude,map.start_latitude) or float_equals(bound.start_longitude,map.start_longitude) or float_equals(bound.end_latitude,map.end_latitude) or float_equals(bound.end_longitude,map.end_longitude):
        bound_recalculate(map)
    db.session.commit()
    return {"id":mapbound.id},200

def reweight_bound(map,s_lat,s_lng,e_lat,e_lng,weight):
    bound = Bound.query.filter(
        coord_at(Bound.start_latitude,s_lat),
        coord_at(Bound.start_longitude,s_lng),
        coord_at(Bound.end_latitude,e_lat),
        coord_at(Bound.end_longitude,e_lng)
    ).first()
    if not bound:
        return {"error":"Cannot find bound"},400
    
    mapbound = MapBound.query.filter_by(bound_id=bound.id,map_id=map.id).first()
    if not mapbound:
        return {"error":"Cannot find map bound"},400
    
    map.total_weight += weight - mapbound.weight
    mapbound.weight = weight
    db.session.commit()
    return {**bound.to_json(),"weight":weight,"id":mapbound.id},200

def bound_recalculate(map):
    bounds = MapBound.query.filter_by(map_id=map.id)
    if bounds.count() == 0:
        map.max_distance = -1
        db.session.commit()
        return
        
    map.start_latitude = 90
    map.start_longitude = 180
    map.end_latitude = -90
    map.end_longitude = -180
    for bound in bounds.all():
        if bound.bound.start_latitude < map.start_latitude:
            map.start_latitude = bound.bound.start_latitude
        if bound.bound.start_longitude < map.start_longitude:
            map.start_longitude = bound.bound.start_longitude
        if map.end_latitude < bound.bound.end_latitude:
            map.end_latitude = bound.bound.end_latitude
        if map.end_longitude < bound.bound.end_longitude:
            map.end_longitude = bound.bound.end_longitude
    map_max_distance(map)
    db.session.commit()

def can_edit(user,map):
    return map.creator_id == user.id or user.is_admin