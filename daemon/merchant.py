#!/usr/bin/env python
#
# Electrum - lightweight Bitcoin client
# Copyright (C) 2011 thomasv@gitorious
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program. If not, see <http://www.gnu.org/licenses/>.


import time, sys, socket, os
import threading
import urllib2
import json
import Queue
import sqlite3
import urllib

import electrum_fair
electrum_fair.set_verbosity(True)

import ConfigParser
config = ConfigParser.ConfigParser()
config.read("merchant.conf")

my_password = config.get('main','password')
my_host = config.get('main','host')
my_port = config.getint('main','port')

database = config.get('sqlite3','database')

received_url = config.get('callback','received')
expired_url = config.get('callback','expired')
cb_password = config.get('callback','password')

wallet_path = config.get('electrum','wallet_path')
xpub = config.get('electrum','xpub')
#Fix Me : Move the needed of this to the config file
seed = "travel nowhere air position hill peace suffer parent beautiful rise blood power home crumble teach"
password = "secret"

first_account_name = "account1"

import_private_key = "a2wKE8HzrD2Hi1EWjY1zwaY391S3igKFL3CDMxUhUMak4nuYGFUm"
import_key_address = "15mKKb2eos1hWa6tisdPwwDC1a5J1y9nma"

pending_requests = {}

num = 0

def check_create_table(conn):
    global num
    c = conn.cursor()
    c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='electrum_payments';")
    data = c.fetchall()
    if not data: 
        c.execute("""CREATE TABLE electrum_payments (address VARCHAR(40), amount FLOAT, confirmations INT(8), received_at TIMESTAMP, expires_at TIMESTAMP, paid INT(1), processed INT(1),item_number VARCHAR(24));""")
        conn.commit()

    c.execute("SELECT Count(address) FROM 'electrum_payments'")
    num = c.fetchone()[0]
    print "num rows", num


def row_to_dict(x):
    return {
        'id':x[0],
        'address':x[1],
        'amount':x[2],
        'confirmations':x[3],
        'received_at':x[4],
        'expires_at':x[5],
        'paid':x[6],
        'processed':x[7],
	'item_number':x[8]
    }



# this process detects when addresses have received payments
def on_wallet_update():
    for addr, v in pending_requests.items():
        h = wallet.history.get(addr, [])
        requested_amount = v.get('requested')
        requested_confs  = v.get('confirmations')
        value = 0
        for tx_hash, tx_height in h:
            tx = wallet.transactions.get(tx_hash)
            if not tx: continue
            if wallet.get_confirmations(tx_hash)[0] < requested_confs: continue
            for o in tx.outputs:
                o_type, o_address, o_value = o
                if o_address == addr:
                    value += o_value

        s = (value)/1.e8
        print "balance for %s:"%addr, s, requested_amount
        if s>= requested_amount: 
            print "payment accepted", addr
            out_queue.put( ('payment', addr))


stopping = False

def do_stop(password):
    global stopping
    if password != my_password:
        return "wrong password"
    stopping = True
    return "ok"

def process_request(amount, confirmations, expires_in, password, item_number):
    print "Process request %s" %amount, confirmations, expires_in, password, item_number 	
    global num
    if password != my_password:
        return "wrong password"
    try:
        amount = float(amount)
        confirmations = int(confirmations)
        expires_in = float(expires_in)
    except Exception:
        return "incorrect parameters"

    account = wallet.default_account()
    pubkeys = account.derive_pubkeys(0, num)
    addr = account.pubkeys_to_address(pubkeys)
    num += 1
    print "Address : %s" %addr
    out_queue.put( ('request', (addr, amount, confirmations, expires_in, item_number) ))
    return addr



def do_dump(password):
    if password != my_password:
        return "wrong password"
    conn = sqlite3.connect(database);
    cur = conn.cursor()
    # read pending requests from table
    cur.execute("SELECT oid, * FROM electrum_payments;")
    data = cur.fetchall()
    return map(row_to_dict, data)


def getrequest(oid, password):
    if password != my_password:
        return "wrong password"
    oid = int(oid)
    conn = sqlite3.connect(database);
    cur = conn.cursor()
    # read pending requests from table
    cur.execute("SELECT oid, * FROM electrum_payments WHERE oid=%d;"%(oid))
    data = cur.fetchone()
    return row_to_dict(data)


def send_command(cmd, params):
    import jsonrpclib
    server = jsonrpclib.Server('http://%s:%d'%(my_host, my_port))
    try:
        f = getattr(server, cmd)
    except socket.error:
        print "Server not running"
        return 1
        
    try:
        out = f(*params)
    except socket.error:
        print "Server not running"
        return 1

    print json.dumps(out, indent=4)
    return 0



