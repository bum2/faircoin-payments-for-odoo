# -*- coding: utf-8 -*-

try:
    import simplejson as json
except ImportError:
    import json
import logging
import pprint
import urllib
import urllib2
import werkzeug
import socket

import jsonrpclib

from openerp import http, SUPERUSER_ID
from openerp.http import request

_logger = logging.getLogger(__name__)


class ElectrumController(http.Controller):
    _notify_url = '/payment/electrum/ipn/'
    _return_url = '/payment/electrum/dpn/'
    _cancel_url = '/payment/electrum/cancel/'
    _payment_form_url = '/payment/electrum/payment_form/'
    _feedback_url = '/payment/electrum/feedback'

    merchant_host = 'http://localhost:8059'
    merchant_password = 'a'
    expires_in = 5
    confirmations = 6	
    
    def _get_return_url(self, **post):
        """ Extract the return URL from the data coming from electrum. """
        return_url = post.pop('return_url', '')
        if not return_url:
            custom = json.loads(post.pop('custom', False) or '{}')
            return_url = custom.get('return_url', '/')
        return return_url

    def electrum_validate_data(self, **post):
        """ Electrum IPN: three steps validation to ensure data correctness

        - step 1: return an empty HTTP 200 response -> will be done at the end
           by returning ''
        - step 2: POST the complete, unaltered message back to Electrum (preceded
           by cmd=_notify-validate), with same encoding
        - step 3: electrum send either VERIFIED or INVALID (single word)

        Once data is validated, process it.

        new_post = dict(post, cmd='_notify-validate')

        electrum_urls = request.registry['payment.acquirer']._get_electrum_urls(cr, uid, tx and tx.acquirer_id and tx.acquirer_id.environment or 'prod', context=context)
        validate_url = electrum_urls['electrum_form_url']
        urequest = urllib2.Request(validate_url, werkzeug.url_encode(new_post))
        uopen = urllib2.urlopen(urequest)
        resp = uopen.read()

        if resp == 'VERIFIED':
            _logger.info('Electrum: validated data')
            res = request.registry['payment.transaction'].form_feedback(cr, SUPERUSER_ID, post, 'electrum', context=context)
        elif resp == 'INVALID':
            _logger.warning('Electrum: answered INVALID on data verification')
        else:
            _logger.warning('Electrum: unrecognized electrum answer, received %s instead of VERIFIED or INVALID' % resp.text)"""
        cr, uid, context = request.cr, request.uid, request.context
	res = False
        reference = post.get('item_number')
        tx = None
        if reference:
            tx_ids = request.registry['payment.transaction'].search(cr, uid, [('reference', '=', reference)], context=context)
            if tx_ids:
                tx = request.registry['payment.transaction'].browse(cr, uid, tx_ids[0], context=context)
	if (post.get('paid')):
        #Payment complete
            _logger.info('Electrum: payment complete in reference %s' % reference)
            res = request.registry['payment.transaction'].form_feedback(cr, SUPERUSER_ID, post, 'electrum', context=context)
	else:
	#Payment expired
            _logger.info('Electrum: payment expired')  	
	    res = request.registry['payment.transaction'].cancel_url(cr, SUPERUSER_ID, post, 'electrum', context=context)
        return res 

    @http.route('/payment/electrum/ipn', type='http', auth='none', methods=['POST'])
    def electrum_ipn(self, **post):
        """ Electrum IPN. """
        _logger.info('Beginning Electrum IPN form_feedback with post data %s', pprint.pformat(post))  # debug
        self.electrum_validate_data(**post)
        return ''

    @http.route('/payment/electrum/dpn', type='http', auth="none", methods=['POST'])
    def electrum_dpn(self, **post):
        """ Electrum DPN """
        _logger.info('Beginning Electrum DPN form_feedback with post data %s', pprint.pformat(post))  # debug
        return_url = self._get_return_url(**post)
        self.electrum_validate_data(**post)
        return werkzeug.utils.redirect(return_url)

    @http.route('/payment/electrum/cancel', type='http', auth="none", methods=['POST'])
    def electrum_cancel(self, **post):
        """ When the user cancels its Electrum payment: GET on this route """
        cr, uid, context = request.cr, SUPERUSER_ID, request.context
        _logger.info('Beginning Electrum cancel with post data %s', pprint.pformat(post))  # debug
        return_url = self._get_return_url(**post)
        return werkzeug.utils.redirect(return_url)

    @http.route('/payment/electrum/payment_form', type='http', auth="none", website="True")
    def electrum_payment_form(self, **post):
	""" Render the faircoin payment screen and notify the daemon with a new request """
        cr, uid, context = request.cr, SUPERUSER_ID, request.context
        reference = post.get('item_number')
        _logger.info('Beginning Electrum render form with post data %s', pprint.pformat(post))  # debug
        # get the address and do a request
        tx = None
        if reference:
            tx_ids = request.registry['payment.transaction'].search(cr, uid, [('reference', '=', reference)], context=context)
            if tx_ids:
                tx = request.registry['payment.transaction'].browse(cr, uid, tx_ids[0], context=context)
        electrum_urls = request.registry['payment.acquirer']._get_electrum_urls(cr, uid, tx and tx.acquirer_id and tx.acquirer_id.environment or 'prod', context=context)
        validate_url = electrum_urls['electrum_daemon_url']
	amount = post.get('amount')
        headers = {'content-type':'application/json'}
        data_json = { 'amount':amount, 'confirmations':'6','expires_in':'4', 'password':'','item_number':reference}
        data_json = json.dumps(data_json)
        _logger.info('Trying request %s' % data_json)  # debug

        server = jsonrpclib.Server(self.merchant_host)
        try:
            f = getattr(server, 'request')
        except socket.error:
            print "Server not running"
            return_url = self._get_return_url(**post)
            return werkzeug.utils.redirect(return_url)
        try:
            address = f(amount, self.confirmations, self.expires_in, self.merchant_password, reference)
        except socket.error:
            print "Server not running"
            return_url = self._get_return_url(**post)
            return werkzeug.utils.redirect(return_url)
    
        _logger.info('Faircoin address received %s' % address) # debug
         
 
        #return "Hello, world"
	msg = "<h1>Faircoin payment</h1><br><br><p>Please complete the faircoin transaction as follow:</p><br><br><b>'address'</b>: %s <br><b>'amount'</b> : %s," %(address,amount)
        return msg


        # Render the qr code

	# ¿Qué debe retornar?
	http.request.render('payment_electrum.electrum_payment_form', {
                'amount' : amount,
                'address' : address
		})
        #return_url = self._get_return_url(**post)
        #return werkzeug.utils.redirect(return_url)

        cr, uid, context = request.cr, SUPERUSER_ID, request.context
        _logger.info('Beginning form_feedback with post data %s', pprint.pformat(post))  # debug
        request.registry['payment.transaction'].form_feedback(cr, uid, post, 'electrum', context)
        return werkzeug.utils.redirect(post.pop('return_url', '/payment/electrum/feedback/'))
