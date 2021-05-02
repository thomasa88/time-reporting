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

import datetime
import requests
import pickle
import time
import json
import bs4

import htmlutils

COOKIE_FILE = 'flexhrm_cookies.pickle'

class Session:
    # Index is important. ForetagKonteringsdimensionId does not decide type.
    # Are these IDs universal??
    COMPANY_ACCOUNT_COL_INDEX = 4
    PROJECT_ACCOUNT_COL_INDEX = 5
            
    def __init__(self, baseurl, username, ask_password):
        self.baseurl = baseurl
        self.username = username
        self.ask_password = ask_password
        self.password = None
        self.token = None
        self.company_id = None
        self.session = requests.Session()
        # Need user-agent to not get redirected to InternalServerError page
        self.session.headers = {
            'User-Agent': 'Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:87.0) Gecko/20100101 Firefox/87.0'
        }
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
                cookies, token = pickle.load(cookie_file)
                self.token = token
                self.session.cookies.update(cookies)
        except FileNotFoundError:
            pass

    def save_cookies(self):
        with open(COOKIE_FILE, 'wb') as cookie_file:
            pickle.dump([self.session.cookies, self.token], cookie_file)

    def is_logged_in(self):
        resp = self.session.get(f'{self.baseurl}/HRM/')
        logged_in = 'HRM/Home?f=' in resp.url
        bs = bs4.BeautifulSoup(resp.content, 'html.parser')
        if logged_in:
            self.company_id = resp.url.split('?f=')[1]

            self.employee_id = bs.select_one('input#MyCalendarAnstallningId')['value']
            return True, None
        else:
            flexhrm_customer_id = bs.select_one('input#Kundinstans')['value']
            return False, flexhrm_customer_id


    # ASP.NET cross-post protection. The token is kept in the browser's
    # Local Storage (javascript: window.localStorage), so it does not show
    # up in all headers!
    def get_request_token(self, ref, has_session=True):
        if has_session:
            # We must pass the old token and call this URL when we already
            # have a session
            old_token = self.token
            url = f'{self.baseurl}/HRM/RequestToken/GetReqeustToken'
        else:
            old_token = None
            url = f'{self.baseurl}/HRM/Login/GetReqeustToken'
        resp = self.session.post(url,
                                 headers={ 'Referer': ref,
                                           '__RequestVerificationToken': old_token,
                                           'X-Requested-With': 'XMLHttpRequest'
                                 })

        try:
            json_resp = json.loads(resp.content)
            self.token = json_resp['Token']
        except json.decoder.JSONDecodeError:
            print("REQ HEADERS", resp.request.headers)
            print(resp.content)
            raise

    def log_in(self):
        logged_in, flexhrm_customer_id = self.is_logged_in()
        if logged_in:
            #print("Already logged in")
            return
        if not self.password:
            self.password = self.ask_password()

        self.get_request_token(ref=f'{self.baseurl}/HRM/Login',
                               has_session=False)

        # Log in
        resp = self.session.post(f'{self.baseurl}/HRM/Login/LogOn',
                                 {
                                     'Kundinstans': flexhrm_customer_id,
                                     'Anvandarnamn': self.username,
                                     'Losenord': self.password,
                                     'X-Requested-With': 'XMLHttpRequest'
                                 },
                                 headers = {
                                     '__RequestVerificationToken': self.token,
                                     'X-Requested-With': 'XMLHttpRequest'
                                 }
        )
        assert resp.status_code == 200

        self.token = resp.headers['AntiforgeryToken']

        success = False
        reason = 'Unknown'
        try:
            json_resp = json.loads(resp.content)
            if json_resp['RedirectUrl'] == '%2fHRM%2fdefault.aspx':
                success = True
        except json.decoder.JSONDecodeError:
            # Not JSON
            # Look for error in HTML
            bs = bs4.BeautifulSoup(resp.content, 'html.parser')
            err_div = bs.select_one('div.validation-summary-errors')
            if err_div:
                reason = err_div.text.strip()
        if not success:
            raise Exception(f"Failed to log in to FlexHRM: {reason}")

        # Log-in redirects to default.aspx, from which we can grab
        # the company ID
        resp = self.session.get(f'{self.baseurl}/HRM/default.aspx')
        self.company_id = resp.url.split('?f=')[1]

        resp = self.session.get(f'{self.baseurl}/HRM/Home',
                                params={ 'f': self.company_id }
        )
        home_resp = resp

        bs = bs4.BeautifulSoup(resp.content, 'html.parser')
        self.employee_id = bs.select_one('input#MyCalendarAnstallningId')['value']

        resp = self.session.get(f'{self.baseurl}/HRM/AnvandarloggLogger/AddOrUpdatePost',
                                headers={ 'X-Requested-With': 'XMLHttpRequest' },
                                params={ '{}': '',
                                         '_': str(int(time.time() * 1000))})
        
        resp = self.session.post(f'{self.baseurl}/HRM/PaminnelserWidget/GetPerForetag',
                                 headers={ 'Referer': home_resp.url,
                                     '__RequestVerificationToken': self.token,
                                     'X-Requested-With': 'XMLHttpRequest',
                                     'Accept': 'application/json, text/javascript, */*; q=0.01'
                                 },
                                 data={ 'foretagId': self.company_id })

        # Every loaded HTML page requests the token (via Javascript/jQuery)?
        self.get_request_token(ref=home_resp.url)
        
    def set_day(self, date, flexhrm_entries):
        # TODO: Allow setting of multiple rows
        # Get initial form values
        hyphen_date = date.strftime("%Y-%m-%d")
        url = f'{self.baseurl}/HRM/Tid/Dagredovisning'
        resp = self.session.get(url,
                                params = { 'f': self.company_id,
                                           'anstallningId': self.employee_id,
                                           'datum': hyphen_date })
        dag_resp = resp

        # Must refresh the token every time after loading this (all?) page(s)?
        self.get_request_token(ref=resp.url)

        bs = bs4.BeautifulSoup(resp.content, 'html.parser')
        form = bs.select_one('form#edit')

        fields = self._parse_form_fields(form)

        #self.session.cookies.set('anstallningId', self.employee_id, domain=get from baseurl, path='/HRM/')

        lock_path = form.get('lock-action')
        
        fields['ModelDirty'] = str(int(time.time() * 1000))

        # Can we skip this?
        resp = self.session.post(f'{self.baseurl}{lock_path}',
                                 data=fields,
                                 headers={
                                     '__RequestVerificationToken': self.token,
                                     'X-Requested-With': 'XMLHttpRequest',
                                     'Referer': dag_resp.url
                                 })

        #fields['ModelHasLock'] = '1'
        self.token = resp.headers['AntiforgeryToken']

        # Fill up with the number of rows we need (could probably skip one)
        for _ in flexhrm_entries:
            self._get_new_row(fields, date)

        row_ids = fields['Tidrapportdag.Tidrader.Index']
        if not isinstance(row_ids, list):
            row_ids = [row_ids]

        for row_id, entry in zip(row_ids, flexhrm_entries):
            begin_str = entry.begin_time.strftime('%H:%M')
            fields[f'Tidrapportdag.Tidrader[{row_id}].FromKlockslag.Value'] = begin_str
            fields[f'Tidrapportdag.Tidrader[{row_id}].FromKlockslag.Changed'] = 'true'
            end_str = entry.end_time.strftime('%H:%M')
            fields[f'Tidrapportdag.Tidrader[{row_id}].TomKlockslag.Value'] = end_str
            fields[f'Tidrapportdag.Tidrader[{row_id}].TomKlockslag.Changed'] = 'true'
            fields[f'Tidrapportdag.Tidrader[{row_id}].NewRow'] = 'True'
            fields[f'Tidrapportdag.Tidrader[{row_id}].Tidkod.Value.Id'] = 'f8ce42e2-1c4f-48cc-8f01-a58f00d49dce'
            fields[f'Tidrapportdag.Tidrader[{row_id}].Tidkod.Changed'] = 'True'
            fields[f'Tidrapportdag.Tidrader[{row_id}].Tidkod.Value.Kodtyp'] = '1'

            fields[f'Tidrapportdag.Tidrader[{row_id}].HarManuelltAndradeKonteringar'] = 'True'

            consultancy_company_id, project_id = entry.account['flexhrm']
            
            # "Konteringar" (accounting???)
            account_col_ids = fields[f'Tidrapportdag.Tidrader[{row_id}].Konteringar.Index']

            #if company:
            company_col_id = account_col_ids[self.COMPANY_ACCOUNT_COL_INDEX]

            #fields[f'Tidrapportdag.Tidrader[{row_id}].Konteringar[{company_col_id}].Value.EntityDescription'] = ''
            fields[f'Tidrapportdag.Tidrader[{row_id}].Konteringar[{company_col_id}].Value.Id'] = consultancy_company_id
            fields[f'Tidrapportdag.Tidrader[{row_id}].Konteringar[{company_col_id}].Changed'] = 'True'
            # This GUID is fetched as part of creating the row
            #fields[f'Tidrapportdag.Tidrader[{row_id}].Konteringar[{company_col_id}].Value.ForetagKonteringsdimensionId'] = ''

            project_col_id = account_col_ids[self.PROJECT_ACCOUNT_COL_INDEX]
            #fields[f'Tidrapportdag.Tidrader[{row_id}].Konteringar[{project_col_id}].Value.EntityDescription'] = ''
            fields[f'Tidrapportdag.Tidrader[{row_id}].Konteringar[{project_col_id}].Value.Id'] = project_id
            fields[f'Tidrapportdag.Tidrader[{row_id}].Konteringar[{project_col_id}].Changed'] = 'True'
            # This GUID is fetched as part of creating the row
            #fields[f'Tidrapportdag.Tidrader[{row_id}].Konteringar[{project_col_id}].Value.ForetagKonteringsdimensionId'] = ''

            us_date_midnight = date.strftime("%m%%2F%d%%2F%Y") + "%2000%3A00%3A00"
        url = f'{self.baseurl}/HRM/Tid/Dagredovisning/Save?anstallningId={self.employee_id}&datum={us_date_midnight}&f={self.company_id}'

        fields['ModelDirty'] = str(int(time.time() * 1000))
        fields['_RequestVerificationToken'] = self.token
        resp = self.session.post(url,
                                 data=fields,
                                 headers={ 'Referer': dag_resp.url,
                                 })

        try:
            # We should be sent on to Dagredovisning
            # If we stay on Save, we have done something wrong
            self.token = resp.history[0].headers['AntiforgeryToken']
        except Exception as e:
            print(repr(e))
            for r in resp.history:
                print(r)
                print(r.url)
            print(resp)
            print(resp.url)
            print(resp.headers)
            #print(resp.content)

        # "Save" redirects to "Dagredovisning", so we need to get a new token
        self.get_request_token(ref=resp.url)
        
        assert resp.status_code == 200
        
    def _get_new_row(self, fields, date):
        # We could probably make up the row ID ourselves, but in this
        # way we don't need to know the names of all the 101(!) fields.
        hyphen_date = date.strftime("%Y-%m-%d")
        resp = self.session.post(f'{self.baseurl}/HRM/Tid/Dagredovisning/EmptyBodyRow',
                                 data = {
                                     'AnstallningId': self.employee_id,
                                     'Datum': hyphen_date
                                 },
                                 params = {
                                     'f': self.company_id
                                 },
                                 headers = {
                                     '__RequestVerificationToken': self.token
                                 }
        )

        bs = bs4.BeautifulSoup(resp.content, 'html.parser')
        row_div = bs.select_one('div.row')
        htmlutils.parse_form_fields(row_div, fields)
        
    def find_project(self, name_substring):
        # page='AutoComplete' works here as well
        return self._auto_complete('AutoCompleteProjektByDeltagare', self.PROJECT_ACCOUNT_COL_INDEX,
                                   name_substring)

    def find_company(self, name_substring):
        return self._auto_complete('AutoComplete', self.COMPANY_ACCOUNT_COL_INDEX,
                                   name_substring)

    def _auto_complete(self, page, col_index, name_substring, limit=15):
        # We need the "dimension" GUID
        fields = {}
        self._get_new_row(fields, datetime.date.today())

        row_id = fields['Tidrapportdag.Tidrader.Index']
        account_col_ids = fields[f'Tidrapportdag.Tidrader[{row_id}].Konteringar.Index']
        col_id = account_col_ids[col_index]

        dimension_id = fields[f'Tidrapportdag.Tidrader[{row_id}].Konteringar[{col_id}].Value.ForetagKonteringsdimensionId']

        us_date_midnight = datetime.date.today().strftime("%m%%2F%d%%2F%Y") + "%2000%3A00%3A00"
        resp = self.session.post(f'{self.baseurl}/HRM/Kontering/{dimension_id}/{page}',
                         data={
                             'term': name_substring,
                             'limit': str(limit),
                             'valueType': 'EntityDescription',
                             'validStatuses[]': '0',
                             'dimensionId': dimension_id,
                             'restrictByAnstallning': 'true',
                             'includeContainers': 'false',
                             'showSenasteProjektTid': 'true',
                             'anstallningId': self.employee_id,
                             #'linkedKonteringar[0][ForetagKonteringsdimensionId]': '',
                             #'linkedKonteringar[0][Kod]': ''
                         },
                         headers={
                             '__RequestVerificationToken': self.token,
                             'X-Requested-With': 'XMLHttpRequest',
                             'Referer': f'{self.baseurl}/HRM/Tid/Dagredovisning/Save?anstallningId={self.employee_id}&datum={us_date_midnight}&f={self.company_id}'
                         }
        )
        resp_json = json.loads(resp.content)
        return [(match['label'], match['id']) for match in resp_json]
