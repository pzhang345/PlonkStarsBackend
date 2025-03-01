import math

from models import db,Bound,MapBound
from api.location.generate import check_multiple_street_views

def haversine(lat1, lng1, lat2, lng2):
    # Convert latitude and lnggitude from degrees to radians
    lat1 = math.radians(lat1)
    lng1 = math.radians(lng1)
    lat2 = math.radians(lat2)
    lng2 = math.radians(lng2)
    
    # Haversine formula
    dlat = lat2 - lat1
    dlng = lng2 - lng1
    a = math.sin(dlat / 2)**2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlng / 2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    
    # Radius of Earth in kilometers (use 3958.8 for miles)
    radius = 6371.0
    
    # Calculate the distance
    distance = radius * c
    return distance

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
    
    map.max_distance = max_dist
    
def map_add_bound(map,s_lat,s_lng,e_lat,e_lng,weight):
    bound = Bound.query.filter_by(
        start_latitude=s_lat,
        start_longitude=s_lng,
        end_latitude=e_lat,
        end_longitude=e_lng
    ).first()
    
    if not bound:
        bound = Bound(
            start_latitude=s_lat,
            start_longitude=s_lng,
            end_latitude=e_lat,
            end_longitude=e_lng
        )
        status = check_multiple_street_views(bound,200)
        if status["status"] == "None":
            return {"error":"No street views found"},400
        
        db.session.add(bound)
        db.session.commit()
    
    if MapBound.query.filter_by(bound_id=bound.id,map_id=map.id).first():
        return {"error":"Bound already added"},400
    
    if map.max_distance == -1:
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
    return {"message":"Bound added"},200