#!/usr/bin/env python

import logging
try:
	from configparser import ConfigParser
except ImportError:
	from ConfigParser import ConfigParser
from flask import Flask, render_template, request
from printers import Ricoh

app = Flask( __name__ )

@app.route( '/add' )
def route_add():
	return render_template( 'add.html' )

@app.route( '/do-add', methods=['POST'] )
def route_do_add():
	config = ConfigParser()
	config.read( 'printers.ini' )
	for section in config.sections():
		with Ricoh( **printer_conn ) as ricoh:
			pass

@app.route( '/list' )
def route_list():
	users = []
	config = ConfigParser()
	config.read( 'printers.ini' )
	for section in config.sections():
		printer_conn = dict(
			 host=config[section]['address'],
			 username=config[section]['user'],
			 password=config[section]['password']
		)
		with Ricoh( **printer_conn ) as ricoh:
			for user in ricoh:
				user.printer = section
				users += [user]

	return render_template( 'list.html', users=users )

if '__main__' == __name__:
	app.run( host='0.0.0.0' )

