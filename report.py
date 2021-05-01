#!/usr/bin/env python3

# This file is part of time-reporting.
#
# Copyright (C) 2021  Thomas Axelsson
#
# VerticalTimeline is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# VerticalTimeline is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with time-reporting.  If not, see <https://www.gnu.org/licenses/>.

import argparse
import calendar
from collections import defaultdict
import datetime
import gzip
import sys

import config
import googledrive
import timerec
import millnet
import flexhrm

def parse_args():
    arg_parser = argparse.ArgumentParser()
    arg_subparsers = arg_parser.add_subparsers(dest='command', required=True)

    parser_dump = arg_subparsers.add_parser('dump-tasks')
    parser_dump.set_defaults(func=run_dump)

    parser_report = arg_subparsers.add_parser('report')
    parser_report.add_argument('-D', '--no-dl', action='store_true',
                               help="Don't download the Time Recording database (use cached)")
    parser_report.add_argument('-n', '--dry-run', action='store_true',
                               help="Don't upload hours to Millnet")
    parser_report.add_argument('range',
                               help='Date range. YYMMDD-YYMMDD for range, YYMM for a full month, YYMMDD for one day')
    parser_report.set_defaults(func=run_report)

    parser_flexhrm = arg_subparsers.add_parser('flexhrm')
    flexhrm_subparsers = parser_flexhrm.add_subparsers(dest='subcommand',
                                                       required=True)
    parser_flexhrm_find_project = flexhrm_subparsers.add_parser('find-project')
    parser_flexhrm_find_project.set_defaults(func=run_flexhrm_find_project)
    parser_flexhrm_find_project.add_argument('name')

    parser_flexhrm_find_company = flexhrm_subparsers.add_parser('find-company')
    parser_flexhrm_find_company.set_defaults(func=run_flexhrm_find_company)
    parser_flexhrm_find_company.add_argument('name')

    parser_flexhrm_report = flexhrm_subparsers.add_parser('report')
    parser_flexhrm_report.set_defaults(func=run_flexhrm_report)
    parser_flexhrm_report.add_argument('-D', '--no-dl', action='store_true',
                                       help="Don't download the Time Recording database (use cached)")
    parser_flexhrm_report.add_argument('-n', '--dry-run', action='store_true',
                                       help="Don't upload hours to Millnet")
    parser_flexhrm_report.add_argument('range',
                                       help='Date range. YYMMDD-YYMMDD for range, YYMM for a full month, YYMMDD for one day')

    args = arg_parser.parse_args()
    args.func(args, arg_parser)

def download_timerec_db():
    temp_db_filename = 'timerec_temp.gz'
    googledrive.download_file(config.google_fileid, temp_db_filename)
    with gzip.open(temp_db_filename) as gzfile:
        with open(config.timerec_db_filename, 'wb') as unpacked_file:
            unpacked_file.write(gzfile.read())

def convert_day_from_timerec_to_millnet(sessions, millnet_activity_table):
    sums = defaultdict(datetime.timedelta)
    for session in sessions:
        timerec_task = (session.customer, session.project)
        try:
            project, activity = config.activity_mapping[timerec_task]
        except KeyError:
            raise Exception(f"No mapping for {repr(timerec_task)}")
        for row in millnet_activity_table:
            if row[1] == project and row[3] == activity:
                project_id = row[0]
                activity_id = row[2]
                break
        else:
            raise Exception("OUCH, No mapping for ", project, activity)
        #project_id, activity_id, hours
        sums[(project_id, activity_id)] += session.end - session.begin
    return sums

# Get a table of
# project_id, project name, activity_id, activity name
def fetch_millnet_user_activities(millnet_session):
    user_activities = []
    millnet_projects = millnet_session.get_projects()
    for p in millnet_projects:
        if p['groupname'] == 'Medlem':
            activities = millnet_session.get_activities(p['id'])
            for a in activities:
                user_activities.append((p['id'], p['value'],
                                        a['ActivityId'], a['Name']))
    return user_activities

def days_in_month(date):
    return calendar.monthrange(date.year, date.month)[1]

