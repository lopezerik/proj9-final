import flask
from flask import render_template
from flask import request
from flask import url_for
import uuid
import sys

import json
import logging

# Date handling 
import arrow # Replacement for datetime, based on moment.js
# import datetime # But we still need time
from dateutil import tz  # For interpreting local times

# database
from pymongo import MongoClient
from bson.objectid import ObjectId

# for random meeting code
import random
import string
import copy

# OAuth2  - Google library implementavailableation for convenience
from oauth2client import client
import httplib2   # used in oauth2 flow

# Google API for services 
from apiclient import discovery

# My Time classes
from ftc import *
###
# Globals
###
import config

if __name__ == "__main__":
    CONFIG = config.configuration()
else:
    CONFIG = config.configuration(proxied=True)

app = flask.Flask(__name__)
app.debug=CONFIG.DEBUG
app.logger.setLevel(logging.DEBUG)
app.secret_key=CONFIG.SECRET_KEY

SCOPES = 'https://www.googleapis.com/auth/calendar.readonly'
CLIENT_SECRET_FILE = CONFIG.GOOGLE_KEY_FILE  ## You'll need this
APPLICATION_NAME = 'MeetMe class project'

MONGO_CLIENT_URL = "mongodb://{}:{}@{}:{}/{}".format(
    CONFIG.DB_USER,
    CONFIG.DB_USER_PW,
    CONFIG.DB_HOST, 
    CONFIG.DB_PORT, 
    CONFIG.DB)

print("Using URL '{}'".format(MONGO_CLIENT_URL))

#############################
#
#  Pages (routed from URLs)
#
#############################

@app.route("/")
@app.route("/index")
def index():
  app.logger.debug("Entering index")
  if 'begin_date' not in flask.session:
    init_session_values()
  return render_template('index.html')

@app.route("/choose")
def choose():
    ## We'll need authorization to list calendars 
    ## I wanted to put what follows into a function, but had
    ## to pull it back here because the redirect has to be a
    ## 'return' 
    app.logger.debug("Checking credentials for Google calendar access")
    credentials = valid_credentials()
    if not credentials:
      app.logger.debug("Redirecting to authorization")
      return flask.redirect(flask.url_for('oauth2callback'))

    gcal_service = get_gcal_service(credentials)
    app.logger.debug("Returned from get_gcal_service")
    flask.g.calendars = list_calendars(gcal_service)
    return render_template('available.html')

'''
- First Sorts the items according to their dates.
- Then sorts the items according to their start time
- Returns sorted list
'''
def sortEvents(master, arrbeg, arrend):
    # sorts an array of TimeBlocks
    dayRange = arrend - arrbeg
    dayRange = dayRange.days
    
    allDays = []
    allDays.append([])
    for i in range(0, dayRange):
        allDays.append([])

    for event in master:
        # check if event is longer than a day
        length = event.end.floor('day') - event.start.floor('day')
        if(length.days != 0):
            # split the event into two, only if we need to/it's in the range
            if(not (event.end.floor('day') > arrend)):
                newEvent = TimeBlock(event.end.floor('day'), event.end, event.summary)
                # make sure we are not adding redundant events
                if(newEvent.start != newEvent.end):
                    master.append(newEvent)
                    event.end = event.start.ceil('day')

        # index = number of days away from the begining of the specified range
        index = (event.start.floor('day').to('utc').floor('day') - 
                arrbeg.floor('day').to('utc').floor('day'))
        index = index.days
        allDays[index].append(event)

    # sort by time
    for i in range(0, len(allDays)):
        allDays[i] = sorted(allDays[i], key=myKey)
    
    print("testing whole sort")
    for day in allDays:
        print("---")
        for event in day:
            print(event)
    return allDays

# used by eventSort for sorting events by start time
def myKey(item):
    return item.start

