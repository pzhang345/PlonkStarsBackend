
from concurrent.futures import ThreadPoolExecutor
import requests
import random
from config import Config
GOOGLE_MAP_API_KEY = Config.GOOGLE_MAPS_API_KEY

def randomize():
    lat = random.uniform(-90,90)
    lng = random.uniform(-180,180)
    return lat,lng
    
def does_exist(lat,lng):
    req = requests.get(f"https://maps.googleapis.com/maps/api/streetview/metadata?location={lat},{lng}&key={GOOGLE_MAP_API_KEY}")
    return req.json()

def check_multiple_street_views(num_checks=100):
    locations = [randomize() for _ in range(num_checks)]
    
    with ThreadPoolExecutor() as executor:
        results = list(executor.map(lambda loc: does_exist(loc[0], loc[1]), locations))
    
    for i,d in enumerate(results):
        if d["status"] == "OK":
            return {"lat":locations[i][0],"lng":locations[i][1],"status":"OK"}

    return {"lat":0,"lng":0,"status":"None"}

def generate():
    answer = check_multiple_street_views()
    while answer["status"] != "OK":
        answer = check_multiple_street_views()
    
    return answer