from flask import Flask, render_template, request, redirect, url_for, session,jsonify
from datetime import datetime, timedelta
import sys
import pandas as pd
import os, os.path
import sqlite3
from bs4 import BeautifulSoup
import requests
import time
import seaborn as sns
import matplotlib #https://stackoverflow.com/questions/73745245/error-using-matplotlib-in-pycharm-has-no-attribute-figurecanvas
matplotlib.use('TkAgg')
import matplotlib.pyplot as plt


#Scraping Wikipedia page to get camp locations
def scrape_camp_locations():
    url = "https://en.wikipedia.org/wiki/List_of_Singapore_Armed_Forces_bases"
    response = requests.get(url)
    soup = BeautifulSoup(response.content, "html.parser")
    table = soup.find("table", {"class": "wikitable"})
    rows = table.find("tbody").find_all("tr")

    camps = []
    for row in rows:
        cells = row.find_all("td")
        if len(cells) >= 3:
            camps.append({"name": cells[0].text.strip(), "location": cells[1].text.strip()})
    return camps

#Convert temperature from Fahrenheit to Celsius
def convert_temperature(temp_fahrenheit):
    if temp_fahrenheit > 45:
        temp_celsius = round((temp_fahrenheit - 32) * 5/9)
        return temp_celsius
    else:
        return temp_fahrenheit

#Fetch weather data from Bing
def get_weather_data(region):
    selected_location_url_encoded = region.replace(' ', '%20')
    user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/94.0.4606.81 Safari/537.36"
    language = "en-US,en;q=0.5"
    max_retries = 3
    delay_seconds = 2

    #Google scraping
    google_url = f'https://www.google.com/search?q=weather+in+Singapore+{selected_location_url_encoded}&hl=en&lr=lang_en&num=1&cr=countrySG'
    session = requests.Session()
    session.headers['User-Agent'] = user_agent
    session.headers['Accept-Language'] = language
    session.headers['Content-Language'] = language

    retries = 0
    while retries < max_retries:
        try:
            html = session.get(google_url)
            html.raise_for_status()
            soup = BeautifulSoup(html.text, "html.parser")
            result = {}
            result['temp_now'] = soup.find("span", attrs={"id": "wob_tm"}).text
            temp_fahrenheit = float(result["temp_now"])
            temp_celsius = convert_temperature(temp_fahrenheit)
            return temp_celsius
        except (requests.RequestException, AttributeError, ValueError) as e:
            retries += 1
            if retries < max_retries:
                time.sleep(delay_seconds)
            else:
                pass

    #Bing scraping
    bing_url = f'https://www.bing.com/search?q=weather+in+{selected_location_url_encoded}&hl=en'
    retries = 0
    while retries < max_retries:
        try:
            html = session.get(bing_url)
            html.raise_for_status()
            soup = BeautifulSoup(html.text, "html.parser")
            result = {}
            result['temp_now'] = soup.find("div", class_="wtr_currTemp b_focusTextLarge").text
            temp_fahrenheit = float(result["temp_now"].split('°')[0])
            temp_celsius = convert_temperature(temp_fahrenheit)
            return temp_celsius
        except (requests.RequestException, AttributeError, ValueError) as e:
            retries += 1
            if retries < max_retries:
                time.sleep(delay_seconds)
            else:
                pass

    return None

def get_heat_injury_risk(region):
    temperature = get_weather_data(region)
    if temperature is None:
        return None, None, None

    if temperature < 30.9:
        risk = "Code Green"
        work_duration = 45
        break_duration = 15
    elif 31 <= temperature <= 31.9:
        risk = "Code Yellow"
        work_duration = 30
        break_duration = 15
    elif 32 <= temperature <= 32.9:
        risk = "Code Red"
        work_duration = 30
        break_duration = 30
    else:
        risk = "Code Black"
        work_duration = 15
        break_duration = 30

    return risk, work_duration, break_duration

app = Flask(__name__)
app.config["DEBUG"] = True  #Enable debug mode

app.secret_key = b'bc3413' #https://stackoverflow.com/questions/22463939/demystify-flask-app-secret-key