'''
- Calculates the free blocks given a list of days and the events in each day
- Returns free blocks list
'''
def overallFree(sortedList, arrbeg, arrend, timestart, timeend):
    freeBlocks = []
    
    for i in range(0, len(sortedList)):
        if len(sortedList[i]) == 0:
            # no events on this day
            superFree = {"start": arrbeg.shift(days=i).format("MM-DD-YYYY h:mmA"),
                         "end": arrbeg.shift(days=i, hours=(timeend - timestart)).format("MM-DD-YYYY h:mmA"),
                         "a": "No events on this day"
                        }
            freeBlocks.append(superFree)
        else:
            # initialize master event for the day
            masterStart = arrow.get("1970-01-01T12:00:00-08:00")
            masterEnd = arrow.get("1970-01-01T12:30:00-08:00")
            master = TimeBlock(masterStart, masterEnd, "Master")
            initialized = False
            # loop through events for the day
            # merge events and calc free time for the day 

            for event in sortedList[i]:
                # create timeblock event
                eventStart = arrow.get(event.start)
                eventEnd = arrow.get(event.end)
                eventBlock = TimeBlock(eventStart, eventEnd, event.summary)
                # if we haven't added the first even
                if(not(initialized)):
                    master.initMaster(eventBlock)
                    initialized = True
                else:
                    # else merge with master block
                    master.merge(eventBlock)
            # create free block and calculate free time
            freeStart = ((sortedList[i][0]).start).floor('day')
            freeStart = freeStart.shift(hours=timestart)
            freeEnd = ((sortedList[i][0]).start).floor('day')
            freeEnd = freeEnd.shift(hours=timeend)
            free = FreeBlock(freeStart, freeEnd)
            free.calcFree(master)
                
            # if free time not empty, add it to a g variable
            if(not(free.empty)):
                for block in free.disjointSet:
                    aptStart = block.start.floor('day').shift(hours=timestart)
                    aptEnd = block.start.floor('day').shift(hours=timeend)
                    # if the free block is within the range
                    if(aptStart < block.end <= aptEnd):
                        # add it to the set 
                        free = {"start": block.start.format("MM-DD-YYYY h:mmA"), 
                                "end": block.end.format("MM-DD-YYYY h:mmA"),
                                "a": block.summary
                               }
                        freeBlocks.append(free)
    
    return freeBlocks

