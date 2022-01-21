# This file is part of time-reporting.
#
# Copyright (C) 2022  Thomas Axelsson
#
# time-reporting is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# time-reporting is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with time-reporting.  If not, see <https://www.gnu.org/licenses/>.

import bs4
import datetime
import requests
import pickle
import time
import json
import logging
import re

import htmlutils
import timereporting

SESSION_DATA_FILE = 'xledger_data.pickle'

logger = logging.getLogger(__name__)

# Form fields with non-changing values that are always present on the time entry page
ENTRY_BASE_FIELDS =  {
                "__EVENTTARGET": "",
                "__EVENTARGUMENT": "",
                "__LASTFOCUS": "",
                "__VIEWSTATE": "",
                "fb$ctl00$ilsRTimesheetCode_Txt": "",
                "fb$ctl00$ilsRTimesheetCode_Txt_PK": "0",
                "fb$ctl00$ilsRTimesheetCode_Txt_S": "*",
                "fb$ctl00$ttmHTimeFromTo": "",
                "fb$ctl00$ttmHTimeFromTo2": "",

                # No project entered

                # No activity entered

                "fb$ctl00$txfFWorkingHours": "0",

                ######## Does this need to be added for customer projects?
                #	"fb$ctl00$txfFInvoiceHours": "",

                "fb$ctl00$txtSText": "time-reporting",

                # TODO: Support Time type (used for e.g. overtime?)
                # TODO: Fill in these values from the response, select: fb$ctl00$ilsRvTimeType$ilsRvTimeType_ddl
    #            "fb_ctl00_ilsRvTimeType_ilsRvTimeType_fhp_RO_Txt": "0+-+Normal",
    #            "fb_ctl00_ilsRvTimeType_ilsRvTimeType_fhp_Txt_PK": "13079384",
            }

