#!/usr/bin/env python

"""
Loads a CSV dump of daily stock prices from Yahoo Finance into
an OpenTSDB instance.

"""

import argparse
import csv
import requests
from datetime import datetime
from pprint import pprint

MAX_METRICS = 10

def parse_arguments():
	"""
	Parse the command-line arguments, returning a dict with all
	the parsed values.
	"""
	parser = argparse.ArgumentParser(description="""Upload a CSV of daily
stock prices from Yahoo Finance into an OpenTSDB instance.""")

	parser.add_argument(
		'--filename',
		required=True,
		action='store',
		help='The path of the CSV file to be uploaded',
	)

	parser.add_argument(
		'--date-col',
		action='store',
		dest='date_col',
		default='Date',
		help='The name of the date column in the CSV',
	)

	parser.add_argument(
		'--value-col',
		action='store',
		dest='value_col',
		default='Open',
		help='The name of the value column to use from the CSV',
	)

	parser.add_argument(
		'--host',
		action='store',
		required=True,
		help='The hostname of the OpenTSDB instance',
	)

	parser.add_argument(
		'--port',
		action='store',
		default='4242',
		help='The port number of the OpenTSDB instance',
	)

	parser.add_argument(
		'--metric',
		action='store',
		required=True,
		help='The name of the metric that will be uploaded to OpenTSDB',
	)

	parser.add_argument(
		'--tags',
		action='store',
		nargs='+',
		required=False,
		help='A set of tags to be applied to the uploaded metrics, in the form of key=value pairs',
	)

	return parser.parse_args()

def load_csv_file(filename):
	"""
	Load the supplied file ready for upload. Returns a csv.DictReader
	instance.
	"""
	with open(filename) as file_handle:
		return list(csv.DictReader(file_handle))

def row_to_metric(row, args):
	"""
	Convert a CSV row into a metric structure that will be acceptable
	to OpenTSDB.
	"""
	date_str = row[args.date_col]
	date = datetime.strptime(date_str, "%Y-%m-%d")

	tags = {}
	for tag in args.tags:
		parts = tag.split("=")
		if len(parts) != 2:
			raise ValueError("Tag format error: Expected key=value, got " + tag)

		tags[parts[0]] = parts[1]

	retval = {
		"metric": args.metric,
		"timestamp": int(date.timestamp()),
		"value": float(row[args.value_col]),
		"tags": tags
	}

	return retval

def row_is_valid(row):
	"""
	Determine whether the supplied row is valid, for storage in
	OpenTSDB.
	"""
	if row[args.value_col] == "null":
		return False
	return True

def send_to_server(metrics, args):
	"""
	HTTP POST the supplied metrics to OpenTSDB via the /api/put
	endpoint.
	"""
	url = "http://{hostname}:{port}/api/put".format(hostname=args.host,port=args.port)
	response = requests.post(
		url,
		json=metrics,
	)
	if response.status_code != 204:
		pprint("Upload to OpenTSDB failed: " + str(response.status_code))
		pprint(response.json())
		raise Exception("Upload to OpenTSDB failed")

if __name__ == "__main__":
	args = parse_arguments()
	rows = load_csv_file(args.filename)

	metrics = []
	for row in rows:
		if row_is_valid(row):
			metric = row_to_metric(row, args)
			metrics.append(metric)

			if len(metrics) >= MAX_METRICS:
				send_to_server(metrics, args)
				metrics = []