'''
- Calculates busy blocks
- Generates a master list of events
- Calls sortEvents and overallFree to calculate free blocks
'''
@app.route("/calculate/<code>/<save>")
def calculateEvents(code, save):
    easySet(code)
    app.logger.debug("Generating master list")
    # Get credentials and gcal_service to pull events
    credentials = valid_credentials()
    if not credentials:
        app.logger.debug("Redirecting to authorization")
        flask.redirect(flask.url_for('myoauth2callback'))
        return calculateEvents(code, save)

    gcal_service = get_gcal_service(credentials)
    app.logger.debug("Returned from get_gcal_service")
    
    # Time parsing for website display and calculations
    timestart = time_to_int(flask.session['begtime'])
    timeend = time_to_int(flask.session['endtime'])

    beg = flask.session["begin_date"]
    end = flask.session["end_date"]

    arrbeg = arrow.get(beg)
    arrbeg = arrbeg.shift(hours=timestart)
    
    arrend = arrow.get(end)
    arrend = arrend.shift(hours=timeend)

    # send to html for display
    flask.g.range = [arrbeg.format("MM-DD-YYYY"), arrend.format("MM-DD-YYYY"), arrbeg.format("h:mmA"), 
                     arrend.format("h:mmA")]

    # loop through all calenders that were checked on the main page
    checked = request.values.getlist('checked')
    flask.g.checked = checked
    masterList = []
    results = []
    for cal in checked:
    # grab events from cal
        events = gcal_service.events().list(calendarId=cal, orderBy='startTime', 
                        singleEvents=True, timeMin=beg, timeMax=end).execute()
        items = events["items"]
        calName = events['summary']
        for item in items:
            # skip if nonblocking event
            if ('transparency' in item) and (item['transparency'] != "opaque"):
                continue

            # some events dont have 'dateTime', all day events
            if('dateTime' not in item['start']):
                start = item['start']['date']
            else:
                start = item['start']['dateTime']
            start = arrow.get(start)
            startClone = start.clone()
            startClone = startClone.floor('day')
            startClone = startClone.shift(hours=timestart)

            # some events dont have 'dateTime', all day events
            if('dateTime' not in item['end']):
                end = item['end']['date']
            else:
                end = item['end']['dateTime']
            end = arrow.get(end)
            endClone = end.clone()
            endClone = endClone.floor('day')
            endClone = endClone.shift(hours=timeend)

            # create new event and add to our master list of events
            newEvent = TimeBlock(start, end, calName)
            masterList.append(newEvent)
            # if in our range
            if (startClone < end <= endClone):
                app.logger.debug("Adding a busy appointment")
                appt = { "summary": item['summary'],
                      "start": start.format("MM-DD-YYYY h:mmA"),
                      "end": end.format("MM-DD-YYYY h:mmA"),
                      "startArrow": start,
                      "endArrow": end,
                      "cal": calName
                      }
                # append appointment
                results.append(appt)

    # sort our blocking results before display
    results = sorted(results, key=resultsKey)
    # send our final list to html for display
    flask.g.busy = results

    # sort our master list with our helper function
    sortedEvents = sortEvents(masterList, arrbeg, arrend)
    
    # calculate free time with our helper function
    freeBlocks = overallFree(sortedEvents, arrbeg, arrend, timestart, timeend)
    flask.g.free = freeBlocks
    flask.g.meeting_code = code
    # if we are going to save the info in the database
    if(save == 'true'):
        # kind of hacky
        # we cant store our TimeBlock objects in the database :(
        # so we copy the list
        emptySort = copy.deepcopy(sortedEvents)
        # clear the copy
        for li in emptySort:
            del li[:]
        # convert items from TimeBlocks to tuples
        for i in range(0, len(emptySort)):
            for event in sortedEvents[i]:
                tup = (str(event.start), str(event.end), event.summary)
                emptySort[i].append(tup)
        # save to database
        # try to access database
        try: 
            dbclient = MongoClient(MONGO_CLIENT_URL)
            db = getattr(dbclient, CONFIG.DB)
            meeting = db["Meeting:" + code]
        except:
            print("Failure opening database.  Is Mongo running? Correct password?")
            sys.exit(1)
        # database success
        for item in meeting.find({"code": "Meeting:" + code}):
            item_id = str(item.get('_id'))
            # push list of sorted events into database
            item = meeting.find_one_and_update(
                {'_id': ObjectId(item_id)},
                {"$push": {
                 "master_list": emptySort
                }}
                )
        return render_options(code)
    else:
        return flask.render_template('busy.html')

# used by calculate to sort blocking times by start time
def resultsKey(item):
    return item['startArrow']

# takes multiple lists of master events and adds all the events into one list
def masterMerge(master_list):
    combined = []
    for master in master_list:
        for day in master:
            for event in day:
                combined.append(event)
    return combined

# show the current meeting options
@app.route("/renderOptions/<code>")
def render_options(code):
    # try to access database
    try: 
        dbclient = MongoClient(MONGO_CLIENT_URL)
        db = getattr(dbclient, CONFIG.DB)
        meeting = db["Meeting:" + code]
    except:
        print("Failure opening database.  Is Mongo running? Correct password?")
        sys.exit(1)
    # database success
    for item in meeting.find({"code": "Meeting:" + code}):
        new_master_list = masterMerge(item["master_list"])
        arrbeg = arrow.get(item['start'])
        arrend = arrow.get(item['end'])
        timestart = item['timestart']
        timeend = item['timeend']
    # sort
    # continued hackiness
    # now we need to convert back from list into TimeBlock for sorting purposes
    toTimeBlock = copy.deepcopy(new_master_list)
    for i in range(0, len(toTimeBlock)):
        toTimeBlock[i] = TimeBlock(arrow.get(toTimeBlock[i][0]), arrow.get(toTimeBlock[i][1]), 
                          toTimeBlock[i][2])
    # sort our converted objects appropriateley
    sortedMaster = sortEvents(toTimeBlock, arrbeg, arrend)
    new_free_blocks = overallFree(sortedMaster, arrbeg, arrend, timestart, timeend)
    flask.g.free = new_free_blocks
    # update session
    new_range = [arrbeg.format("MM-DD-YYYY"), arrend.format("MM-DD-YYYY"), 
                 arrbeg.format("h:mmA"), arrend.format("h:mmA")]
    flask.g.range = new_range
    flask.g.meeting_code = code
    return flask.render_template('options.html')

