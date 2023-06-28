import requests
import yaml
import threading
import argparse
import time, sys, os

from flask import Flask, render_template

import logging
from logging.handlers import RotatingFileHandler





# ----------------------------------------------------
#            FUNCTIONS TO CREATE CONFIGS
# ----------------------------------------------------


def create_parse():
    """
        Create a dictionary with the <key,value> of the argparse configs.
    """

    parser = argparse.ArgumentParser()

    # Add arguments
    parser.add_argument("-cf", "--config.file", type=str, required=True, help="Configuration [yaml] file path.")
    parser.add_argument("-slp", "--storage.log.path", type=str, required=True, help="Path to store the [.log] files.")
    parser.add_argument("-scp", "--storage.counter.path", type=str, required=True, help="Path to store the [counters] files. In order to avoid loosing conexion and lose the last checkpoint of the counters.")

    try:
        args = parser.parse_args(sys.argv[1:])
        dict_parse = vars(args)

        # create paths if not exists
        key_paths = ["storage.log.path", "storage.counter.path"]
        for key in key_paths:
            path = dict_parse[key]
            if not os.path.exists(path):
                os.makedirs(path)

        return dict_parse

    # Error -> not all the required arguments are given!
    except:
        print("Error! You need to pass the following argumnets:")
        parser.print_help()
        exit(1)



def create_yaml():
    """
        Create a dictionary with the YAML configurations.
    """
    global PARSE
    with open(PARSE["config.file"], 'r') as file:
        yaml_dict = yaml.load(file, Loader=yaml.FullLoader)
    return yaml_dict



def create_logger():
    """
        Create a logger with the YAML configuration.
    """
    global YAML, PARSE

    log_file      = YAML["Configuration"]["Logging"]["File_name"]
    max_file_size = YAML["Configuration"]["Logging"]["Max_size"]
    backup_count  = YAML["Configuration"]["Logging"]["Backup_count"]

    # Create handler
    file_path = os.path.join(PARSE["storage.log.path"], log_file)
    file_handler = RotatingFileHandler(file_path, maxBytes=max_file_size, backupCount=backup_count)

    # Create configs
    file_handler.setLevel(logging.DEBUG)
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    file_handler.setFormatter(formatter)

    # Add configs 
    logger = logging.getLogger('')
    logger.setLevel(logging.DEBUG)
    logger.addHandler(file_handler)

    return logger



def load_counter(filename):
    """
        Arguments: 
             - filename: file name of the counter metric that we want to load. 
        Return: 
             - counter: number of the actual counter.

        This function is going to be used only at the beginning of the script. Then we are are going to use a global variable to track the counter.
    """
    global PARSE
    path = os.path.join(PARSE["storage.counter.path"], filename)
    if not os.path.exists(path):
        with open(path, "w") as f:
            f.write("0")
            counter = 0
    else:
        with open(path, "r") as f:
            counter = int(f.read())
    return counter



def update_counter(filename, n):
    """
        Arguments: 
            - filename: file name of the counter metric that we want to save.
            - n : number of the counter 

        This process updates the counter storage. It is going to be call every time we update the (global variable) counter. 
    """
    global PARSE
    path = os.path.join(PARSE["storage.counter.path"], filename)
    with open(path, "w") as f:
        f.write(str(n))




# ----------------------------------------------------
#                   GLOBAL VARIABLES 
# ----------------------------------------------------



METRICS_WEBSITE = ""

PARSE  = create_parse()
YAML   = create_yaml()
LOGGER = create_logger()

APIKEY = YAML["Configuration"]["Web"]["APIKey"]

COUNTER = {
    "weather_n_calls" : load_counter("weather_n_calls")
}



# ----------------------------------------------------
#       FUNCTIONS TO GET THE DATA FROM THE API 
# ----------------------------------------------------


def api_call(city, country):
    """
        API Call -> Get the data (in json format) given a pair {city, country}
    """

    global APIKEY, LOGGER, COUNTER

    name = "weather_n_calls"
    COUNTER[name] += 1
    update_counter(name, COUNTER[name])

    url = f"https://api.openweathermap.org/data/2.5/weather?q={city},{country}&appid={APIKEY}"

    try:
        response = requests.get(url)

        # Succesfull call
        if response.status_code // 100 == 2:
            LOGGER.info(f"API call succesfull! N = {COUNTER['weather_n_calls']}.")
            data = response.json()
        # Error with the api call
        else:
            message = f"Error: {response.status_code}, while trying to do the api call with <city='{city}', country='{country}'>!"
            LOGGER.error(message)
            data = None

    except:
        message = f"API request Error! while trying to do the api call with <city='{city}', country='{country}'>!"
        LOGGER.error(message)
        data = None

    return data


