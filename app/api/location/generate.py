
from flask import jsonify
from concurrent.futures import ThreadPoolExecutor
import requests
import random
from config import Config
from models import db,SVLocation, MapBound
from sqlalchemy.sql.expression import func

GOOGLE_MAPS_API_KEY = Config.GOOGLE_MAPS_API_KEY
session = requests.Session()
session.get("https://maps.googleapis.com/maps/api/streetview/metadata")

def randomize(bound):
    lat = random.uniform(float(bound.start_latitude),float(bound.end_latitude))
    lng = random.uniform(float(bound.start_longitude),float(bound.end_longitude))
    return (lat,lng)
    
def call_api(lat,lng):
    req = session.get(f"https://maps.googleapis.com/maps/api/streetview/metadata?location={lat},{lng}&key={GOOGLE_MAPS_API_KEY}")
    return req.json()

def check_multiple_street_views(bound,num_checks=10,looptime=10):
    for i in range(looptime):
        with ThreadPoolExecutor() as executor:
            results = list(executor.map(lambda loc: call_api(loc[0], loc[1]), [randomize(bound) for _ in range(num_checks)]))
        
        for d in results:
            if d["status"] == "OK":
                return {"lat":d["location"]["lat"],"lng":d["location"]["lng"],"status":"OK"}

    return {"status":"None"}

def get_random_bounds(map):
    num = random.uniform(0,map.total_weight)
    bounds = MapBound.query.filter_by(map_id=map.id).all()
    for bound in bounds:
        num -= bound.weight
        if num < 0:
            return bound.bound
    raise Exception("total weight incorrect")
        
    
def generate_location(map):
    bound = get_random_bounds(map)
    count = 0
    gen = check_multiple_street_views(bound)
    
    while gen["status"] != "OK":
        bound = get_random_bounds(map)
        if count < 10:
            gen = check_multiple_street_views(bound)
        else:
            if count > 100:
                raise Exception("can not find location")
            loc = db_location(bound)
            if loc:
                return loc
        count += 1
    
    new_coord = SVLocation.query.filter_by(latitude=gen["lat"],longitude=gen["lng"]).first()
    if new_coord:
        return new_coord
    
    new_coord = SVLocation(latitude=gen["lat"],longitude=gen["lng"])

    db.session.add(new_coord)
    db.session.commit()
    return new_coord

def db_location(bound):
    s_lat = bound.start_latitude
    s_lng = bound.start_longitude
    e_lat = bound.end_latitude
    e_lng = bound.end_longitude
    return SVLocation.query.filter(s_lat <= SVLocation.latitude,SVLocation.latitude <= e_lat,
                                   s_lng <= SVLocation.longitude,SVLocation.longitude <= e_lng).order_by(func.rand()).first()