'''
- this is a variation on addToMeeting.
- the reason we use it is because session variables are not set if you are not the 
  meeting creator.
- this variation sets the session variables before calculating in order to get 
  the correct results.
'''
@app.route('/contToMeeting/<save>/<code>', methods=['POST'])
def contToMeeting(save, code):
    # update session
    flask.g.meeting_code = code
    flask.session["meeting_code"] = code
    easySet(code)
    app.logger.debug("Checking credentials for Google calendar access")
    credentials = valid_credentials()
    if not credentials:
      app.logger.debug("Redirecting to authorization")
      flask.redirect(flask.url_for('myoauth2callback'))
      return contToMeeting(save, code)

    gcal_service = get_gcal_service(credentials)
    app.logger.debug("Returned from get_gcal_service")
    flask.g.calendars = list_calendars(gcal_service)


    if(save == 'true'):
        return calculateEvents(code, 'true')
    else:
        return render_template('available.html')

@app.route('/addToMeeting/<save>', methods=['POST'])
def addToMeeting(save):
    # update session
    code = request.form.get('meeting_code')
    flask.g.meeting_code = code
    flask.session["meeting_code"] = code
    easySet(code)

    app.logger.debug("Checking credentials for Google calendar access")
    credentials = valid_credentials()
    if not credentials:
      app.logger.debug("Redirecting to authorization")
      return flask.redirect(flask.url_for('oauth2callback'))

    gcal_service = get_gcal_service(credentials)
    app.logger.debug("Returned from get_gcal_service")
    flask.g.calendars = list_calendars(gcal_service)

    # if true calculate free times and save to database
    if(save == 'true'):
        return calculateEvents(code, 'true')
    # else just show availabilty
    else:
        return render_template('available.html')

@app.route("/newCode")
def newMeetingCode():
    # try to access database
    try: 
        dbclient = MongoClient(MONGO_CLIENT_URL)
        db = getattr(dbclient, CONFIG.DB)
        meetings = db.meeting_codes
    except:
        print("Failure opening database.  Is Mongo running? Correct password?")
        sys.exit(1)
    
    # database success
    unique = False
    # grab a code until it's unique
    while(not unique):
        new_code = random_code()
        if(unique_code(meetings, new_code)):
            unique = True

    # add code to database
    meetings.insert_one({"code": new_code})
    return new_code

def random_code():
    # random string generator from: 
    # https://stackoverflow.com/questions/2257441/random-string-generation
    # -with-upper-case-letters-and-digits-in-python
    return ''.join(random.choice(string.ascii_uppercase + string.digits) for _ in range(6))

# tests to see if code is unique
# if code is in database, then it is not unique
def unique_code(database, code):
    search = database.find({"code": code})
    if search.count() == 0:
        # code not in database, so it's unique
        app.logger.debug("Found unique code")
        return True
    app.logger.debug("Not a unique code, try again")
    return False

