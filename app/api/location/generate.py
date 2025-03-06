
from flask import jsonify
from concurrent.futures import ThreadPoolExecutor
import requests
import random
from config import Config
from models import db,SVLocation, MapBound
from sqlalchemy.sql.expression import func
import math

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
    for _ in range(10):
        bound = get_random_bounds(map)
        gen = check_multiple_street_views(bound)
        if gen["status"] == "OK":
            break
    
    if gen["status"] == "None":
        bound = get_random_bounds(map)
        return db_location(bound)
    
    return add_coord(gen["lat"],gen["lng"])

def add_coord(lat,lng):
    new_coord = SVLocation.query.filter_by(latitude=lat,longitude=lng).first()
    if new_coord:
        return new_coord
    
    new_coord = SVLocation(latitude=lat,longitude=lng)

    db.session.add(new_coord)
    db.session.commit()
    return new_coord

r_earth = 6371000
def add_meters(lat,lng,d_lat,d_lng):
    new_lat = lat + (d_lat / r_earth) * (180 / math.pi)
    new_lng = lng + (d_lng / r_earth) * (180 / math.pi) / max(0.01,math.cos(lat * math.pi / 180))
    return new_lat,new_lng

def db_location(bound):
    random_func = func.rand() if db.engine.dialect.name == 'mysql' else func.random()
    s_lat,s_lng = add_meters(float(bound.start_latitude),float(bound.start_longitude),-50,-50)
    e_lat,e_lng = add_meters(float(bound.end_latitude),float(bound.end_longitude),50,50)
    return SVLocation.query.filter(s_lat <= SVLocation.latitude,SVLocation.latitude <= e_lat,
                                   s_lng <= SVLocation.longitude,SVLocation.longitude <= e_lng).order_by(random_func).first()