def parse_report_range(range_str):
    begin_str, sep, end_str = range_str.partition('-')

    # end_date is inclusive
    end_date = None
    
    if sep:
        begin_date = datetime.datetime.strptime(begin_str, '%y%m%d').date()
        end_date = datetime.datetime.strptime(end_str, '%y%m%d').date()
    else:
        if len(begin_str) == 6:
            begin_date = datetime.datetime.strptime(begin_str, '%y%m%d').date()
            end_date = begin_date
        elif len(begin_str) == 4:
            begin_date = datetime.datetime.strptime(begin_str, '%y%m').date()
            end_date = datetime.date(begin_date.year, begin_date.month,
                                     days_in_month(begin_date))
        else:
            raise Exception(f'Bad date range: {range_str}')
    if not end_date:
        end_date = begin_date
    return begin_date, end_date

def run_report(args, arg_parser):
    begin_date, end_date = parse_report_range(args.range)

    print(f"Date range: {begin_date} - {end_date}")

    if not args.no_dl:
        print("Downloading latest Time Recording database...")
        download_timerec_db()

    with millnet.Session(config.baseurl, config.username, config.ask_password) as m:
        millnet_activity_table = fetch_millnet_user_activities(m)

        millnet_days = []
        one_day = datetime.timedelta(days=1)
        current_date = begin_date
        # Collect all data before reporting, to be sure that the mapping succeeds
        print("Collecting...")
        while current_date <= end_date:
            tr = timerec.TimeRecording(config.timerec_db_filename)
            day_report = tr.get_day(current_date)
            millnet_day = convert_day_from_timerec_to_millnet(day_report, millnet_activity_table)
            millnet_days.append((current_date, millnet_day))
            # for ((project_id, activity_id), hours) in millnet_day.items():
            #    print(project_id, activity_id, hours)
            current_date += one_day

        print("Reporting...")
        if args.dry_run:
            print("DRY RUN")
        for date, millnet_day in millnet_days:
            day_hours = datetime.timedelta()
            print(date, end=': ')
            for ((project_id, activity_id), hours) in millnet_day.items():
                if not args.dry_run:
                    m.set_hours(project_id, activity_id, date,
                                hours, row_id=None)
                day_hours += hours
            if day_hours:
                print(day_hours)
            else:
                print("-")
        print("Done")

def run_dump(args, arg_parser):
    with millnet.Session(config.baseurl, config.username, config.ask_password) as m:
        for row in fetch_millnet_user_activities(m):
            print((row[1], row[3]))

def run_flexhrm_find_project(args, arg_parser):
    with flexhrm.Session(config.flexhrm_baseurl, config.flexhrm_username,
                         config.flexhrm_ask_password) as flex:
        for label, guid in flex.find_project(args.name):
            print(guid, label)

def run_flexhrm_find_company(args, arg_parser):
    with flexhrm.Session(config.flexhrm_baseurl, config.flexhrm_username,
                         config.flexhrm_ask_password) as flex:
        for label, guid in flex.find_company(args.name):
            print(guid, label)

def run_flexhrm_report(args, arg_parser):
    begin_date, end_date = parse_report_range(args.range)

    print(f"Date range: {begin_date} - {end_date}")

    if not args.no_dl:
        print("Downloading latest Time Recording database...")
        download_timerec_db()

    with flexhrm.Session(config.flexhrm_baseurl, config.flexhrm_username,
                         config.flexhrm_ask_password) as flex:
        days = []
        one_day = datetime.timedelta(days=1)
        current_date = begin_date
        # Collect all data before reporting, to be sure that the mapping succeeds
        print("Collecting...")
        while current_date <= end_date:
            tr = timerec.TimeRecording(config.timerec_db_filename)
            day_entries = tr.get_day(current_date)
            for entry in day_entries:
                map_entry(entry, 'timerec', 'flexhrm')
            days.append((current_date, day_entries))
            current_date += one_day
            print([str(d) for d in day_entries])

        print("Reporting...")
        if args.dry_run:
            print("DRY RUN")
        for date, entries in days:
            print(date)
            if not args.dry_run:
                flex.set_day(date, entries)
        print("Done")

def map_entry(entry, from_system, to_system):
    index = config.account_mapping[from_system].index(entry.account[from_system])
    entry.account[to_system] = config.account_mapping[to_system][index]

def check_mappings():
    # TODO: Check that all mapping lists have equal length
    # Only when using them?
    pass

check_mappings()
parse_args()