# tests a code to see if it exists in our database
# used to service html requests
@app.route("/checkCode", methods=['POST'])
def checkCode():
    # try to access database
    try: 
        dbclient = MongoClient(MONGO_CLIENT_URL)
        db = getattr(dbclient, CONFIG.DB)
        meeting = db.meeting_codes
    except:
        print("Failure opening database.  Is Mongo running? Correct password?")
        sys.exit(1)
    
    # database success

    code = request.form.get('code')
    code = code.strip().upper()
    if(not unique_code(meeting, code)):
        # code exists
        flask.g.exists = 'true'
        flask.g.meeting_code = code
        flask.session["meeting_code"] = code
        return flask.render_template('index.html')
    else:
        flask.g.exists = 'false'
        flask.g.meeting_code = code
        return flask.render_template('index.html')
    
#############################
#
#  Helper functions (routed from URLs)
#
#############################

@app.route("/my/<url>")
def my_redirect(url):
    return flask.render_template(url + ".html")

####
#
#  Google calendar authorization:
#      Returns us to the main /choose screen after inserting
#      the calendar_service object in the session state.  May
#      redirect to OAuth server first, and may take multiple
#      trips through the oauth2 callback function.
#
#  Protocol for use ON EACH REQUEST: 
#     First, check for valid credentials
#     If we don't have valid credentials
#         Get credentials (jump to the oauth2 protocol)
#         (redirects back to /choose, this time with credentials)
#     If we do have valid credentials
#         Get the service object
#
#  The final result of successful authorization is a 'service'
#  object.  We use a 'service' object to actually retrieve data
#  from the Google services. Service objects are NOT serializable ---
#  we can't stash one in a cookie.  Instead, on each request we
#  get a fresh serivce object from our credentials, which are
#  serializable. 
#
#  Note that after authorization we always redirect to /choose;
#  If this is unsatisfactory, we'll need a session variable to use
#  as a 'continuation' or 'return address' to use instead. 
#
####

def valid_credentials():
    """
    Returns OAuth2 credentials if we have valid
    credentials in the session.  This is a 'truthy' value.
    Return None if we don't have credentials, or if they
    have expired or are otherwise invalid.  This is a 'falsy' value. 
    """
    if 'credentials' not in flask.session:
      return None

    credentials = client.OAuth2Credentials.from_json(
        flask.session['credentials'])

    if (credentials.invalid or
        credentials.access_token_expired):
      return None
    return credentials


def get_gcal_service(credentials):
  """
  We need a Google calendar 'service' object to obtain
  list of calendars, busy times, etc.  This requires
  authorization. If authorization is already in effect,
  we'll just return with the authorization. Otherwise,
  control flow will be interrupted by authorization, and we'll
  end up redirected back to /choose *without a service object*.
  Then the second call will succeed without additional authorization.
  """
  app.logger.debug("Entering get_gcal_service")
  http_auth = credentials.authorize(httplib2.Http())
  service = discovery.build('calendar', 'v3', http=http_auth)
  app.logger.debug("Returning service")
  return service

@app.route('/oauth2callback')
def oauth2callback():
  """
  The 'flow' has this one place to call back to.  We'll enter here
  more than once as steps in the flow are completed, and need to keep
  track of how far we've gotten. The first time we'll do the first
  step, the second time we'll skip the first step and do the second,
  and so on.
  """
  app.logger.debug("Entering oauth2callback")
  flow =  client.flow_from_clientsecrets(
      CLIENT_SECRET_FILE,
      scope= SCOPES,
      redirect_uri=flask.url_for('oauth2callback', _external=True))
  ## Note we are *not* redirecting above.  We are noting *where*
  ## we will redirect to, which is this function. 
  
  ## The *second* time we enter here, it's a callback 
  ## with 'code' set in the URL parameter.  If we don't
  ## see that, it must be the first time through, so we
  ## need to do step 1. 
  app.logger.debug("Got flow")
  if 'code' not in flask.request.args:
    app.logger.debug("Code not in flask.request.args")
    auth_uri = flow.step1_get_authorize_url()
    return flask.redirect(auth_uri)
    ## This will redirect back here, but the second time through
    ## we'll have the 'code' parameter set
  else:
    ## It's the second time through ... we can tell because
    ## we got the 'code' argument in the URL.
    app.logger.debug("Code was in flask.request.args")
    auth_code = flask.request.args.get('code')
    credentials = flow.step2_exchange(auth_code)
    flask.session['credentials'] = credentials.to_json()
    ## Now I can build the service and execute the query,
    ## but for the moment I'll just log it and go back to
    ## the main screen
    app.logger.debug("Got credentials")
    flask.g.meeting_code = flask.session["meeting_code"]
    flask.g.range = flask.session["new_range"]
    return my_redirect("invite")

