#!/usr/bin/env python3

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

import argparse
import calendar
from collections import defaultdict
import datetime
import gzip
import sys
import logging

import timereporting
import config
import googledrive
import timerec
import millnet
import flexhrm
import xledger

#logging.basicConfig(level=logging.INFO)
logger = logging.getLogger('report')
#stdout_handler = logging.StreamHandler(sys.stdout)
#logger.addHandler(stdout_handler)
#logger.setLevel(logging.INFO)

def parse_args():
    arg_parser = argparse.ArgumentParser()
    arg_subparsers = arg_parser.add_subparsers(dest='module', required=True)

    arg_parser.add_argument('-v', '--verbose', action='store_true',
                            help='Verbose output')

    parser_millnet = arg_subparsers.add_parser('millnet')
    millnet_subparsers = parser_millnet.add_subparsers(dest='command',
                                                       required=True)
    
    parser_millnet_report = millnet_subparsers.add_parser('report')
    parser_millnet_report.add_argument('-n', '--dry-run', action='store_true',
                               help="Don't upload hours to Millnet")
    parser_millnet_report.add_argument('range',
                               help='Date range. YYMMDD-YYMMDD for range, YYMM for a full month, YYMMDD for one day')
    parser_millnet_report.set_defaults(func=run_millnet_report)

    parser_millnet_dump = millnet_subparsers.add_parser('dump-tasks')
    parser_millnet_dump.set_defaults(func=run_millnet_dump)

    parser_timerec = arg_subparsers.add_parser('timerec')
    timerec_subparsers = parser_timerec.add_subparsers(dest='command',
                                                       required=True)
    parser_timerec_fetch = timerec_subparsers.add_parser('fetch')
    parser_timerec_fetch.set_defaults(func=run_timerec_fetch)

    parser_flexhrm = arg_subparsers.add_parser('flexhrm')
    flexhrm_subparsers = parser_flexhrm.add_subparsers(dest='command',
                                                       required=True)
    parser_flexhrm_find_project = flexhrm_subparsers.add_parser('find-project')
    parser_flexhrm_find_project.set_defaults(func=run_flexhrm_find_project)
    parser_flexhrm_find_project.add_argument('name')

    parser_flexhrm_find_company = flexhrm_subparsers.add_parser('find-company')
    parser_flexhrm_find_company.set_defaults(func=run_flexhrm_find_company)
    parser_flexhrm_find_company.add_argument('name')

    parser_flexhrm_report = flexhrm_subparsers.add_parser('report')
    parser_flexhrm_report.set_defaults(func=run_flexhrm_report)
    parser_flexhrm_report.add_argument('-n', '--dry-run', action='store_true',
                                       help="Don't upload hours to FlexHRM")
    parser_flexhrm_report.add_argument('range',
                                       help='Date range. YYMMDD-YYMMDD for range, YYMM for a full month, YYMMDD for one day')

    parser_xledger = arg_subparsers.add_parser('xledger')
    xledger_subparsers = parser_xledger.add_subparsers(dest='command',
                                                       required=True)
    
    parser_xledger_report = xledger_subparsers.add_parser('report')
    parser_xledger_report.add_argument('-n', '--dry-run', action='store_true',
                               help="Don't upload hours to Xledger")
    parser_xledger_report.add_argument('range',
                               help='Date range. YYMMDD-YYMMDD for range, YYMM for a full month, YYMMDD for one day')
    parser_xledger_report.set_defaults(func=run_xledger_report)

    args = arg_parser.parse_args()

    if args.verbose:
        logging.basicConfig(level=logging.DEBUG)
    else:
        logging.basicConfig(level=logging.INFO)
    
    args.func(args, arg_parser)

def run_timerec_fetch(args, arg_parser):
    logger.info("Downloading Time Recording database...")
    download_timerec_db()
    logger.info("Done")

def download_timerec_db():
    temp_db_filename = 'timerec_temp.gz'
    googledrive.download_file(config.google_fileid, temp_db_filename)
    with gzip.open(temp_db_filename) as gzfile:
        with open(config.timerec_db_filename, 'wb') as unpacked_file:
            unpacked_file.write(gzfile.read())

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

