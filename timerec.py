import sqlite3
import datetime

CHECK_ACTION_IN = 10
CHECK_ACTION_OUT = 20

class Session:
    def __init__(self):
        self.begin = None
        self.end = None
        self.customer = None
        self.project = None
        self.comment = None

    def __str__(self):
        if self.end is not None:
            end_str = self.end.time().strftime("%H:%M")
        else:
            end_str = None
        return "%s %s-%s %s %s %s" % (self.begin.date(),
                                      self.begin.time().strftime("%H:%M"),
                                      end_str, self.customer,
                                      self.project, self.comment)

class TimeRecording:

    def __init__(self, database):
        self.conn = sqlite3.connect(database)

    def get_day(self, date):
        date_str = date.strftime("%Y-%m-%d 00:00:00")
        c = self.conn.cursor()
        c.execute("select stamp_date_str, check_action, customer, t_category_1.name, comment from T_STAMP_3 left outer join T_CATEGORY_1 on T_CATEGORY_1.id = T_STAMP_3.category_id where asofdate == ? order by stamp_date_str asc, check_action desc", (date_str,))

        sessions = []
        last_action = None
        row = c.fetchone()
        last_row = None
        current_session = None
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
                current_session = Session()
                current_session.begin = dt
                current_session.customer = customer
                current_session.project = category
                current_session.comment = comment
            elif action == CHECK_ACTION_OUT:
                current_session.end = dt
                sessions.append(current_session)
                current_session = None

            last_action = action
            last_row = row
            row = c.fetchone()

        if last_action != CHECK_ACTION_OUT and current_session:
            print("Last action was not check")
            raise Exception(f"Non-completed session: {current_session}")

        return sessions 
