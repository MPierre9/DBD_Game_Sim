import os
import json
import redis
import random
import mysql.connector
import time
import boto3
import uuid
import datetime

# Time to live for cached data
TTL = 30

# Read the Redis credentials from the REDIS_URL environment variable.
REDIS_URL = os.environ.get('REDIS_URL')

# Read the DB credentials from the DB_* environment variables.
DB_HOST = os.environ.get('DB_HOST')
DB_USER = os.environ.get('DB_USE')
DB_PASS = os.environ.get('DB_PASS')
DB_NAME = os.environ.get('DB_NAME')

bhvr_db = mysql.connector.connect(
        host=DB_HOST,
        user=DB_USER,
        passwd=DB_PASS,
        database=DB_NAME,
        auth_plugin='mysql_native_password'
)

user_cursor = bhvr_db.cursor()

# Initialize the cache
Cache = redis.Redis.from_url(REDIS_URL)

# Connect to AWS Kinesis Firehose
firehose_client = boto3.client('firehose', region_name='us-east-1')

def get_game_results(players):
    print("Getting game results")
    game_won = True
    # The below variables are used to make the data relational when streaming to S3. Due to time constraints this doesn't seem efficient but will work for now.
    match_time = str(datetime.datetime.now().strftime("%d-%m-%Y-%H-%M-%S"))
    match_id = str(uuid.uuid4()) + "-" + match_time
    for player in players:
        # Check if any survivors made it.
        if not player["killed"] and player["killer"] == "":
            game_won = False
        # Here we will add the match ID so we can arrange the players into matches via SQL later in AWS
        player["match_id"] = match_id
        # Stream match players to S3
        json_game_string = json.dumps(player)
        firehose_player_response = firehose_client.put_record(
            DeliveryStreamName='BHVR-STREAM',
            Record={
                'Data': json_game_string
            }
        )
        print(firehose_player_response)
        time.sleep(2)
    # This data will be used for a second table that will act a match lookup table to arrange players in matches after the fact.
    game_data = {
        "match_id": match_id,
        "match_time": match_time
    }
    # Stream match to S3
    json_match_string = json.dumps(game_data)
    firehose_game_response = firehose_client.put_record(
        DeliveryStreamName='BHVR_GAME_STREAM',
            Record={
                'Data': json_match_string
            }
    )
    print(firehose_game_response)

    if game_won:
        print("Game Won!")
    else:
        print("Game Lost!")
    print("Preparing for next game...")

    # Stream out each individual player at a time
    # Assign game_id to each player. We will use this ID to correlate the game they were in when querying the data.

    time.sleep(20)
    get_users_for_game()

# In this function we determine the chance that a specific player in the game will get killed
# The more the play time the killer has means they have a better chance of killing the opponent (in this simulation)
# This function returns whether a player has been killed or not
# The killer must roll a 8 or 9 to kill the opponent and get additional rolls based on play time
def roll_dice(killer_play_time):
    print("Players play time: " + str(killer_play_time))
    amount_rolls = round((0.002) * pow(killer_play_time,2))

    # Let's roll
    rolls = 1 + amount_rolls
    print("Killer gets: " + str(rolls))
    for roll in range(0, rolls):
        dice = random.randint(0, 10)
        if dice == 9 or dice == 10:
            print("Player killed.")
            return True

    print("Player not killed.")
    return False

def play_game(players, killer_num):
    print("Game started")
    for survivor in players:
        if survivor["killer"] == "":
            result = roll_dice(players[killer_num]["play_time"])
            if result:
                print(survivor["username"] + " has been killed.")
                survivor["killed"] = True
            else:
                print(survivor["username"] + " has escaped.")

    get_game_results(players)

# In this function we will generate a player list to use in our simulated game.
# From this player list we will determine one player to be the killer. Then we will assign a character to the killer.
def get_users_for_game():
    print("Getting users for game...")
    user_list = fetch("SELECT * FROM USER")
    user_count = len(user_list)
    print("User count: " + str(len(user_list)))

    player_ids = []
    # Pick five players at random for the game
    for i in range(5):
        # user count - 1 so we don't get a index out of range
        player_ids.append(random.randint(1, user_count - 1))

    players = []
    for x in player_ids:
        player = {
            "username": "",
            "play_time": "",
            "killer": "",
            "killed": False
        }

        print("Selected Player: " + str(x))
        player["username"] = user_list[x][1]

        player["play_time"] = user_list[x][3]
        players.append(player)


    # Let's pick a random number to see who the killer will be
    killer_num = random.randint(0, 4)
    print("Our Killer Is: " + players[killer_num]["username"])

    # Let's pick what killer our selected will be
    killer_list = fetch("SELECT * FROM KILLER")

    killer_count = len(killer_list)

    # Pick random killer
    killer_indice = random.randint(0, killer_count - 1)
    killer_character = killer_list[killer_indice][2]
    print("The killer will be playing as: " + killer_character)
    print("\n\n\n")
    players[killer_num]["killer"] = killer_character
    play_game(players, killer_num)

def fetch(sql):
    result = Cache.get(sql)

    if result:
        print("Loaded from Elasticache")
        return json.loads(result)

    print("Loaded from MySQL Database")
    user_cursor.execute(sql)
    result = user_cursor.fetchall()
    Cache.setex(sql,TTL, json.dumps(result))
    return result

get_users_for_game()
