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

import sqlite3
import datetime
import timereporting

CHECK_ACTION_IN = 10
CHECK_ACTION_OUT = 20

class TimeRecording:

    def __init__(self, database):
        self.conn = sqlite3.connect(database)

    def get_day(self, date):
        date_str = date.strftime("%Y-%m-%d 00:00:00")
        c = self.conn.cursor()
        c.execute("select stamp_date_str, check_action, customer, t_category_1.name, comment from T_STAMP_3 left outer join T_CATEGORY_1 on T_CATEGORY_1.id = T_STAMP_3.category_id where asofdate == ? order by stamp_date_str asc, check_action desc", (date_str,))

        entries = []
        last_action = None
        row = c.fetchone()
        last_row = None
        current_entry = None
        while row:
            #print(row)
            # Parse stamp
            dt = datetime.datetime.strptime(row[0], "%Y-%m-%d %H:%M:%S")
            action = row[1]
            customer = row[2]
            category = row[3]
            comment = row[4]

            if action == last_action:
                print("Same action twice!")
                print("Previous row: ", last_row)
                print("Current row:  ", row)
            elif action == CHECK_ACTION_IN:
                current_entry = timereporting.Entry()
                current_entry.begin_time = dt.time()
                current_entry.account['timerec'] = (customer, category)
                current_entry.comment = comment
            elif action == CHECK_ACTION_OUT:
                current_entry.end_time = dt.time()
                entries.append(current_entry)
                current_entry = None

            last_action = action
            last_row = row
            row = c.fetchone()

        if last_action != CHECK_ACTION_OUT and current_entry:
            print("Last action was not check")
            raise Exception(f"Non-completed entry: {current_entry}")

        return entries 
