import csv
import os
from collections import defaultdict
import logging

logger = logging.getLogger(__name__)

FILE_DIR = os.path.dirname(os.path.realpath(__file__))

account_mapping = defaultdict(list)

with open(FILE_DIR + '/mapping.csv', newline='') as csv_file:
    reader = csv.reader(csv_file)

    headers = next(reader)
    column_mapping = defaultdict(list)
    for i, header in enumerate(headers):
        system, _, subinfo = header.partition('-')
        column_mapping[system].append(i)

    for row in reader:
        for system, columns in column_mapping.items():
            account = tuple(row[c] for c in columns)
            empty = True
            for c in account:
                if c:
                    empty = False
                    break
            if empty:
                # No data on this line. It should be ignored
                # when mapped to this system.
                account = None
            account_mapping[system].append(account)

logger.debug(f'CSV Account mapping {account_mapping}')