@app.route('/myoauth2callback')
def myoauth2callback():
  """
  The 'flow' has this one place to call back to.  We'll enter here
  more than once as steps in the flow are completed, and need to keep
  track of how far we've gotten. The first time we'll do the first
  step, the second time we'll skip the first step and do the second,
  and so on.
  """
  app.logger.debug("Entering oauth2callback")
  flow =  client.flow_from_clientsecrets(
      CLIENT_SECRET_FILE,
      scope= SCOPES,
      redirect_uri=flask.url_for('oauth2callback', _external=True))
  ## Note we are *not* redirecting above.  We are noting *where*
  ## we will redirect to, which is this function. 
  
  ## The *second* time we enter here, it's a callback 
  ## with 'code' set in the URL parameter.  If we don't
  ## see that, it must be the first time through, so we
  ## need to do step 1. 
  app.logger.debug("Got flow")
  if 'code' not in flask.request.args:
    app.logger.debug("Code not in flask.request.args")
    auth_uri = flow.step1_get_authorize_url()
    return flask.redirect(auth_uri)
    ## This will redirect back here, but the second time through
    ## we'll have the 'code' parameter set
  else:
    ## It's the second time through ... we can tell because
    ## we got the 'code' argument in the URL.
    app.logger.debug("Code was in flask.request.args")
    auth_code = flask.request.args.get('code')
    credentials = flow.step2_exchange(auth_code)
    flask.session['credentials'] = credentials.to_json()
    ## Now I can build the service and execute the query,
    ## but for the moment I'll just log it and go back to
    ## the main screen
    app.logger.debug("Got credentials")
    flask.g.meeting_code = flask.session["meeting_code"]
    flask.g.range = flask.session["new_range"]
    return
#
#  Option setting:  Buttons or forms that add some
#     information into session state.  Don't do the
#     computation here; use of the information might
#     depend on what other information we have.
#   Setting an option sends us back to the main display
#      page, where we may put the new information to use. 
#
#####

@app.route('/setrange', methods=['POST'])
def setrange():
    """
    User chose a date range with the bootstrap daterange
    widget.
    """
    app.logger.debug("Entering setrange")  
    flask.flash("Setrange gave us '{}'".format(
      request.form.get('daterange')))
    daterange = request.form.get('daterange')
    flask.session['daterange'] = daterange
    begtime = request.form.get('timestart')
    flask.session['begtime'] = begtime
    endtime = request.form.get('timeend')
    flask.session['endtime'] = endtime
    daterange_parts = daterange.split()
    flask.session['begin_date'] = interpret_date(daterange_parts[0])
    flask.session['end_date'] = interpret_date(daterange_parts[2])
    app.logger.debug("Setrange parsed {} - {}  dates as {} - {}".format(
      daterange_parts[0], daterange_parts[1], 
      flask.session['begin_date'], flask.session['end_date']))
    return flask.redirect(flask.url_for("choose"))

