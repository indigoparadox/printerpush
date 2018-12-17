#!/usr/bin/env python

import logging
import ldap
import argparse
import json
try:
	from configparser import ConfigParser
except ImportError:
	from ConfigParser import ConfigParser
from printers import Ricoh

def get_tag_idx( name ):
	tag_idx = {
		'A': 2,
		'B': 2,
		'C': 3,
		'D': 3,
		'E': 4,
		'F': 4,
		'G': 5,
		'H': 5,
		'I': 6,
		'J': 6,
		'K': 6,
		'L': 7,
		'M': 7,
		'N': 7,
		'O': 8,
		'P': 8,
		'Q': 8,
		'R': 9,
		'S': 9,
		'T': 9,
		'U': 10,
		'V': 10,
		'W': 10,
		'X': 11,
		'Y': 11,
		'Z': 11
	}
	return tag_idx[name[0]]

def ad_connect( servername, bindname, bindpw ):
	logger = logging.getLogger( 'ad.connect' )

	config = ConfigParser()

	try:
		config.read( 'adauth.ini' )

		lc = ldap.initialize( config.get( 'ldap', 'server' ) )
		lc.protocol_version = 3
		lc.set_option( ldap.OPT_REFERRALS, 0 )
		logger.info( 'Connecting to {} as {}...'.format(
			config.get( 'ldap', 'server' ),
			config.get( 'ldap', 'bindname' )
		) )
		lc.simple_bind_s(
			config.get( 'ldap', 'bindname' ),
			config.get( 'ldap', 'bindpw' )
		)
	except ldap.LDAPError as ex:
		lc.unbind_s()
		logger.error( ex ) 
		return None

	logger.info( 'LDAP bind successful.' )
	return lc

def get_ad_users():

	ad_config = ConfigParser()
	ad_config.read( 'adauth.ini' )
	
	lc = ad_connect(
		ad_config.get( 'ldap', 'server' ),
		ad_config.get( 'ldap', 'bindname' ),
		ad_config.get( 'ldap', 'bindpw' )
	)
	res = lc.search_s( 
		ad_config.get( 'ldap', 'basedn' ),
		ldap.SCOPE_SUBTREE,
		ad_config.get( 'ldap', 'filter' )
	)
	
	ad_users = {}
	for ad_user in res:
		if 'mail' in ad_user[1]:
			ad_mail = ad_user[1]['mail'][0].lower()
			ad_users[ad_mail] = {
				'id': '{}{}'.format(
					ad_user[1]['givenName'][0],
					ad_user[1]['sn'][0][0]
				),
				'fullname': '{} {}'.format(
					ad_user[1]['givenName'][0],
					ad_user[1]['sn'][0]
				),
				'name': '{} {}'.format(
					ad_user[1]['givenName'][0],
					ad_user[1]['sn'][0][0]
				),
				'mail': ad_mail,
				'tag': get_tag_idx( ad_user[1]['givenName'][0] )
			}

	additions = json.loads( ad_config.get( 'ldap', 'additions' ) )
	for add_user in additions:
		ad_users[add_user['mail']] = add_user

	return ad_users

def export_user( user ):
	line = ''
	for field in user._fields:
		field_data = user._asdict()[field]
		if field_data:
			line += field_data + ','
		else:
			line += ','
	return line

def sync_rem_ad_missing( user, ad_users, printer_users, ricoh ):

	logger = logging.getLogger( 'sync' )

	if '' != user.mailaddress and \
	user.mailaddress.lower() not in ad_users:
		logger.warning(
			'Removing user not in AD: {} ({})'.format(
				user.name, user.mailaddress ) )
		ricoh.delete_user( user.id )
		return True
	elif '' != user.mailaddress:
		printer_users[user.mailaddress.lower()] = {
			'name': user.name,
			'mail': user.mailaddress.lower()
		}
		return False

def sync_printer( pname, host, user, pw, ad_users, af, rf, fields=None ):

	logger = logging.getLogger( 'sync' )

	printer_users = {}
	printer_conn = dict( host=host, username=user, password=pw )
	with Ricoh( **printer_conn ) as ricoh:
		logger.warning( 'Printer: {}'.format( pname ) )

		for user in ricoh:
			# If this is the first line, write the field names.
			if not fields:
				af.write( 'UserID,Name,Display,EMail,Printer\n' )
				rf.write( ','.join( user._fields ) )
				rf.write( ',printer\n' )
				fields = user._fields

			res = sync_rem_ad_missing( user, ad_users, printer_users, ricoh )
			if res:
				rf.write( export_user( user ) )
				rf.write( ',' + pname + '\n'  )

		for ad_user in ad_users:
			if ad_users[ad_user]['mail'] not in printer_users:
				adid = ad_users[ad_user]['id']
				adfullname = ad_users[ad_user]['fullname']
				addisplay = ad_users[ad_user]['name']
				admail = ad_users[ad_user]['mail']

				logger.warning( '{}: Adding missing user: [{}] {} ({})'.format(
					pname, ad_users[ad_user]['tag'], addisplay, admail ) )
				ricoh.add_user(
					userid=adid, name=adfullname, displayName=addisplay,
					email=admail )
				af.write( '"{}","{}","{}","{}","{}"\n'.format(
					adid, adfullname, addisplay, admail, pname ) )

	return fields

def main():

	parser = argparse.ArgumentParser()
	subparsers = parser.add_subparsers( dest='action' )

	parse_export = subparsers.add_parser( 'export' )
	parse_export.add_argument( '-a', '--add-filename', action='store' )
	parse_export.add_argument( '-r', '--rem-filename', action='store' )

	args = parser.parse_args()

	logging.basicConfig( level=logging.WARNING )
	logger = logging.getLogger( 'main' )

	p_config = ConfigParser()
	p_config.read( 'printers.ini' )

	ad_users = get_ad_users()

	if None == args.rem_filename:
		fn_rem = '/dev/null'

	fields = None
	with open( args.rem_filename, 'w' ) as rem_log:
		with open( args.add_filename, 'w' ) as add_log:
			for printer in p_config.sections():
				host = p_config.get( printer, 'address' )
				username = p_config.get( printer, 'user' )
				password = p_config.get( printer, 'password' )
				fields = sync_printer( printer, host, username, password, \
					ad_users, add_log, rem_log, fields )

if '__main__' == __name__:
	main()

