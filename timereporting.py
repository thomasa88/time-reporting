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

class Day:
    def __init__(self):
        pass

    # def set_total_hours(cls, amount, start_of_day=datetime.time(8, 00),
    #                     lunch_start=datetime.time(12, 00),
    #                     lunch_end=datetime.time(13, 00)):
    #     pass

    def get_total_hours():
        pass

class Entry:
    def __init__(self):
        self.begin_time = None
        self.end_time = None

        # Different reports will have e.g. one or multiple of company,
        # client and project. If one is consulting, any <project> in
        # one system can be <client> in another.  Therefore, we keep a
        # generic "account" dictionary, where the variants for
        # different systems can be filled in as needed.
        self.account = {}
        
        self.comment = None

    def __str__(self):
        return '%s-%s %s %s' % (self.begin_time,
                                self.end_time,
                                self.account,
                                self.comment)
