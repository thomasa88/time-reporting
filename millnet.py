# This file is part of time-reporting.
#
# Copyright (C) 2021  Thomas Axelsson
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

import config
import htmlutils
import timereporting

COOKIE_FILE = 'millnet_cookies.pickle'

logger = logging.getLogger(__name__)

class Session:
    def __init__(self):
        self.baseurl = config.millnet_baseurl
        self.username = config.millnet_username
        self.ask_password = config.millnet_ask_password
        self.password = None
        self.project_list_cache = None
        self.activity_list_cache = {}
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

    def set_day(self, date, entries):
        '''
        Set the entries for the given day. Hours are summed up.
        '''

        number_date = date.strftime("%Y%m%d")
        hyphen_date = date.strftime("%Y-%m-%d")

        sums = timereporting.sum_entries(entries, 'millnet')

        resp = self.session.post(f"{self.baseurl}/cgi/milltime.cgi/main",
                                 data={
                                     'period': number_date,
                                     'periodtype': 'D' # day
                                     # date_* values says what date was last visited
                                 })

        bs = bs4.BeautifulSoup(resp.content, 'html.parser')
        form = bs.select_one('form#mt_main_form')
        fields = htmlutils.parse_form_fields(form)

        # ro_<number> contains a row ID for existing rows that have values
        # It seems that Millnet starts the IDs at 2, so we mark 0 as taken
        max_taken_id = 0
        row_ids = {}
        for name, value in fields.items():
            if name.startswith('ro_'):
                unique_id = round(float(value))
                index = int(name.split('_')[1])
                project_id = fields[f'pid_{index}']
                activity_id = fields[f'aid_{index}']
                account_ids = (project_id, activity_id)
                # If the user has already created multiple rows for the
                # same account, we just overwrite the value of the first
                # one. That is, we don't really handle multiple rows for
                # the same account.
                if not account_ids in row_ids:
                    row_ids[account_ids] = unique_id
                if unique_id > max_taken_id:
                    max_taken_id = unique_id
        next_free_id = max_taken_id + 2

        # TODO: Remove any already existing rows?

        # We pick up more form fields than we want to send,
        # so set up a new dictionary for the post data
        data = {}
        # Index is just counted up from 0 (the Javascript discards the indices
        # of the input boxes)
        for index, (account, sum_) in enumerate(sums.items()):
            account_ids = self._account_to_ids(account)
            project_id, activity_id = account_ids
            hours = sum_.total_seconds() / 3600
            row_id = row_ids.get(account_ids, None)
            row_fields = {
                f'dirty_{index}': '1',
                f'rt_{index}': str(hours),
                f'pid_{index}': project_id,
                f'aid_{index}': activity_id,
                f'regday_{index}': number_date, # today?
                f'regday_{index}_org': number_date, # required
                # lck not required for new rows
                f'lck_{index}': 'false',
                f'pha_{index}': 'Default',
                f'rt_{index}_org': '',

                #f'atype_{index}': '(null)',
                # Absencetype seems to get populated correctly, even though
                # we don't send it.
                #f'absencetype_{index}': '(null)',
                #f'requirenote_{index}': '0',
            }
            if row_id:
                # Do not set ro_* for new rows. keep value for existing rows
                row_fields[f'ro_{index}'] = f'{row_id}.000000'
            data.update(row_fields)

        data.update({
            # 'edOverTime1_20210401': '',
            # 'edOverTime1_20210401_org': '',
            # 'edOverTime2_20210401': '',
            # 'edOverTime2_20210401': '',
            # 'edOverTime2_20210401_org': '',
            # 'moveto_ro': '',
            # 'moveto_pid': '',
            # 'moveto_ppa': '',
            # 'moveto_aid': '',
            # 'moveto_pha': '',
            # 'moveto_new_date': '',
            # 'moveto_date_org': '',
            'periodtype': 'D',
            'date': hyphen_date,
            'date_org': hyphen_date, # drop this?
            'date_begin': number_date,
            'date_end': number_date,
            'part': 'save-time',
            'period_value': '',
            'period': '',#number_date,
            'param1': 'save',
            'param2': '',
            'param3': '',
            'param4': '',
            'param5': '',
            'param6': '',
            'param7': '',
            'project_id': '',
            'submenu': '',
            'submenu_prev': '',
            'orderby_name': '',
            'orderby_order': '0',
            'context': '',
        })

        resp = self.session.post(f"{self.baseurl}/cgi/milltime.cgi/main", data)
        
        assert resp.status_code == 200

    def _account_to_ids(self, account):
        project, activity = account

        if not self.project_list_cache:
            self.project_list_cache = {p['value']: p['id']
                                       for p in self.get_projects()}

        try:
            project_id = self.project_list_cache[project]
        except KeyError:
            raise Exception(f'Could not find project: {project}')

        if project_id not in self.activity_list_cache:
            self.activity_list_cache[project_id] = {a['Name']: a['ActivityId']
                                                    for a in
                                                    self.get_activities(project_id)}

        activities = self.activity_list_cache[project_id]
        try:
            activity_id = activities[activity]
        except KeyError:
            raise Exception(f'Could not find activity "{activity}" for project "{project}"')

        logger.debug('%s, %s -> %s, %s', project, activity, project_id, activity_id)

        return project_id, activity_id
        
        
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
        timestamp = str(int(time.time() * 1000)) # Browser cache protection?
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