class UserCSVManager:
    def __init__(self):
        self.create_table()
        self.move_csv_files_to_database()

    def create_table(self):
        conn = sqlite3.connect("user_data_storage.db")
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='users'") #https://www.geeksforgeeks.org/check-if-table-exists-in-sqlite-using-python/#:~:text=SELECT%20tableName%20FROM%20sqlite_master%20WHERE,not%20exist%20in%20the%20database.
        existing_tables = cursor.fetchall()
        if not existing_tables:
            cursor.execute('''CREATE TABLE users (
                                User_ID TEXT,
                                Date DATE,
                                Time TEXT,
                                BodyTemperature_Celsius REAL,
                                HeartRate_BPM INTEGER,
                                Sweatchloride_mmol_L REAL,
                                Obesity TEXT,
                                Heart_Disease TEXT,
                                High_Blood_Pressure TEXT,
                                PRIMARY KEY (User_ID, Date, Time)
                            )''')
            conn.commit()

    def move_csv_files_to_database(self):
        conn = sqlite3.connect("user_data_storage.db")
        cursor = conn.cursor()

        csv_files = [file for file in os.listdir() if file.endswith('.csv')] #https://stackoverflow.com/questions/61125425/listdir-to-only-call-csv-files

        for file in csv_files:
            df = pd.read_csv(file)
            for index, row in df.iterrows(): #https://stackoverflow.com/questions/16476924/how-to-iterate-over-rows-in-a-pandas-dataframe

                try:
                    #Convert date format from dd-mm-yyyy to yyyy-mm-dd
                    formatted_date = datetime.strptime(row[1], '%d/%m/%Y').strftime('%Y-%m-%d') #https://stackoverflow.com/questions/65303781/converting-date-into-y-m-d-using-strptime-and-strftime-using-python
                    #Replace the date value in the row
                    row[1] = formatted_date

                    cursor.execute('INSERT INTO users VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)', row)
                    conn.commit()
                except (sqlite3.IntegrityError, sqlite3.InterfaceError):
                    pass
        conn.close()

    def append_user_data(self, user_data):
        conn = sqlite3.connect("user_data_storage.db")
        cursor = conn.cursor()

        try:
            cursor.execute('INSERT INTO users VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)',
                           (user_data[0], user_data[1], user_data[2], user_data[3], user_data[4], user_data[5],
                            user_data[6], user_data[7], user_data[8]))
            conn.commit()
        except (sqlite3.IntegrityError, sqlite3.InterfaceError):
            pass

