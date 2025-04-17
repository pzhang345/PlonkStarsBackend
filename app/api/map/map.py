import math
from sqlalchemy import Float, cast, func

from models.stats import MapStats, UserMapStats

def haversine(lat1, lng1, lat2, lng2):
    # Convert latitude and longitude from degrees to radians
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

def get_stats(map,user=None,nmpz=None):
    if user:
        query = UserMapStats.query.filter_by(user_id=user.id)
        model = UserMapStats
    else:
        query = MapStats.query
        model = MapStats
        
    if nmpz != None:
        return query.filter_by(map_id=map.id,nmpz=nmpz).first()
    
    totals = (
        query.with_entities(
            func.sum(cast(model.total_time,Float)).label("total_time"),
            func.sum(cast(model.total_score,Float)).label("total_score"),
            func.sum(cast(model.total_distance,Float)).label("total_distance"),
            func.sum(cast(model.total_guesses,Float)).label("total_guesses"),
        )
        .filter_by(map_id=map.id)
        .first()
    )
    
    return totals