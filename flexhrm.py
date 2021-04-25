#!/usr/bin/env python3

import datetime
import requests
import pickle
import time
import json
import bs4

COOKIE_FILE = 'flexhrm_cookies.pickle'

class Session:
    def __init__(self, baseurl, flexhrm_customer_id, username, ask_password):
        self.baseurl = baseurl
        self.flexhrm_customer_id = str(flexhrm_customer_id)
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
        if logged_in:
            self.company_id = resp.url.split('?f=')[1]

            bs = bs4.BeautifulSoup(resp.content, 'html.parser')
            self.employee_id = bs.select_one('input#MyCalendarAnstallningId')['value']
        return logged_in


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
        if self.is_logged_in():
            #print("Already logged in")
            return
        if not self.password:
            self.password = self.ask_password()

        self.get_request_token(ref=f'{self.baseurl}/HRM/Login',
                               has_session=False)

        # Log in
        resp = self.session.post(f'{self.baseurl}/HRM/Login/LogOn',
                                 {
                                     'Kundinstans': self.flexhrm_customer_id,
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
        
    def set_hours(self, project_id, activity_id, date, hours, row_id):
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
        form_fields = form.select('[name]')
        # <select> and <textarea> does not have a "value" attribute
        fields = {}
        for form_field in form_fields:
            if form_field.name == 'input':
                if form_field['type'] == 'image':
                    # Drop image button
                    continue
                value = form_field.get('value', '')
            elif form_field.name == 'textarea':
                # The only textarea is the "comments" field (2021-04-24)
                value = ''
            elif form_field.name == 'select':
                # TODO: Check for "option" tag "DEFAULT" marker, if needed
                option = form_field.select_one('option')
                value = option.get('value', '')
            name = form_field['name']
            if name in fields:
                prev_value = fields[name]
                if isinstance(prev_value, list):
                    prev_value.append(value)
                else:
                    fields[name] = [prev_value, value]
            else:
                fields[name] = value

        row_indices = fields['Tidrapportdag.Tidrader.Index']
        row_index = row_indices[0]

        #self.session.cookies.set('anstallningId', self.employee_id, domain=get from baseurl, path='/HRM/')

        lock_path = form.get('lock-action')
        
        fields['ModelDirty'] = str(int(time.time() * 1000))
        
        resp = self.session.post(f'{self.baseurl}{lock_path}',
                                 data=fields,
                                 headers={
                                     '__RequestVerificationToken': self.token,
                                     'X-Requested-With': 'XMLHttpRequest',
                                     'Referer': dag_resp.url
                                 })

        #fields['ModelHasLock'] = '1'
        self.token = resp.headers['AntiforgeryToken']


        ###fields[f'Tidrapportdag.Tidrader[{row_index}].Tidkod.Change'] = 'True'
        #fields[f'Tidrapportdag.Tidrader[{row_index}].FromKlockslag.Value'] = '02:07'
        #fields[f'Tidrapportdag.Tidrader[{row_index}].FromKlockslag.Changed'] = 'true'
        #fields[f'Tidrapportdag.Tidrader[{row_index}].TomKlockslag.Value'] = '06:00'
        #fields[f'Tidrapportdag.Tidrader[{row_index}].TomKlockslag.Changed'] = 'true'

        
        us_date_midnight = date.strftime("%m%%2F%d%%2F%Y") + "%2000%3A00%3A00"
        url = f'{self.baseurl}/HRM/Tid/Dagredovisning/Save?anstallningId={self.employee_id}&datum={us_date_midnight}&f={self.company_id}'

        fields['ModelDirty'] = str(int(time.time() * 1000))
        fields['_RequestVerificationToken'] = self.token
        resp = self.session.post(url,
                                 data=fields,
                                 headers={ 'Referer': dag_resp.url,
                                 })

        self.token = resp.history[0].headers['AntiforgeryToken']

        # "Save" redirects to "Dagredovisning", so we need to get a new token
        self.get_request_token(ref=resp.url)
        
        assert resp.status_code == 200

    def get_projects(self):
        '''
        Returns a list of projects
        '''
        pass

    def get_activities(self):
        '''
        Returns a list of activities
        '''
        pass
