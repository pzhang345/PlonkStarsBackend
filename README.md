Link to the frontend repo: https://github.com/Bartavius/Plonkstars

## What is Plonkstars?
Plonkstars, inspired by GeoGuessr, is a completely free (both developer side and user side) geolocation guessing game using Google Streetview Embeds and React Leaflet's functionality to create a seamlessly addictive game.

As active GeoGuessr players, my friends and I were heartbroken when we heard that GeoGuessr was going to charge users a monthly subscription as it became too expensive to maintain its functionalities. As broke college students, this was an absolute dealbreaker. So instead, we figured we would make it ourselves, completely free.

## Getting started
head over to https://plonkstars.vercel.app and register an account. Click on the Game tab and input your game settings: the map, the no. of rounds (-1 for infinite rounds), and the time per round in seconds (-1 for infinite). If you want to play a game synchronously with a friend, you can enter in the match ID (found in the URL) and paste it into the join game input box. Otherwise, you can get started on a new game!

Select the minimap to place your guess after looking around on the streetview embed, and take your guess! Your distance from the correct location will then be displayed on the results page. Then try again! Have fun! Just don't get too addicted and let it distract you from class.

## Tech stack
Frontend - React.js, TailwindCSS, Next.js<br>
Backend - Flask, PostgreSQL

Server-side is hosted on Heroku<br>
Client-side is hosted on Vercel

To run the backend locally, run these commands in different terminal tabs:
```
docker run --name redis --rm -p 6379:6379 redis redis-server
celery -A my_celery.celery_worker.celery worker --loglevel=info --pool=threads
flask run
```

Here are the configs that are set in the configs table:
```
id,key,value
1,DAILY_DEFAULT_ROUNDS,5
2,DAILY_DEFAULT_TIME_LIMIT,180
3,DAILY_DEFAULT_NMPZ,False
4,DAILY_DEFAULT_MAP_ID,1
5,DAILY_DEFAULT_HOST_ID,1
6,GAME_DEFAULT_ROUNDS,5
7,GAME_DEFAULT_TIME_LIMIT,60
8,GAME_DEFAULT_NMPZ,False
9,GAME_DEFAULT_MAP_ID,1
10,DUELS_DEFAULT_ROUNDS,-1
11,DUELS_DEFAULT_TIME_LIMIT,-1
12,DUELS_DEFAULT_NMPZ,False
13,DUELS_DEFAULT_MAP_ID,1
14,DUELS_DEFAULT_START_HP,6000
15,DUELS_DEFAULT_DAMAGE_MULTI_START_ROUND,1
16,DUELS_DEFAULT_DAMAGE_MULTI_MULT,1
17,DUELS_DEFAULT_DAMAGE_MULTI_ADD,0
18,DUELS_DEFAULT_DAMAGE_MULTI_FREQ,1
19,DUELS_DEFAULT_GUESS_TIME_LIMIT,15
```