def run_millnet_report(args, arg_parser):
    begin_date, end_date = parse_report_range(args.range)

    logger.info(f"Date range: {begin_date} - {end_date}")

    with millnet.Session(config.millnet_baseurl, config.millnet_username,
                         config.millnet_ask_password) as m:
        days = []
        one_day = datetime.timedelta(days=1)
        current_date = begin_date
        # Collect all data before reporting, to be sure that the mapping succeeds
        logger.info("Collecting...")
        tr = timerec.TimeRecording(config.timerec_db_filename)
        while current_date <= end_date:
            entries = tr.get_day(current_date)
            millnet_entries = [e for e in entries
                               if convert_entry(e, 'timerec', 'millnet')]
            if millnet_entries:
                days.append((current_date, millnet_entries))
            current_date += one_day

        logger.info("Reporting...")
        if args.dry_run:
            logger.info("DRY RUN")
        for date, entries in days:
            logger.info(date)
            if not args.dry_run:
                m.set_day(date, entries)
        logger.info("Done")

def run_millnet_dump(args, arg_parser):
    with millnet.Session(config.millnet_baseurl,
                         config.millnet_username,
                         config.millnet_ask_password) as m:
        for row in fetch_millnet_user_activities(m):
            print((row[1], row[0], row[3], row[2]))

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

    logger.info(f"Date range: {begin_date} - {end_date}")

    with flexhrm.Session(config.flexhrm_baseurl, config.flexhrm_username,
                         config.flexhrm_ask_password) as flex:
        days = []
        one_day = datetime.timedelta(days=1)
        current_date = begin_date
        # Collect all data before reporting, to be sure that the mapping succeeds
        logger.info("Collecting...")
        tr = timerec.TimeRecording(config.timerec_db_filename)
        while current_date <= end_date:
            entries = tr.get_day(current_date)
            flexhrm_entries = [e for e in entries
                               if convert_entry(e, 'timerec', 'flexhrm')]
            if flexhrm_entries:
                if config.detect_lunch:
                    lunch = detect_lunch(flexhrm_entries)
                    convert_entry(lunch, 'generic', 'flexhrm')
                    # TODO: Define __lt__ and use bisect.insort() to keep entries sorted
                    flexhrm_entries.append(lunch)
                days.append((current_date, flexhrm_entries))
            current_date += one_day

        logger.info("Reporting...")
        if args.dry_run:
            logger.info("DRY RUN")
        for date, entries in days:
            logger.info(date)
            if not args.dry_run:
                flex.set_day(date, entries)
        logger.info("Done")

def run_xledger_report(args, arg_parser):
    begin_date, end_date = parse_report_range(args.range)

    logger.info(f"Date range: {begin_date} - {end_date}")

    with xledger.Session(config.xledger_baseurl, config.xledger_username,
                         config.xledger_ask_password,
                         config.xledger_pair_password) as x:
        days = []
        one_day = datetime.timedelta(days=1)
        current_date = begin_date
        # Collect all data before reporting, to be sure that the mapping succeeds
        logger.info("Collecting...")
        tr = timerec.TimeRecording(config.timerec_db_filename)
        while current_date <= end_date:
            entries = tr.get_day(current_date)
            xledger_entries = [e for e in entries
                               if convert_entry(e, 'timerec', 'xledger')]
            if xledger_entries:
                days.append((current_date, xledger_entries))
            current_date += one_day

        logger.info("Reporting...")
        if args.dry_run:
            logger.info("DRY RUN")
        for date, entries in days:
            logger.info(date)
            if not args.dry_run:
                x.set_day(date, entries)
        logger.info("Done")

def detect_lunch(entries):
    # This function assumes that entries are sorted
    # TODO: Expand lunch to be longer than the minimum time
    min_begin = datetime.time(10, 30)
    max_end = datetime.time(14, 00)
    begin = min_begin
    end = (datetime.datetime.combine(datetime.datetime.min, min_begin) + config.min_lunch_duration).time()
    for entry in entries:
        # Overlap check: https://stackoverflow.com/a/325964/106019
        if entry.begin_time < end and entry.end_time > begin:
            begin = entry.end_time
            end = (datetime.datetime.combine(datetime.datetime.min, entry.end_time) + config.min_lunch_duration).time()
    if end > max_end:
        raise Exception('Failed to find lunch slot', entries)
    lunch = timereporting.Entry()
    lunch.begin_time = begin
    lunch.end_time = end
    lunch.account['generic'] = 'LUNCH'
    return lunch
        
def convert_entry(entry, from_system, to_system):
    '''
    Add information for another accounting system.

    Returns True if the entry should be counted in the to_system.
    '''
    index = config.account_mapping[from_system].index(entry.account[from_system])
    value = config.account_mapping[to_system][index]
    entry.account[to_system] = value
    return value is not None

def check_mappings():
    # TODO: Check that all mapping lists have equal length
    # Only when using them?
    pass

check_mappings()
parse_args()