class User:
    def __init__(self, csv_manager):
        self.csv_manager = csv_manager
        self.last_additional_qns_asked = {}  #Dictionary to store the last time additional questions were asked for each user

    def get_user_details(self, user_id):
        conn = sqlite3.connect("user_data_storage.db")
        cursor = conn.cursor()
        cursor.execute('''SELECT * FROM users WHERE User_ID = ? ORDER BY Date DESC, Time DESC''', (user_id,))
        user_data = cursor.fetchone()
        return user_data

    def track_heat_exhaustion(self):
        conn = sqlite3.connect("user_data_storage.db")
        cursor = conn.cursor()

        cursor.execute('''
            SELECT User_ID, Date, Time, BodyTemperature_Celsius, Sweatchloride_mmol_L
            FROM users
            WHERE (BodyTemperature_Celsius > 38.3 OR Sweatchloride_mmol_L > 18.5) AND Date = ? GROUP BY User_ID
        ''', (datetime.now().date(),))

        users_at_risk = cursor.fetchall()

        users_at_risk_output = []
        print("\nUsers at risk of heat exhaustion today:")
        for user in users_at_risk:
            users_at_risk_output.append(f"{user[0]} - {user[1]} {user[2]} -  {user[3]}°C -  {user[4]} ")
            time.sleep(0.5)

        conn = sqlite3.connect("user_data_storage.db")
        cursor = conn.cursor()
        cursor.execute('''
                    SELECT User_ID, Date, Time,Obesity, Heart_Disease,High_Blood_Pressure
                    FROM users
                    WHERE (Obesity='y' OR Heart_Disease='y' OR High_Blood_Pressure= 'y') GROUP BY User_ID
                ''')

        heat_related_diseases_output = []
        heat_related_diseases = cursor.fetchall()
        if heat_related_diseases:
            print("\nUsers at risk of heat exhaustion due to health issues are:")
            for user in heat_related_diseases:
                heat_related_diseases_output.append(
                    f"{user[0]} - {user[1]} {user[2]} -  {user[3]} -  {user[4]} -  {user[5]}")
                time.sleep(0.5)

        return users_at_risk_output, heat_related_diseases_output

    def track_heat_exhaustion_for_chart(self):
        conn = sqlite3.connect("user_data_storage.db")
        cursor = conn.cursor()

        cursor.execute('''
            SELECT User_ID, Date, Time, BodyTemperature_Celsius, Sweatchloride_mmol_L
            FROM users
            WHERE (BodyTemperature_Celsius > 38.3 OR Sweatchloride_mmol_L > 18.5) AND Date = ? GROUP BY User_ID
        ''', (datetime.now().date(),))

        results = cursor.fetchall()
        conn.close()

        num_occurrences = len(results)

        conn = sqlite3.connect("user_data_storage.db")
        cursor = conn.cursor()
        cursor.execute('''
                    SELECT User_ID, Date, Time, Obesity, Heart_Disease, High_Blood_Pressure
                    FROM users
                    WHERE (Obesity='y' OR Heart_Disease='y' OR High_Blood_Pressure= 'y') GROUP BY User_ID
                ''')

        heat_illness = cursor.fetchall()
        conn.close()

        if heat_illness:
            heat_illness_occurrences = len(heat_illness)

            conn = sqlite3.connect("user_data_storage.db")
            cursor = conn.cursor()
            cursor.execute('''
                        SELECT User_ID AS total_number
                        FROM users
                        GROUP BY User_ID
                    ''')

            total_number = cursor.fetchall()
            conn.close()

            total_number_occurrences = len(total_number)

            #Plotting the bar chart
            categories = ['Users at risk of HE', 'Risk of HE due to health issues', 'Total Number of Users']
            counts = [num_occurrences, heat_illness_occurrences, total_number_occurrences]
            sns.set_style("whitegrid")
            plt.figure(figsize=(8, 6))
            ax = sns.barplot(x=categories, y=counts, palette="muted") #https://stackoverflow.com/questions/43214978/how-to-display-custom-values-on-a-bar-plot
            for i in range(len(categories)):
                ax.text(i, counts[i] + 0.05, str(counts[i]), ha='center', va='bottom')
            plt.ylabel('Counts')
            plt.title('Users at risk of HE against Total Number of Users')
            bar_chart_filename = 'bar_chart.png'
            bar_chart_path = os.path.join('static', 'Images', bar_chart_filename)
            plt.savefig(bar_chart_path)
            plt.close()

            #Plotting Pie Chart https://medium.com/@kvnamipara/a-better-visualisation-of-pie-charts-by-matplotlib-935b7667d77f
            proportions = [num_occurrences / total_number_occurrences,
                           heat_illness_occurrences / total_number_occurrences,
                           total_number_occurrences]

            sns.set_style("whitegrid")
            sns.despine(left=True, bottom=True)
            categories = ['Users at risk of HE', 'Risk of HE due to health issues', 'No Risk']
            colors = ['#ff9999', '#66b3ff', '#99ff99']
            explode = (0.1, 0, 0)  # explode the 1st slice (Users at risk of HE)
            plt.figure(figsize=(8, 6))
            plt.pie(proportions, labels=categories, autopct='%1.1f%%', startangle=140, colors=colors, explode=explode,
                    shadow=True)
            plt.title('Proportion of Users at risk of HE and Risk of HE due to health issues')
            plt.axis('equal')  # Equal aspect ratio ensures that pie is drawn as a circle.
            pie_chart_filename = 'pie_chart.png'
            pie_chart_path = os.path.join('static', 'Images',pie_chart_filename)
            plt.savefig(pie_chart_path)
            plt.close()

            return bar_chart_filename, pie_chart_filename

