# scrapeVehicles.py loops through all cities listed on Craigslist and scrapes every vehicle for sale and adds it to cities.db
# this program will take awhile to run, don't run unless you're willing to let it sit for at least 2 hours
# the database is commited after we've finished scraping each city, so the program can be terminated and results are still saved if you need to exit for any reason

import os
import psycopg2
from json import loads
from lxml import html
from datetime import datetime
from requests_html import HTMLSession
from connect import connect
from crawlCities import storeCities

def runScraper():
    storeCities()
    
    conn = connect()
    
    #the cities table contains around 480 cities, all of the craigslist pages in north america
    curs = conn.cursor()
    curs.execute("SELECT * FROM cities")
    
    citiesList = []
    for city in curs.fetchall():
        citiesList.append(city)

    curs.execute('''CREATE TABLE IF NOT EXISTS vehicles(id BIGINT PRIMARY KEY, url TEXT, region TEXT, region_url TEXT, 
    price BIGINT, year BIGINT, manufacturer TEXT, model TEXT, condition TEXT, cylinders TEXT, fuel TEXT, 
    odometer BIGINT, title_status TEXT, transmission TEXT, VIN TEXT, drive TEXT, size TEXT, type TEXT, paint_color TEXT, image_url TEXT, 
    description TEXT, county TEXT, state TEXT, lat REAL, long REAL)''')

    session = HTMLSession()
    
    #scraped counts all entries gathered
    scraped = 0
    
    #carBrands dictate what qualifies as a brand so we can snatch that data from the 'model' tag
    carBrands = ["ford", "toyota", "chevrolet", "chev", "chevy", "honda", "jeep", "hyundai", "subaru",
                 "kia", "gmc", "ram", "dodge", "mercedes-benz", "mercedes", "mercedesbenz",
                 "volkswagen", "vw", "bmw", "saturn", "land rover", "landrover", "pontiac", 
                 "mitsubishi", "lincoln", "volvo", "mercury", "harley-davidson", "harley", 
                 "rover", "buick", "cadillac", "infiniti", "infinity", "audi", "mazda", "chrysler",
                 "acura", "lexus", "nissan", "datsun", "jaguar", "alfa", "alfa-romeo", "aston", "aston-martin",
                 "ferrari", "fiat", "hennessey", "porsche", "noble", "morgan", "mini", "tesla"]
    
    #if the car year is beyond next year, we toss it out. this variable is used later
    nextYear = datetime.now().year + 1
    
    #simple txt file mechanism to track scraping progress
    fileName = os.path.dirname(os.path.abspath(__file__)) + "/static/trackVehicleScraping.txt"
    exists = os.path.isfile(fileName)
    if not exists:
        tracker = open(fileName, "w")
        tracker.write("0")
        tracker.close()
    
    with open(fileName, "r") as tracker:
        cities = int(tracker.readlines()[0])
    citiesCount = len(citiesList)
    citiesList = citiesList[cities:]
    
    for city in citiesList:
        scrapedInCity = 0
        cities += 1
        print(f"Scraping vehicles from {city[2]}, {citiesCount - cities} cities remain")
        empty = False
        
        #scrapedIds is used to store each individual vehicle id from a city, therefore we can delete vehicle records from the database
        #if their id is no longer in scrapedIds under the assumption that the entry has been removed from craigslist
        scrapedIds = set([])
        
        #track items skipped that are already in the database
        skipped = 0
        
        #this loop executes until we are out of search results, craigslist sets this limit at 3000 and cities often contain the full 3000 records (but not always)        
        while not empty:
            print(f"Gathering entries {scrapedInCity} through {scrapedInCity + 120}")
            
            #now we scrape
            try:
                searchUrl = f"{city[1]}/d/cars-trucks/search/cta?s={scrapedInCity}"
                page = session.get(searchUrl)
            except Exception as e:
                #catch any excpetion and continue the loop if we cannot access a site for whatever reason
                print(f"Failed to reach {searchUrl}, entries have been dropped: {e}")
                scrapedInCity += 120
                continue
            
            #each search page contains 120 entries
            scrapedInCity += 120
            tree = html.fromstring(page.content)
            
            #the following line returns a list of urls for different vehicles
            vehicles = tree.xpath('//a[@class="result-image gallery"]')
            if len(vehicles) == 0:
                #if we no longer have entries, continue to the next city
                empty = True
                continue
            vehiclesList = []
            for item in vehicles:
                vehicleDetails = []
                vehicleDetails.append(item.attrib["href"])
                try:
                    #this code attempts to grab the price of the vehicle. some vehicles dont have prices (which throws an exception)
                    #and we dont want those which is why we toss them
                    vehicleDetails.append(item[0].text)
                except:
                    continue
                vehiclesList.append(vehicleDetails)
            
            #loop through each vehicle
            for item in vehiclesList:
                url = item[0]
                try:
                    idpk = int(url.split("/")[-1].strip(".html"))
                except ValueError as e:
                    print("{} does not have a valid id: {}".format(url, e))
                
                #add the id to scrapedIds for database cleaning purposes
                scrapedIds.add(idpk)
                
                #vehicle id is a primary key in this database so we cant have repeats. if a record with the same url is found, we continue
                #the loop as the vehicle has already been stored                
                curs.execute(f"SELECT 1 FROM vehicles WHERE id = {idpk}")
                if len(curs.fetchall()) != 0:
                    skipped += 1
                    continue
                
                vehicleDict = {}
                vehicleDict["price"] = int(item[1].replace(",", "").strip("$"))
                
                try:
                    #grab each individual vehicle page
                    page = session.get(url)
                    tree = html.fromstring(page.content)
                except:
                    print(f"Failed to reach {url}, entry has been dropped")
                    continue
                
                attrs = tree.xpath('//span//b')
                #this fetches a list of attributes about a given vehicle. each vehicle does not have every specific attribute listed on craigslist
                #so this code gets a little messy as we need to handle errors if a car does not have the attribute we're looking for
                for item in attrs:
                    try:
                        #model is the only attribute without a specific tag on craigslist, so if this code fails it means that we've grabbed the model of the vehicle
                        k = item.getparent().text.strip()
                        k = k.strip(":")
                    except:
                        k = "model"
                    try:
                        #this code fails if item=None so we have to handle it appropriately
                        vehicleDict[k] = item.text.strip()
                    except:
                        continue
                    
                #we will assume that each of these variables are None until we hear otherwise
                #that way, try/except clauses can simply pass and leave these values as None
                price = None
                year = None
                manufacturer = None
                model = None
                condition = None
                cylinders = None
                fuel = None
                odometer = None
                title_status = None
                transmission = None
                VIN = None
                drive = None
                size = None
                vehicle_type = None
                paint_color = None
                image_url = None
                lat = None
                long = None
                description = None
                
                #now this code gets redundant. if we picked up a specific attr in the vehicleDict then we can change the variable from None.
                #integer attributes (price/odometer) are handled in case the int() is unsuccessful, but i have never seen that be the case
                if "price" in vehicleDict:
                    try:
                        price = int(vehicleDict["price"])
                    except Exception as e:
                        print(f"Could not parse price: {e}")
                if "odomoter" in vehicleDict:
                    try:
                        odometer = int(vehicleDict["odometer"])
                    except Exception as e:
                        print(f"Could not parse odometer: {e}")
                if "condition" in vehicleDict:
                    condition = vehicleDict["condition"]
                if "model" in vehicleDict:
                    #model actually contains 3 variables that we'd like: year, manufacturer, and model (which we call model)
                    try:
                        year = int(vehicleDict["model"][:4])
                        if year > nextYear:
                            year = None
                    except:
                        year = None
                    model = vehicleDict["model"][5:]
                    foundManufacturer = False
                    #we parse through each word in the description and search for a match with carBrands (at the top of the program)
                    #if a match is found then we have our manufacturer, otherwise we set model to the entire string and leave manu blank
                    for word in model.split():
                        if word.lower() in carBrands:
                            foundManufacturer = True
                            model = ""
                            #resolve conflicting manufacturer titles
                            manufacturer = word.lower()
                            if manufacturer == "chev" or manufacturer == "chevy":
                                manufacturer = "chevrolet"
                            if manufacturer == "mercedes" or manufacturer == "mercedesbenz":
                                manufacturer = "mercedes-benz"
                            if manufacturer == "vw":
                                manufacturer = "volkswagen"
                            if manufacturer == "landrover":
                                manufacturer = "land rover"
                            if manufacturer == "harley":
                                manufacturer = "harley-davidson"
                            if manufacturer == "infinity":
                                manufacturer = "infiniti"
                            if manufacturer == "alfa":
                                manufacturer = "alfa-romeo"
                            if manufacturer == "aston":
                                manufacturer = "aston-martin"
                            continue
                        if foundManufacturer:
                            model = model + word.lower() + " "
                    model = model.strip()
                if "cylinders" in vehicleDict:
                    cylinders = vehicleDict["cylinders"]
                if "fuel" in vehicleDict:
                    fuel = vehicleDict["fuel"]
                if "odometer" in vehicleDict:
                    odometer = vehicleDict["odometer"]
                if "title status" in vehicleDict:
                    title_status = vehicleDict["title status"]    
                if "transmission" in vehicleDict:
                    transmission = vehicleDict["transmission"]
                if "VIN" in vehicleDict:
                    VIN = vehicleDict["VIN"]
                if "drive" in vehicleDict:
                    drive = vehicleDict["drive"]
                if "size" in vehicleDict:
                    size = vehicleDict["size"]
                if "type" in vehicleDict:
                    vehicle_type = vehicleDict["type"]
                if "paint color" in vehicleDict:
                    paint_color = vehicleDict["paint color"]
                    
                #now lets fetch the image url if exists
                
                try:
                    img = tree.xpath('//div[@class="slide first visible"]//img')
                    image_url = img[0].attrib["src"]
                except:
                    pass
                
                #try to fetch lat/long and city/state, remain as None if they do not exist
                
                try:
                    location = tree.xpath("//div[@id='map']")
                    lat = float(location[0].attrib["data-latitude"])
                    long = float(location[0].attrib["data-longitude"])
                except Exception as e:
                    pass
                                
                #try to fetch a vehicle description, remain as None if it does not exist
                
                try:
                    location = tree.xpath("//section[@id='postingbody']")
                    description = location[0].text_content().replace("\n", " ").replace("QR Code Link to This Post", "").strip()
                except:
                    pass
                    
                
                #finally we get to insert the entry into the database
                curs.execute('''INSERT INTO vehicles(id, url, region, region_url, price, year, manufacturer, model, condition,
                cylinders, fuel,odometer, title_status, transmission, VIN, drive, size, type, 
                paint_color, image_url, description, lat, long, state)
                VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)''', 
                    (idpk, url, city[2], city[1], price, year, manufacturer, model, condition, cylinders,
                     fuel, odometer, title_status, transmission, VIN, drive, 
                     size, vehicle_type, paint_color, image_url, description, lat, long, city[3]))
                
                scraped += 1
            #these lines will execute every time we grab a new page (after 120 entries)
            print("{} vehicles scraped".format(scraped))
        
        #now to clean the database we grab all urls from the city that are already logged
        curs.execute("SELECT id FROM vehicles WHERE region_url = '{}'".format(city[1]))
        deleted = 0
        
        #if a given id is not in scrapedIds (the ids that we just scraped) then the entry no longer exists and we remove it
        for oldId in curs.fetchall():
            if int(oldId[0]) not in scrapedIds:
                curs.execute("DELETE FROM vehicles WHERE id = '{}'".format(oldId[0]))
                deleted += 1
        print("Deleted {} old records, {} records skipped as they are already stored".format(deleted, skipped))
        conn.commit()
        
        #update progress file
        with open(fileName, "w") as tracker:
            tracker.write(str(cities))
            
    #delete tracker file
    os.remove(fileName)
    count = curs.execute("SELECT Count(*) FROM vehicles")
    print("Table vehicles successfully updated, {} entries exist".format(\
        curs.fetchall()[0][0]))
    conn.close()
    
def main():
    runScraper()


if __name__ == "__main__":
    main()
