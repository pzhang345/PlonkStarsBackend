
from flask import jsonify
from concurrent.futures import ThreadPoolExecutor
import requests
import random
from config import Config
from models import db,SVLocation, MapBound
GOOGLE_MAP_API_KEY = Config.GOOGLE_MAPS_API_KEY

def randomize(bound):
    lat = random.uniform(float(bound.start_latitude),float(bound.end_latitude))
    lng = random.uniform(float(bound.start_longitude),float(bound.end_longitude))
    return (lat,lng)
    
def does_exist(lat,lng):
    req = requests.get(f"https://maps.googleapis.com/maps/api/streetview/metadata?location={lat},{lng}&key={GOOGLE_MAP_API_KEY}")
    return req.json()

def check_multiple_street_views(bound,num_checks=100):
    locations = [randomize(bound) for _ in range(num_checks)]
    
    with ThreadPoolExecutor() as executor:
        results = list(executor.map(lambda loc: does_exist(loc[0], loc[1]), locations))
    
    for d in results:
        if d["status"] == "OK":
            return {"lat":d["location"]["lat"],"lng":d["location"]["lng"],"status":"OK"}

    return {"lat":0,"lng":0,"status":"None"}

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
        if count == 5:
            bound = get_random_bounds(map)
        if count == 20:
            raise Exception("could not a find location")
    
        gen = check_multiple_street_views(bound)
        count += 1
    
    new_coord = SVLocation.query.filter_by(latitude=gen["lat"],longitude=gen["lng"]).first()
    if new_coord:
        return new_coord
    
    new_coord = SVLocation(latitude=gen["lat"],longitude=gen["lng"])

    db.session.add(new_coord)
    db.session.commit()
    return new_coord

def db_location():
    row_count = db.session.query(SVLocation).count()
    if row_count == 0:
        raise Exception("No items found in the database")
    
    random_index = random.randint(0, row_count - 1)
    random_coord = SVLocation.query.offset(random_index).first()
    return random_coord