import aiohttp
import asyncio
import random
import math
from sqlalchemy.sql.expression import func
from sqlalchemy import and_

from config import Config
from models.db import db
from models.location import SVLocation
from models.map import MapBound
from utils import coord_at

GOOGLE_MAPS_API_KEY = Config.GOOGLE_MAPS_API_KEY

def randomize(bound):
    lat = random.uniform(bound.start_latitude,bound.end_latitude)
    lng = random.uniform(bound.start_longitude,bound.end_longitude)
    return (lat,lng)
    
async def call_api(session,bound):
    lat,lng = randomize(bound)
    async with session.get(f"https://maps.googleapis.com/maps/api/streetview/metadata?location={lat},{lng}&key={GOOGLE_MAPS_API_KEY}") as response:
        return await response.json()

async def check_multiple_street_views(bound,num_checks=100):
    async with aiohttp.ClientSession() as session:
        tasks = [call_api(session,bound) for _ in range(num_checks)]
        results = await asyncio.gather(*tasks)
    
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
        if (bound.start_latitude == bound.end_latitude and bound.start_longitude == bound.end_longitude):
            gen = asyncio.run(check_multiple_street_views(bound,1))
        else:
            gen = asyncio.run(check_multiple_street_views(bound))
        if gen["status"] == "OK":
            break
    
    if gen["status"] == "None":
        bound = get_random_bounds(map)
        return db_location(bound)
    
    return add_coord(gen["lat"],gen["lng"])

def add_coord(lat,lng):
    coord = SVLocation.query.filter(and_(coord_at(SVLocation.latitude,lat),coord_at(SVLocation.longitude,lng))).first()
    if coord:
        return coord

    coord = SVLocation(latitude=lat,longitude=lng)
    db.session.add(coord)
    db.session.commit()
    return coord

r_earth = 6371000
def add_meters(lat,lng,d_lat,d_lng):
    new_lat = lat + (d_lat / r_earth) * (180 / math.pi)
    new_lng = lng + (d_lng / r_earth) * (180 / math.pi) / max(0.01,math.cos(lat * math.pi / 180))
    return new_lat,new_lng

def db_location(bound):
    random_func = func.rand() if db.engine.dialect.name == 'mysql' else func.random()
    s_lat,s_lng = add_meters(bound.start_latitude,bound.start_longitude,-50,-50)
    e_lat,e_lng = add_meters(bound.end_latitude,bound.end_longitude,50,50)
    return SVLocation.query.filter(s_lat <= SVLocation.latitude,SVLocation.latitude <= e_lat,
                                   s_lng <= SVLocation.longitude,SVLocation.longitude <= e_lng).order_by(random_func).first()