# sets session based on database info
def easySet(code):
    app.logger.debug("Entering easysetrange")  
    # try to access database
    try: 
        dbclient = MongoClient(MONGO_CLIENT_URL)
        db = getattr(dbclient, CONFIG.DB)
        meeting = db["Meeting:" + code]
    except:
        print("Failure opening database.  Is Mongo running? Correct password?")
        sys.exit(1)
    # database success
    for item in meeting.find({"code": "Meeting:" + code}):
        arrbeg = arrow.get(item['start'])
        arrend = arrow.get(item['end'])
        timestart = item['timestart']
        timeend = item['timeend']
        begtime = item['begtime']
        endtime = item['endtime']
    # update session
    beg = interpret_date(arrbeg.floor('day').format("MM/DD/YYYY"))
    end = interpret_date(arrend.floor('day').format("MM/DD/YYYY"))
    flask.session['begin_date'] = beg
    flask.session['end_date'] = end
    flask.session['begtime'] = begtime
    flask.session['endtime'] = endtime

    new_range = [arrbeg.format("MM-DD-YYYY"), arrend.format("MM-DD-YYYY"), 
                 arrbeg.format("h:mmA"), arrend.format("h:mmA")]
    flask.g.range = new_range
    flask.g.meeting_code = code

    flask.session["new_range"] = new_range
    return

# used when creating a new meeting
@app.route('/newsetrange', methods=['POST'])
def newsetrange():
    """
    User chose a date range with the bootstrap daterange
    widget.
    """
    app.logger.debug("Entering newsetrange")  
    daterange = request.form.get('daterange')
    flask.session['daterange'] = daterange
    begtime = request.form.get('timestart')
    flask.session['begtime'] = begtime
    endtime = request.form.get('timeend')
    flask.session['endtime'] = endtime
    daterange_parts = daterange.split()
    beg = interpret_date(daterange_parts[0])
    end = interpret_date(daterange_parts[2])
    flask.session['begin_date'] = beg
    flask.session['end_date'] = end
    app.logger.debug("Setrange parsed {} - {}  dates as {} - {}".format(
      daterange_parts[0], daterange_parts[1], 
      flask.session['begin_date'], flask.session['end_date']))
    arrbeg = arrow.get(beg).shift(hours=(time_to_int(begtime)))
    arrend = arrow.get(end).shift(hours=(time_to_int(endtime)))
    new_range = [arrbeg.format("MM-DD-YYYY"), arrend.format("MM-DD-YYYY"), 
                 arrbeg.format("h:mmA"), arrend.format("h:mmA")]
    flask.g.range = new_range
    flask.session["new_range"] = new_range
    # database
    try: 
        dbclient = MongoClient(MONGO_CLIENT_URL)
        db = getattr(dbclient, CONFIG.DB)
    except:
        print("Failure opening database.  Is Mongo running? Correct password?")
        sys.exit(1)
    
    # acquire a unique meeting code
    new_code = newMeetingCode()
    flask.g.meeting_code = new_code
    # can't start a collection with a number
    new_code = "Meeting:" + new_code
    # add new collection to database
    timestart = time_to_int(begtime)
    timeend = time_to_int(endtime)
    meeting = db.create_collection(new_code)
    meeting.insert_one({"start": str(arrbeg), "end": str(arrend), 
                        "timestart": timestart, "timeend": timeend,
                        "begtime": begtime, "endtime": endtime,
                        "master_list": [], "code": new_code})
    
    return my_redirect("invite")


####
#
#   Initialize session variables 
#
####

def init_session_values():
    """
    Start with some reasonable defaults for date and time ranges.
    Note this must be run in app context ... can't call from main. 
    """
    # Default date span = tomorrow to 1 week from now
    now = arrow.now('local')     # We really should be using tz from browser
    tomorrow = now.replace(days=+1)
    nextweek = now.replace(days=+7)
    flask.session["begin_date"] = tomorrow.floor('day').isoformat()
    flask.session["end_date"] = nextweek.ceil('day').isoformat()
    flask.session["daterange"] = "{} - {}".format(
        tomorrow.format("MM/DD/YYYY"),
        nextweek.format("MM/DD/YYYY"))
    # Default time span each day, 8 to 5
    flask.session["begin_time"] = interpret_time("9am")
    flask.session["end_time"] = interpret_time("5pm")

