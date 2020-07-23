"""
This is an example program for how to use the L2L Dispatch API to read and write data in the Dispatch system.

This code is written for Python 3.7+ and runs on any platform supported by Python 3.7 and the python-requests library.
To use this code, you need to make sure python 3.7 is installed, and then create a virtual environment using a command
like:
    $ python3.7 -m venv ./pyenv

Then you need to install the dependencies with a command like:
    $ pyenv/bin/pip install -r requirements.txt

To run this code, you would then run:
    $ pyenv/bin/python main.py
"""
# Standard python packages we use
import argparse, json, random, time
from datetime import datetime, timedelta

# this is the http client library we use here, but there are many others that can be used. The aiohttp and httpx
# projects are great alternatives for modern python3 that support Python 3's asyncio framework.
import requests


# These are the standard datetime string formats that the Dispatch API supports
API_MINUTE_FORMAT = "%Y-%m-%d %H:%M"
API_SECONDS_FORMAT = "%Y-%m-%d %H:%M:%S"


def main():
    args = argparse.ArgumentParser(description="L2L API Client")
    args.add_argument("--dbg", action="store_true", help="Print out verbose api output for debugging")

    args.add_argument("server", action="store", nargs=1, help="Specify a hostname to use as the server")
    args.add_argument("site", action="store", type=int, nargs=1, help="Specify the site id to operate against")
    args.add_argument("user", action="store", nargs=1, help="Specify the username for a user to use in the test")

    # This example has you pass your API key in on the command line. Note that you should not do this in your
    # production code. The API Key MUST be kept secret, and effective secrets management is outside the scope
    # of this document. Make sure you don't hard code your api key into your source code, and usually you should
    # expose it to your production code through an environment variable.
    args.add_argument("apikey", action="store", nargs=1, help="Specify an API key to use for authentication")

    cmdline = args.parse_args()
    dbg = cmdline.dbg
    server = cmdline.server[0]
    apikey = cmdline.apikey[0]
    site = cmdline.site[0]
    testuser = cmdline.user[0]
    baseurl = f'https://{server}/api/1.0/'

    # Every API call needs some arguments in the GET query args, or in the POST body - the API key is always required.
    args = {'auth': apikey}

    ###################################################################################################################
    # This shows how to use the API to look up information about a Site. For this application, the specified site must
    # be a test site so that we can avoid any accidents with production data. For production code, you don't need to do
    # this kind of check as you'll need to work against production sites.
    #
    # Note that we are using a function to check the api results - API calls can fail for a variety of reasons and
    # your code should make sure to check the results.  Also, API calls that read data should always use an HTTP GET
    # operation.
    #
    # This shows an example of asking the api to list all Sites that are active, are a test site, and have the
    # specified site id using filter parameters in the query args. There must be only one item in the result list.
    resp = requests.get(baseurl + 'sites/', dcu(args, {'test_site': True, 'site': site, 'active': True}))
    data = respcheck(resp)
    if len(data) != 1:
        raise Exception("Invalid test site specified")
    args['site'] = site  # We have validated the specified site, so add it to all api call arguments
    log(dbg, f"Using site: {data[0]['description']}", data)

    ###################################################################################################################
    # Now let's find an area/line/machine to use
    area_data = line_data = machine_data = dispatchtype_data = None

    # let's grab the last area in the list - this shows how we can page through the data returned by the api calls,
    # as you can never assume that all the data will fit in one request. Check the API documentation for the default
    # limit.
    limit = 2
    offset = 0
    finished = False

    while not finished:
        resp = requests.get(baseurl + 'areas/', dcu(args, {
            'active': True, 'limit': limit, 'offset': offset
        }))
        data = respcheck(resp)
        if len(data) < limit:  # this means we hit the last page of possible results, so grab the last one in the list
            finished = True
            if data:
                area_data = data[-1]
        else:
            offset += len(data)
            area_data = data[-1]
    if not area_data:
        raise Exception("Couldn't find an active area to use")
    log(dbg, f"Using area: {area_data['code']}", area_data)

    # grab a line in the area we've found that supports production
    resp = requests.get(baseurl + 'lines/', dcu(args, {
        'area_id': area_data['id'], 'active': True, 'enable_production': True
    }))
    data = respcheck(resp)
    if data:
        line_data = data[0]
    if not line_data:
        raise Exception("Couldn't find an active line to use")
    log(dbg, f"Using line: {line_data['code']}", line_data)

    # grab a machine on the line
    resp = requests.get(baseurl + 'machines/', dcu(args, {
        'line_id': line_data['id'], 'active': True
    }))
    data = respcheck(resp)
    if data:
        machine_data = data[0]
    if not machine_data:
        raise Exception("Couldn't find an active machine to use")
    log(dbg, f"Using machine: {machine_data['code']}", machine_data)

    # grab a Dispatch Type we can use
    resp = requests.get(baseurl + 'dispatchtypes/', dcu(args, {
        'active': True
    }))
    data = respcheck(resp)
    if data:
        dispatchtype_data = data[0]
    if not dispatchtype_data:
        raise Exception("Couldn't find an active dispatch type to use")
    log(dbg, f"Using Dispatch Type: {dispatchtype_data['code']}", dispatchtype_data)

    ###################################################################################################################
    # Let's record a user clocking in to Dispatch to work on our line we created previously.
    resp = requests.post(baseurl + f'users/clock_in/{testuser}/', dcu(args, {'linecode': line_data['code']}))
    respjson = respcheck(resp, getdata=False)
    log(dbg, "User clocked in", respjson)

    # Now clock them out
    resp = requests.post(baseurl + f'users/clock_out/{testuser}/', dcu(args, {'linecode': line_data['code']}))
    respjson = respcheck(resp, getdata=False)
    log(dbg, "User clocked out", respjson)

    # We can record a user clockin session in the past by supplying a start and an end parameter. These datetime
    # parameters in the API must be formatted consistently, and must represent the current time in the Site's
    # timezone (NOT UTC) unless otherwise noted in the API documentation.
    start = datetime.now() - timedelta(days=7)
    end = start + timedelta(hours=8)
    resp = requests.post(baseurl + f'users/clock_in/{testuser}/', dcu(args, {
        'linecode': line_data['code'],
        'start': start.strftime(API_MINUTE_FORMAT),
        'end': end.strftime(API_MINUTE_FORMAT),
    }))
    respjson = respcheck(resp, getdata=False)
    log(dbg, "Created backdated clock in", respjson)

    ###################################################################################################################
    # Let's call specific api's for the machine we created. Here we set the machine's cycle count, and then
    # we increment the machine's cycle count.
    resp = requests.post(baseurl + 'machines/set_cycle_count/', dcu(args, {
        'code': machine_data['code'], 'cyclecount': 832
    }))
    respjson = respcheck(resp, getdata=False)
    log(dbg, "Set machine cycle count", respjson)

    # this simulates a high frequency machine where we make so many calls to this we don't care about tracking the
    # lastupdated values for the machine cycle count.
    resp = requests.post(baseurl + 'machines/increment_cycle_count/', dcu(args, {
        'code': machine_data['code'], 'skip_lastupdated': 1, 'cyclecount': 5,
    }))
    respjson = respcheck(resp, getdata=False)
    log(dbg, "Incremented machine cycle count", respjson)

    ###################################################################################################################
    # Let's create a Dispatch for the machine, to simulate an event that requires intervention
    resp = requests.post(baseurl + 'dispatches/open/', dcu(args, {
        'dispatchtype': dispatchtype_data['id'], 'description': 'l2lsdk test dispatch', 'machine': machine_data['id']
    }))
    data = respcheck(resp)
    log(dbg, "Created open Dispatch", data)

    # Now let's close it
    resp = requests.post(baseurl + f'dispatches/close/{data["id"]}/', dcu(args, {}))
    data = respcheck(resp)
    log(dbg, "Closed open Dispatch", data)

    ###################################################################################################################
    # Let's add a Dispatch for the machine that represents an event that already happened and we just want to record
    # it
    reported = datetime.now() - timedelta(days=60)
    completed = reported + timedelta(minutes=34)
    resp = requests.post(baseurl + 'dispatches/add/', dcu(args, {
        'dispatchtypecode': dispatchtype_data['code'],
        'description': 'l2lsdk test dispatch (already closed)',
        'machinecode': machine_data['code'],
        'reported': reported.strftime(API_SECONDS_FORMAT),
        'completed': completed.strftime(API_SECONDS_FORMAT),
    }))
    data = respcheck(resp)
    log(dbg, "Created backdated Dispatch", data)

    ###################################################################################################################
    # Let's record some production data using the record_details api. This will create a 1 second pitch as we use now
    # both start and end. Typically you should use a real time range for the start and end values.
    resp = requests.post(baseurl + 'pitchdetails/record_details/', dcu(args, {
        'linecode': line_data['code'],
        'productcode': 'testproduct-' + str(int(time.time())),  # this creates a new unique product
        'actual': random.randint(10, 100),
        'scrap': random.randint(5, 20),
        'operator_count': random.randint(0, 10),
        'start': 'now',
        'end': 'now',
    }))
    data = respcheck(resp)
    log(dbg, "Recorded Pitch details", data)

    # Let's get the production reporting data for our line
    end = datetime.now() + timedelta(days=1)
    start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    resp = requests.get(baseurl + 'reporting/production/daily_summary_data_by_line/', dcu(args, {
        'start': start.strftime(API_MINUTE_FORMAT),
        'end': end.strftime(API_MINUTE_FORMAT),
        'linecode': line_data['code'],
        'show_products': True
    }))
    data = respcheck(resp)
    log(dbg, "Retrieved Daily summary for line", data)


#######################################################################################################################
# Utility functions
#######################################################################################################################
def log(debug, msg, data):
    print(msg)
    if debug:
        print(json.dumps(data, indent=2))


def dcu(d1, d2):
    """Dict copy & update, returning the new dictionary"""
    rval = d1.copy()
    rval.update(d2)
    return rval


def respcheck(resp, getdata=True):
    # If the HTTP status code is not 200, that means there was some kind of system failure.
    if not resp.ok:
        raise Exception(f"API call system failure, status: {resp.status_code}, error: {resp.content}")

    # After verifying that the HTTP status code is 200, we need to check the json response and look at the success
    # field. The api call only has succeeded if this field is True.
    respjson = resp.json()
    if not respjson['success']:
        raise Exception(f"API call failed, error: {respjson['error']}")

    return respjson['data'] if getdata else respjson


if __name__ == "__main__":
    main()