def create_prometheus_data(temp):
    """
        Arguments:
            temp: dictionary (with multiples values) with the name of 
                the city and country which we wan to take the data from. 
        Return:
            ss: string with the data in Prometheus format
    """

    global COUNTER, LOGGER
    
    s1 = "# HELP city_temperature Celsius Temperature from a specific city.\n# TYPE city_temperature gauge\n"
    s2 = "# HELP city_windspeed Wind spped (m/s) from a specific city.\n# TYPE city_windspeed gauge\n"
    s3 = "# HELP city_pressure Pressure from a specific city.\n# TYPE city_pressure gauge\n"
    s4 = "# HELP city_humidity Humidity from a specific city.\n# TYPE city_humidity gauge\n"
    s5 = "# HELP weather_n_calls Number of OpenWeather API Calls.\n# TYPE weather_n_calls counter\n"

    n = len(temp)
    data = [None for _ in range(n)]

    for i in range(n):
        city    = temp[i]["City"] 
        country = temp[i]["Country"]

        data = api_call(city, country)

        # skip when we didnt get any data (because of an API request error)
        if data == None:
            LOGGER.info(f"Empty data for <city='{city}', country='{country}'>.")
            continue

        x1 = round(data["main"]["temp"] - 273.15, 2)
        x2 = data["wind"]["speed"]
        x3 = data["main"]["pressure"]
        x4 = data["main"]["humidity"]

        s1 += 'city_temperature{city="' + str(city) + '", country="' + str(country) + '"} ' + str(x1) + '\n'
        s2 += 'city_windspeed{city="'   + str(city) + '", country="' + str(country) + '"} ' + str(x2) + '\n'
        s3 += 'city_pressure{city="' + str(city) + '", country="' + str(country) + '"} ' + str(x3) + '\n'
        s4 += 'city_humidity{city="'   + str(city) + '", country="' + str(country) + '"} ' + str(x4) + '\n'
    
    s5 += 'weather_n_calls ' + str(COUNTER["weather_n_calls"]) + '\n'

    ss = s1 + s2 + s3 + s4 + s5

    return ss


# ----------------------------------------------------
#                   INIT WEB PAGE
# ----------------------------------------------------

app = Flask(__name__)

@app.route('/')
def init():
    """
        Render a simple HTML file in the "/" path of our website.
    """
    return render_template("init.html")


# ----------------------------------------------------
#                       METRICS
# ----------------------------------------------------

@app.route(YAML["Configuration"]["Web"]["WRoute"])
def metrics():
    """
        Here we create the "/metrics/" path of our website.

        Return: data in a Prometheus format.
    """
    global METRICS_WEBSITE

    return METRICS_WEBSITE, 200, {'Content-Type': "text/plain"}



# ----------------------------------------------------
#        THREADING - UPDATE DATA ON THE WEBSITE
# ----------------------------------------------------

def temperature_update(upd_period):
    global METRICS_WEBSITE, LOGGER
    while True:
        temp = YAML["Temperature"]
        METRICS_WEBSITE = create_prometheus_data(temp)
        LOGGER.info("Metrics updated!")
        time.sleep(upd_period)


# ----------------------------------------------------
#                     RUN THE APP
# ----------------------------------------------------

if __name__ == '__main__':

    LOGGER.info("Configurations loaded correctly!")

    # start threading

    period = YAML["Configuration"]["Web"]["Period"]

    thread = threading.Thread(target=temperature_update, args=(period,))
    thread.start()

    LOGGER.info("Running thread!")

    # start web site

    host = YAML["Configuration"]["Web"]["Host"]
    port = YAML["Configuration"]["Web"]["Port"]

    LOGGER.info(f"Running app in host={host} and port={port}.")

    app.run(host=host, port=int(port))
    
    LOGGER.error("App is no longer running!!")
