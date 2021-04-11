#!/usr/bin/env python3

import datetime
import requests
import pickle
import time
import json

COOKIE_FILE = 'millnet_cookies.pickle'

class Session:
    def __init__(self, baseurl, username, ask_password):
        self.baseurl = baseurl
        self.username = username
        self.ask_password = ask_password
        self.password = None
        self.session = requests.Session()
        self.load_cookies()

    def __enter__(self):
        self.log_in()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        # Cannot use  __del__ as Python functions (e.g. open()) are
        # removed at that point...
        self.save_cookies()

    def load_cookies(self):
        try:
            with open(COOKIE_FILE, 'rb') as cookie_file:
                self.session.cookies.update(pickle.load(cookie_file))
        except FileNotFoundError:
            pass

    def save_cookies(self):
        with open(COOKIE_FILE, 'wb') as cookie_file:
            pickle.dump(self.session.cookies, cookie_file)

    def is_logged_in(self):
        resp = self.session.get(f"{self.baseurl}/cgi/milltime.cgi")
        assert resp.status_code == 200
        return 'login' not in resp.url

    def log_in(self):
        if self.is_logged_in():
            #print("Already logged in")
            return
        if not self.password:
            self.password = self.ask_password()
        resp = self.session.post(f"{self.baseurl}/cgi/mt.cgi/api/login",
                                 {"submit": "Logga in",
                                  "form_loaded": "1",
                                  "userlogin": self.username,
                                  "password": self.password,
                                  "type": "json"}
        )
        assert resp.status_code == 200
        json_resp = json.loads(resp.content)
        if not json_resp['success']:
            raise Exception("Failed to log in to Millnet: " + json_resp['errors'])

    def set_hours(self, project_id, activity_id, date, hours, row_id):
        '''
        Set the hours for the given project, activity and row.

        If row_id is None, a new row will be created!
        '''
        number_date = date.strftime("%Y%m%d")
        hyphen_date = date.strftime("%Y-%m-%d")
        # It is possible to update multiple lines by incrementing the _0
        # suffix for each change
        data = {
                                "dirty_0": "1",
                                "rt_0": str(hours),
    #	                    "rt_0_org": "4.00",
    #	                    "note_0": "",
    #	                    "note_0_org": "",
                                "pid_0": project_id,
                                "aid_0": activity_id,
    #	                    "aname_0": "Kompetensutveckling",
                                "atype_0": "(null)",
                                "absencetype_0": "(null)",
                                "requirenote_0": "0",
    #	                    "pha_0": "Default",
    #	                    "phasename_0": "",
    ##	                    "ro_0": "2.000000", # required. What does it mean?
                                "regday_0": number_date, # today?
                                "regday_0_org": number_date, # required
    ##	                    "lck_0": "false", # lock?
    ###	                    "lck_0_org": "false",
                                # "edOverTime1_20210401": "",
                                # "edOverTime1_20210401_org": "",
                                # "edOverTime2_20210401": "",
                                # "edOverTime2_20210401": "",
                                # "edOverTime2_20210401_org": "",
                                # "moveto_ro": "",
                                # "moveto_pid": "",
                                # "moveto_ppa": "",
                                # "moveto_aid": "",
                                # "moveto_pha": "",
                                # "moveto_new_date": "",
                                # "moveto_date_org": "",
                                "periodtype": "D",
                                "date": hyphen_date,
                                "date_org": hyphen_date, # drop this?
                                "date_begin": number_date,
                                "date_end": number_date,
                                "part": "save-time",
                                "period_value": "",
                                "period": number_date,
                                "param1": "save",
                                "param2": "",
                                "param3": "",
                                "param4": "",
                                "param5": "",
                                "param6": "",
                                "param7": "",
                                "project_id": "",
                                "submenu": "",
                                "submenu_prev": "",
                                "orderby_name": "",
                                "orderby_order": "0",
                                "context": "",
                                "module": ""
                            }
        #if new_row or:
        data.update({
            "pha_0": "Default",
            "rt_0_org": ""
        })
        if row_id:
            data.update({
                ## Without these, a new line of the same type is added
                # Seems to be ID of the row in the current sheet. Increments by 2.0 for each created row.
                "ro_0": row_id, # "2.000000", # required.

                "lck_0": "false", # lock?
    #            "lck_0_org": "false",
            })
        resp = self.session.post(f"{self.baseurl}/cgi/milltime.cgi/main", data)
        assert resp.status_code == 200

    def get_projects(self, limit=50):
        '''
        Returns a list of projects

        {'id': '300000000000000001',
         'value': 'Project name',
         'leader': 'Project leader',
         'groupname': 'Group', # Always 'Medlem' if user is a member?
         'group': '1',
         'customer': 'Customer',
         'projectnr': 'P000-000',
         'disabled': '0'}
        '''
        timestamp = str(time.time() * 1000) # Browser cache protection?
        params = {
            'param1': 'mt-get-projects',
            '_dc': timestamp,
            'param2': 'TIME',
            'show_all': '1',
            'page': '1',
            'start': '0',
            'limit': str(limit)
        }
        resp = self.session.get(f'{self.baseurl}/cgi/milltime.cgi/mt_data', params=params)
        assert resp.status_code == 200

        # Response is rows: [{ 0: {}, 1: {} }]
        return json.loads(resp.content)["rows"]

    def get_activities(self, project_id):
        '''
        Returns a list of activities

        {
            "PhaseName": "",
            "Name": "Name",
            "ActivityName": "Name",
            "ActivityId": "300000000000000001",
            "PhaseId": "Default",
            "ProjPlanActivityId": "",
            "VariationId": "", # Can be "DRIVELOG"
            "AbsenceType": "",
            "RequireNote": "0",
            "CompleteName": "Name",
            "Favorite": "1"
        }

        '''
        #today = datetime.date.today().strftime("%Y%m%d")
        # Does the date range limit activities to only those that
        # are "active" for that period?
        data = {
            "param1": "mt-get-activities",
            "param2": "",
            "project_id": project_id,
            #"date_begin": today,
            #"date_end": today
        }
        resp = self.session.post(f'{self.baseurl}/cgi/milltime.cgi/mt_data', data=data)
        assert resp.status_code == 200
        return json.loads(resp.content)["rows"]