def interpret_time( text ):
    """
    Read time in a human-compatible format and
    interpret as ISO format with local timezone.
    May throw exception if time can't be interpreted. In that
    case it will also flash a message explaining accepted formats.
    """
    app.logger.debug("Decoding time '{}'".format(text))
    time_formats = ["ha", "h:mma",  "h:mm a", "H:mm"]
    try: 
        as_arrow = arrow.get(text, time_formats).replace(tzinfo=tz.tzlocal())
        as_arrow = as_arrow.replace(year=2016) #HACK see below
        app.logger.debug("Succeeded interpreting time")
    except:
        app.logger.debug("Failed to interpret time")
        flask.flash("Time '{}' didn't match accepted formats 13:30 or 1:30pm"
              .format(text))
        raise
    return as_arrow.isoformat()
    #HACK #Workaround
    # isoformat() on raspberry Pi does not work for some dates
    # far from now.  It will fail with an overflow from time stamp out
    # of range while checking for daylight savings time.  Workaround is
    # to force the date-time combination into the year 2016, which seems to
    # get the timestamp into a reasonable range. This workaround should be
    # removed when Arrow or Dateutil.tz is fixed.
    # FIXME: Remove the workaround when arrow is fixed (but only after testing
    # on raspberry Pi --- failure is likely due to 32-bit integers on that platform)


def interpret_date( text ):
    """
    Convert text of date to ISO format used internally,
    with the local time zone.
    """
    try:
      as_arrow = arrow.get(text, "MM/DD/YYYY").replace(
          tzinfo=tz.tzlocal())
    except:
        flask.flash("Date '{}' didn't fit expected format 12/31/2001")
        raise
    return as_arrow.isoformat()

def next_day(isotext):
    """
    ISO date + 1 day (used in query to Google calendar)
    """
    as_arrow = arrow.get(isotext)
    return as_arrow.replace(days=+1).isoformat()

####
#
#  Functions (NOT pages) that return some information
#
####
  
def list_calendars(service):
    """
    Given a google 'service' object, return a list of
    calendars.  Each calendar is represented by a dict.
    The returned list is sorted to have
    the primary calendar first, and selected (that is, displayed in
    Google Calendars web app) calendars before unselected calendars.
    """
    app.logger.debug("Entering list_calendars")  
    calendar_list = service.calendarList().list().execute()["items"]
    result = [ ]
    for cal in calendar_list:
        kind = cal["kind"]
        id = cal["id"]
        if "description" in cal: 
            desc = cal["description"]
        else:
            desc = "(no description)"
        summary = cal["summary"]
        # Optional binary attributes with False as default
        selected = ("selected" in cal) and cal["selected"]
        primary = ("primary" in cal) and cal["primary"]
        
        result.append(
          { "kind": kind,
            "id": id,
            "summary": summary,
            "selected": selected,
            "primary": primary
            })
    return sorted(result, key=cal_sort_key)


def cal_sort_key( cal ):
    """
    Sort key for the list of calendars:  primary calendar first,
    then other selected calendars, then unselected calendars.
    (" " sorts before "X", and tuples are compared piecewise)
    """
    if cal["selected"]:
       selected_key = " "
    else:
       selected_key = "X"
    if cal["primary"]:
       primary_key = " "
    else:
       primary_key = "X"
    return (primary_key, selected_key, cal["summary"])

def time_to_int(time):
    parts = time.split(':')
    if parts[1] == '30':
        return int(parts[0]) + .5
    return int(parts[0])

#################
#
# Functions used within the templates
#
#################

@app.template_filter( 'fmtdate' )
def format_arrow_date( date ):
    try: 
        normal = arrow.get( date )
        return normal.format("ddd MM/DD/YYYY")
    except:
        return "(bad date)"

@app.template_filter( 'fmttime' )
def format_arrow_time( time ):
    try:
        normal = arrow.get( time )
        return normal.format("HH:mm")
    except:
        return "(bad time)"
    
#############


if __name__ == "__main__":
  # App is created above so that it will
  # exist whether this is 'main' or not
  # (e.g., if we are running under green unicorn)
  app.run(port=CONFIG.PORT,host="0.0.0.0", threaded=True)
    