def db_thread():
    conn = sqlite3.connect(database);
    # create table if needed
    check_create_table(conn)
    while not stopping:
        cur = conn.cursor()

        # read pending requests from table
        cur.execute("SELECT address, amount, confirmations, item_number FROM electrum_payments WHERE paid IS NULL;")
        data = cur.fetchall()

        # add pending requests to the wallet
        for item in data: 
            addr, amount, confirmations, item_number = item
            if addr in pending_requests: 
                continue
            else:
                with wallet.lock:
                    print "subscribing to %s"%addr
                    pending_requests[addr] = {'requested':float(amount), 'confirmations':int(confirmations)}
                    wallet.synchronizer.subscribe_to_addresses([addr])
                    wallet.up_to_date = False

        try:
            cmd, params = out_queue.get(True, 10)
        except Queue.Empty:
            cmd = ''

        if cmd == 'payment':
            addr = params
            # set paid=1 for received payments
            print "received payment from", addr
            cur.execute("update electrum_payments set paid=1 where address='%s'"%addr)

        elif cmd == 'request':
            # add a new request to the table.
            addr, amount, confs, minutes, item_number = params
            sql = "INSERT INTO electrum_payments (address, amount, confirmations, received_at, expires_at, paid, processed, item_number)"\
                + " VALUES ('%s', %.8f, %d, datetime('now'), datetime('now', '+%d Minutes'), NULL, NULL, '%s');"%(addr, amount, confs, minutes, item_number)
            print sql
            cur.execute(sql)

        # set paid=0 for expired requests 
        cur.execute("""UPDATE electrum_payments set paid=0 WHERE expires_at < CURRENT_TIMESTAMP and paid is NULL;""")

        # do callback for addresses that received payment or expired
        cur.execute("""SELECT oid, address, paid, item_number from electrum_payments WHERE paid is not NULL and processed is NULL;""")
        data = cur.fetchall()
        for item in data:
            oid, address, paid, item_number = item
            paid = bool(paid)
            headers = {'content-type':'application/html'}
            data_json = { 'address':address, 'password':cb_password, 'paid':paid, 'item_number': item_number }
#            data_json = json.dumps(data_json)
            data_encoded =  urllib.urlencode(data_json)
            url = received_url if paid else expired_url
            if not url:
                continue
            req = urllib2.Request(url, data_encoded, headers)
            try:
                response_stream = urllib2.urlopen(req)
		print response_stream.info()
                print 'Got Response %s \n for %s' %(response_stream.read(), address)
                cur.execute("UPDATE electrum_payments SET processed=1 WHERE oid=%d;"%(oid))
            except urllib2.HTTPError as e:
                print "ERROR: cannot do callback", data_json
		print "ERROR: code : %s" %e.code
                print e.read() 
            except urllib2.URLError as e:
		print 'ERROR: Can not contact with %s' %url
		print 'ERROR: Reason : %s ' % e.reason
            except ValueError, e:
                print e
                print "ERROR: cannot do callback", data_json

        conn.commit()

    conn.close()
    print "database closed"



if __name__ == '__main__':

    if len(sys.argv) > 1:
        cmd = sys.argv[1]
        params = sys.argv[2:]
        ret = send_command(cmd, params)
        sys.exit(ret)

    # start network
    c = electrum_fair.SimpleConfig({'wallet_path':wallet_path})
    daemon_socket = electrum_fair.daemon.get_daemon(c, True)
    network = electrum_fair.NetworkProxy(daemon_socket, config)
    network.start()

    # wait until connected
    while network.is_connecting():
        time.sleep(0.1)

    if not network.is_connected():
        print "daemon is not connected"
        sys.exit(1)

    # create watching_only wallet
    storage = electrum_fair.WalletStorage(wallet_path)
    if not storage.file_exists:
        print "creating wallet file"
#       wallet = electrum_fair.wallet.Wallet.from_xpub(xpub, storage)
#       def from_seed(self, seed, password, storage):
        wallet = electrum_fair.wallet.Wallet.from_seed(seed, password, storage)
    else:
        wallet = electrum_fair.wallet.Wallet(storage)

    wallet.synchronize = lambda: None # prevent address creation by the wallet
    wallet.start_threads(network)
    network.register_callback('updated', on_wallet_update)

    threading.Thread(target=db_thread, args=()).start()
    
    out_queue = Queue.Queue()
    # server thread
    from jsonrpclib.SimpleJSONRPCServer import SimpleJSONRPCServer
    server = SimpleJSONRPCServer(( my_host, my_port))
    server.register_function(process_request, 'request')
    server.register_function(do_dump, 'dump')
    server.register_function(getrequest, 'getrequest')
    server.register_function(do_stop, 'stop')
    server.socket.settimeout(1)
    while not stopping:
        try:
            server.handle_request()
        except socket.timeout:
            continue