csv_manager = UserCSVManager()
user_manager = User(csv_manager)

@app.route("/", methods=["GET", "POST"])
def home():
        return render_template("gp_homepage.html")

@app.route('/gp_1')
def index():
    camps = scrape_camp_locations()
    return render_template('gp_1.html', camps=camps)

#Endpoint to fetch camp options
@app.route('/get_camp_options')
def get_camp_options():
    camps = scrape_camp_locations()
    return jsonify(camps)

#Endpoint to fetch weather data and risk for a selected camp
@app.route('/get_weather_risk')
def get_weather_risk():
    location = request.args.get('location')
    risk, work_duration, break_duration = get_heat_injury_risk(location)
    temperature = get_weather_data(location)
    return jsonify({"location_c": location,"temperature": temperature, "risk": risk, "work_duration": work_duration, "break_duration": break_duration})


@app.route("/gp_2", methods=["GET", "POST"])
def gp_2():
    if request.method == "POST":
        user_id = request.form["user_id"]
        if user_id.lower() == "n":
            return redirect(url_for("gp_2_create_user"))
        else:
            user_exists = user_manager.get_user_details(user_id)
            if user_exists:
                session["user_id"] = user_id
                return redirect(url_for("gp_2_record_temperature", user_id=user_id))
            else:
                return render_template('gp_2_fail.html')
    else:
        return render_template("gp_2.html")

@app.route("/gp_2_create_user", methods=["GET", "POST"])
def gp_2_create_user():
    if request.method == "POST":
        user_id = request.form["user_id"]
        if len(user_id) < 1:
            return render_template("gp_2_create_user.html", error="User ID needs to be at least 1 character. Please try again.")

        existing_user = user_manager.get_user_details(user_id)
        if existing_user:
            return render_template("gp_2_create_user.html", error="User ID already exists. Please enter another user ID.")
        else:
            session["user_id"] = user_id
            return redirect(url_for("gp_2_record_temperature"))
    else:
        return render_template("gp_2_create_user.html")

@app.route("/gp_2_record_temperature", methods=["GET", "POST"])
def gp_2_record_temperature():
    if request.method == "POST":
        user_id = session.get("user_id")
        user_bodytemperature_celsius = float(request.form["body_temperature"])
        user_heartrate_bpm = int(request.form["heart_rate"])
        user_sweatchloride_mmol_l = float(request.form["sweat_chloride"])
        user_obesity = request.form["obesity"]
        user_heart_disease = request.form["heart_disease"]
        user_high_blood_pressure = request.form["high_blood_pressure"]

        current_date = datetime.now().strftime('%Y-%m-%d')
        current_time = datetime.now().strftime('%H:%M:%S')

        user_data = [user_id, current_date, current_time, user_bodytemperature_celsius, user_heartrate_bpm,
                     user_sweatchloride_mmol_l, user_obesity, user_heart_disease, user_high_blood_pressure]
        csv_manager.append_user_data(user_data)

        session['user_data'] = user_data
        return redirect(url_for("gp_2_check_temp_risk"))
    else:
        return render_template("gp_2_record_temperature.html")

@app.route("/gp_2_check_temp_risk")
def gp_2_check_temp_risk():
    user_data = session.get('user_data')
    return render_template("gp_2_check_temp_risk.html", data=user_data)

@app.route("/gp_3", methods=["GET", "POST"])
def gp_3():
    if request.method == 'POST':
        user_id = request.form['user_id']
        if user_id == 'admin':
            users_at_risk_output, heat_related_diseases_output = user_manager.track_heat_exhaustion()
            user_manager.track_heat_exhaustion_for_chart()
            return render_template('gp_3_success.html', user_output=users_at_risk_output,
                                   disease_output=heat_related_diseases_output)
        else:
            return render_template('gp_3_fail.html')
    return render_template('gp_3.html')


if __name__ == "__main__":
    app.run()