class Session:
    def __init__(self, baseurl, username, ask_password, device_password):
        self.baseurl = baseurl
        self.username = username
        self.ask_password = ask_password
        self.password = None

        self.device_password = device_password
        # Unique ID of the paired device
        self.device_key = None

        self.project_list_cache = None
        self.activity_list_cache = {}
        self.session = requests.Session()

        self.load_session_data()

    def __enter__(self):
        self.log_in()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        # Cannot use  __del__ as Python functions (e.g. open()) are
        # removed at that point...
        self.save_session_data()

    def load_session_data(self):
        try:
            with open(SESSION_DATA_FILE, 'rb') as f:
                data = pickle.load(f)
                self.session.cookies.update(data['cookies'])
                self.device_key = data['device_key']
        except FileNotFoundError:
            pass

    def save_session_data(self):
        with open(SESSION_DATA_FILE, 'wb') as f:
            data = { 'cookies': self.session.cookies,
                     'device_key': self.device_key }
            pickle.dump(data, f)

    def is_logged_in(self):
        resp = self.session.get(f"{self.baseurl}/Restricted/Touch.aspx")
        assert resp.status_code == 200
        return 'Default.aspx' not in resp.url

    def log_in(self):
        if self.is_logged_in():
            logger.debug('Already logged in')
            return

        # Using Device pairing to avoid the e-mail security code
        # on each login
        if not self._log_in_req():
            logger.info('Login failed. Try to pair.')
            self.pair()
            if not self._log_in_req():
                raise Exception("Device log in failed: TODO")

        logger.debug('Login successful')

    def _log_in_req(self):
        resp = self.session.get(f"{self.baseurl}")

        # Load form to get ASP.Net fields
        form_fields = htmlutils.form_fields_from_selector(resp.content, 'form#Default')
        # We don't want all the fields, so build our own set
        fields = {
	        "__EVENTTARGET": "",
            "__EVENTARGUMENT": "",
            "__VIEWSTATE": "",
            "__EVENTVALIDATION": form_fields["__EVENTVALIDATION"],
            "ucLogin$hfDeviceKey": self.device_key,
            "ucLogin$UtcOffset": "-60",
            "ucLogin$txtDevicePassword": self.device_password,
            "ucLogin$btnLoginDevice": ""
        }
        resp = self.session.post(f"{self.baseurl}",
                                 fields,
                                 headers={ 'Referer': resp.url }
        )
        assert resp.status_code == 200

        return resp.url == f'{self.baseurl}/Restricted/Index.aspx'

    def pair(self):
        if not self.password:
            self.password = self.ask_password()

        resp = self.session.get(f"{self.baseurl}")

        # Load form to get ASP.Net fields
        form_fields = htmlutils.form_fields_from_selector(resp.content, 'form#Default')
        # We don't want all the fields, so build our own set
        # TODO: Just strip "btn" parameters?
        fields = {
	    "__EVENTTARGET": "",
            "__EVENTARGUMENT": "",
            "__VIEWSTATE": "",
            "__EVENTVALIDATION": form_fields["__EVENTVALIDATION"],
            "ucLogin$hfDeviceKey": "",
            "ucLogin$UtcOffset": "-60",
            "ucLogin$txtUser": self.username,
            "ucLogin$txtPassword": self.password,
            "ucLogin$btnPairDevice": "",
            "ucLogin$txtDevicePassword": ""
        }
        resp = self.session.post(f"{self.baseurl}/Default.aspx",
                                 fields,
                                 headers={ 'Referer': resp.url }
        )
        assert resp.status_code == 200

        # Seems that sometimes we get English and sometimes the local language,
        # so look for something that does not change. Can we force the language?
        if 'txtEnterSecCode' not in resp.text:
            raise Exception("Failed to log in to Xledger: TODO")

        # Security code entry
        sec_code = input('Security code: ')

        form_fields = htmlutils.form_fields_from_selector(resp.content, 'form#Default')
        fields = {
            "__EVENTTARGET": "",
            "__EVENTARGUMENT": "",
            "__VIEWSTATE": "",
            "__EVENTVALIDATION": form_fields["__EVENTVALIDATION"],
            "ucLogin$hfDeviceKey": "",
            "ucLogin$UtcOffset": "-60",
            "ucLogin$ucSecCode$txtEnterSecCode": sec_code,
            "ucLogin$ucSecCode$btn_next": "Next",
        }
        resp = self.session.post(f"{self.baseurl}",
                                 fields,
                                 headers={ 'Referer': resp.url }
        )
        assert resp.status_code == 200

        if 'ucLogin$ucPairDevice$txtSDeviceName' not in resp.text:
            raise Exception("Security code check failed: TODO")

        # Device password entry
        form_fields = htmlutils.form_fields_from_selector(resp.content, 'form#Default')
        fields = {
            "__EVENTTARGET": "",
            "__EVENTARGUMENT": "",
            "__VIEWSTATE": "",
            "__EVENTVALIDATION": form_fields["__EVENTVALIDATION"],
            "ucLogin$hfDeviceKey": "",
            "ucLogin$UtcOffset": "-60",
            "ucLogin$ucPairDevice$txtSDeviceName": "time-reporting",
            "ucLogin$ucPairDevice$txtSDevicePassword": self.device_password,
            "ucLogin$ucPairDevice$txtSConfirmDevicePassword": self.device_password,
            # TODO: Make this language-agnostic
	        "ucLogin$ucPairDevice$pnlCustomButtons_0$B19052": "Registrera"
        }
        resp = self.session.post(f"{self.baseurl}",
                                 fields,
                                 headers={ 'Referer': resp.url }
        )
        assert resp.status_code == 200

        key_match = re.search(r"PairDevice\('([^']+)'\);", resp.text)
        if key_match:
            self.device_key = key_match.group(1)
        else:
            raise Exception('Failed to get pairing device key')

        logging.info('Paired')

    def set_day(self, date, entries):
        '''
        Set the entries for the given day. Hours are summed up.
        '''

        java_timestamp = int(datetime.datetime.utcnow().timestamp() * 1000)
        hyphen_date = date.strftime("%Y-%m-%d")

        sums = timereporting.sum_entries(entries, 'xledger')

        for account, sum_ in sums.items():
            project, activity = self._account_to_ids(account)
            hours = sum_.total_seconds() / 3600

            project_id = project[0]
            project_url_name = project[1].replace(' ', '+')

            activity_id = activity[0]
            activity_url_name = activity[1].replace(' ', '+')

            # Mobile reporting page
            resp = self.session.get(f'{self.baseurl}/Restricted/TouchFrame.aspx?Mnu=2329&frm=3&src=2&sn=fb_ctl00_pnlButtonsTouch_G&v={java_timestamp}&pk=0&dk={hyphen_date}&pb=true&rf=false')

            form_fields = htmlutils.form_fields_from_selector(resp.content, 'form#frmTouchFrame')

            # Set the project
            common_fields = {
                "fb$ctl00$txdDAssignment": hyphen_date,
                "fb$ctl00$ilsRvProject$ilsRvProject_fhp_Txt": project_url_name,
                "fb$ctl00$ilsRvProject$ilsRvProject_fhp_Txt_S": "*", # Search string used to find project?
                "fb$ctl00$ilsRvProject$ilsRvProject_fhp_Txt_PK": project_id,
                **ENTRY_BASE_FIELDS
                }

            fields_proj = {
                "__PBT75108-2329-3": form_fields["__PBT75108-2329-3"], # Request counter?
                "__EVENTVALIDATION": form_fields["__EVENTVALIDATION"],
                **common_fields
            }

            # We must set the project before we can set an activity
            # (I guess the __PBT counter tracks the session?)
            resp = self.session.post(resp.url,
                                     data=fields_proj)
            
            # TODO: Don't use floats, to avoid potential decimal problems
            hours_str = str(hours).replace('.', ',')

            form_fields = htmlutils.form_fields_from_selector(resp.content, 'form#frmTouchFrame')

            # Set the activity and save
            fields = {
                "__PBT75108-2329-3": form_fields["__PBT75108-2329-3"], # Request counter?
                "__EVENTVALIDATION": form_fields["__EVENTVALIDATION"],
                **common_fields,
                "fb$ctl00$ilsRvActivity$ilsRvActivity_fhp_Txt": activity_url_name,
                "fb$ctl00$ilsRvActivity$ilsRvActivity_fhp_Txt_S": "*",
                "fb$ctl00$ilsRvActivity$ilsRvActivity_fhp_Txt_PK": activity_id,

                "fb$ctl00$txfFWorkingHours": hours_str,

                "fb$ctl00$pnlButtons$T": "" # Save button
            }

            resp = self.session.post(resp.url,
                                     data=fields)

            assert resp.status_code == 200

            if 'ReturnButtonZoom' not in resp.text:
                raise Exception(f'Failed to save {project} {activity} for {date}')

    def _account_to_ids(self, account):
        project, activity = account

        if not self.project_list_cache:
            self.project_list_cache = {p['name']: p['id']
                                       for p in self.get_projects()}

        try:
            project_id = self.project_list_cache[project]
            project_name = project
        except KeyError:
            raise Exception(f'Could not find project: {project}')

        if project_id not in self.activity_list_cache:
            self.activity_list_cache[project_id] = {a['name']: a['id']
                                                    for a in
                                                    self.get_activities(project_id,
                                                                        project_name)}

        activities = self.activity_list_cache[project_id]
        try:
            activity_id = activities[activity]
            activity_name = activity
        except KeyError:
            raise Exception(f'Could not find activity "{activity}" for project "{project}"')

        logger.debug('%s, %s -> %s, %s', project, activity, project_id, activity_id)

        return ((project_id, project_name), (activity_id, activity_name))


    def get_projects(self):
        '''
        Returns a list of projects

        {'id': '1393939',
         'name': '1234 - Project A'}
        '''

        java_timestamp = int(datetime.datetime.utcnow().timestamp() * 1000)
        today = datetime.date.today()
        hyphen_date = today.strftime("%Y-%m-%d")

        # Get request parameters from the Mobile reporting page
        resp = self.session.get(f'{self.baseurl}/Restricted/TouchFrame.aspx?Mnu=2329&frm=3&src=2&sn=fb_ctl00_pnlButtonsTouch_G&v={java_timestamp}&pk=0&dk={hyphen_date}&pb=true&rf=false')

        help_match = re.search("OpenFieldHelp\(3, 'fb_ctl00_ilsRvProject_ilsRvProject_fhp_Txt'[^)]+", resp.text)

        if not help_match:
            raise Exception('Failed to get project help parameters')

        help_params = help_match.group().split(', ')

        resp = self.session.get(f'{self.baseurl}/Restricted/Frame.aspx',
                                params={
                                    "Mnu": "937",
                                    "frm": "4",
                                    "src": "3",
                                    "sn": "fb_ctl00_ilsRvProject_ilsRvProject_fhp_Txt",
                                    "v": java_timestamp,
                                    "rf": "false",
                                    "li": help_params[11].replace("'", ""),
                                    "dt": help_params[3],
                                    "lc": help_params[14],
                                    "bl": "true",
                                    "lk": help_params[13],
                                    "e": help_params[8],
                                    "sb": "*",
                                    "c": help_params[7],
                                    "fk2": help_params[5],
                                    "oo": "0",
                                    "fk": help_params[4],
                                    "lv": "0",
                                    "pb": "true",
                                    "fk3": "0",
                                    "bo": help_params[2]
                                })

        assert resp.status_code == 200

        proj_helps = re.findall('onclick="[^"]+ReturnFieldHelp\((.*?)\)', resp.text)
        projects = []
        for proj_help in proj_helps:
            s = proj_help.split(', ')
            proj_id = s[3]
            proj_name = s[4].replace('&#39;', '') # HTML-encoded single quotes around the string
            projects.append({'id': proj_id, 'name': proj_name})

        return projects

    def get_activities(self, project_id, project_name):
        '''
        Returns a list of activities

        {'id': '1393939',
         'name': 'Activity A'}
        '''

        url_name = project_name.replace(' ', '+')

        java_timestamp = int(datetime.datetime.utcnow().timestamp() * 1000)
        today = datetime.date.today()
        hyphen_date = today.strftime("%Y-%m-%d")

        # Mobile reporting page
        resp = self.session.get(f'{self.baseurl}/Restricted/TouchFrame.aspx?Mnu=2329&frm=3&src=2&sn=fb_ctl00_pnlButtonsTouch_G&v={java_timestamp}&pk=0&dk={hyphen_date}&pb=true&rf=false')

        # Select the project, to be able to get the list of activities using the correct parameters
        form_fields = htmlutils.form_fields_from_selector(resp.content, 'form#frmTouchFrame')

        fields_proj = {
            "__PBT75108-2329-3": form_fields["__PBT75108-2329-3"], # Request counter?
            "__EVENTVALIDATION": form_fields["__EVENTVALIDATION"],

            "fb$ctl00$txdDAssignment": hyphen_date,
            "fb$ctl00$ilsRvProject$ilsRvProject_fhp_Txt": url_name,
            "fb$ctl00$ilsRvProject$ilsRvProject_fhp_Txt_S": "*", # Search string used to find project?
            "fb$ctl00$ilsRvProject$ilsRvProject_fhp_Txt_PK": project_id,
            
            **ENTRY_BASE_FIELDS
        }

        resp = self.session.post(resp.url,
                                 data=fields_proj)

        help_match = re.search("OpenFieldHelp\(3, 'fb_ctl00_ilsRvActivity_ilsRvActivity_fhp_Txt'[^)]+", resp.text)

        if not help_match:
            raise Exception('Failed to get activity help parameters')

        help_params = help_match.group().split(', ')

        resp = self.session.get(f'{self.baseurl}/Restricted/Frame.aspx',
                                params={
			"Mnu": "937",
			"frm": "4",
			"src": "3",
			"sn": "fb_ctl00_ilsRvActivity_ilsRvActivity_fhp_Txt",
			"v": java_timestamp,
			"rf": "false",
			"li": help_params[11],
			"dt": help_params[3],
			"lc": help_params[14],
			"bl": "true",
			"lk": help_params[13],
			"e": help_params[8],
			"sb": "*",
			"c": help_params[7],
			"fk2": "0",
			"oo": "0",
			"fk": project_id,
			"lv": "0",
			"pb": "true",
			"fk3": "0",
			"bo": help_params[2]
		})

        assert resp.status_code == 200

        act_helps = re.findall('onclick="[^"]+ReturnFieldHelp\((.*?)\)', resp.text)
        activities = []
        for act_help in act_helps:
            s = act_help.split(', ')
            act_id = s[3]
            act_name = s[4].replace('&#39;', '') # HTML-encoded single quotes around the string
            activities.append({'id': act_id, 'name': act_name})

        return activities
