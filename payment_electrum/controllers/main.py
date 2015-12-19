# -*- coding: utf-8 -*-

try:
    import simplejson as json
except ImportError:
    import json
import logging
import pprint
import urllib
import urllib2
import urlparse
import werkzeug
import socket

import jsonrpclib

from openerp import http, SUPERUSER_ID
from openerp.http import request

_logger = logging.getLogger(__name__)

#ToDo: El problema mayor del script es que nos salimos del "flujo" de odoo en el método de pago, habría que integrar eso en Odoo. La página de validación que usa el módulo payment_transfer sólo sale en métodos manuales, y en el método "automático" se espera que la página se renderice fuera de Odoo y retorne cuando la transacción ha sido realizada o expirada.
# ¿¿¿¿¿ Cómo renderizar una página en payment_form de forma que se redirija tras llegar un mensaje válido a ipn o a cancel?????? ipn o cancel retornan al Demonio, no al usuario!

class ElectrumController(http.Controller):
    _notify_url = '/payment/electrum/ipn/'
    _return_url = '/payment/electrum/dpn/'
    _cancel_url = '/payment/electrum/cancel/'
    _payment_form_url = '/payment/electrum/payment_form/'
    _feedback_url = '/payment/electrum/feedback'
# ToDo: Esto habrá que pasarlo a la configuración de odoo
    merchant_host = 'http://localhost:8059'
    merchant_password = 'a'
    expires_in = 60 # minutes
    confirmations = 1	
    
    def _get_return_url(self, **post):
        """ Extract the return URL from the data coming from electrum. """
        return_url = post.pop('return_url', '')
        if not return_url:
            custom = json.loads(post.pop('custom', False) or '{}')
            return_url = custom.get('return_url', '/')
        return return_url
# vieja función de paypal, sin uso? Es un ejemplo de verificación con el server remoto, puede servir en el futuro para más seguridad
    def electrum_validate_data(self, **post):
        """Electrum IPN: three steps validation to ensure data correctness

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
            _logger.warning('Electrum: unrecognized electrum answer, received %s instead of VERIFIED or INVALID' % resp.text)
        cr, uid, context = request.cr, request.uid, request.context
	res = False """
        cr, uid, context = request.cr, SUPERUSER_ID, request.context        
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

    # LLamado por el demonio para confirmar una orden
    @http.route('/payment/electrum/ipn', type='http', auth='none', methods=['POST'])
    def electrum_ipn(self, **post):
        _logger.info('Beginning Electrum IPN form_feedback')  # debug
        cr, uid, context = request.cr, SUPERUSER_ID, request.context
        data_raw = request.httprequest.get_data()	
	data_decoded = urlparse.parse_qs(data_raw)
	_logger.info('Data decoded : %s' %data_decoded)
        data_post = {
            'payment_status': 'Completed',
	    'item_number' : data_decoded['item_number']	
         }	
	_logger.info('data posted to : %s' %data_post)
        request.registry['payment.transaction'].form_feedback(cr, uid, data_post, 'electrum', context)

        return 'OK'

    # Sin uso, creo, sería la url donde retorna paypal...
    @http.route('/payment/electrum/dpn', type='http', auth="none", methods=['POST'])
    def electrum_dpn(self, **post):
        _logger.info('Beginning Electrum DPN form_feedback with post data %s', pprint.pformat(post))  # debug
        return_url = self._get_return_url(**post)
        self.electrum_validate_data(**post)
        return werkzeug.utils.redirect(return_url)

    # LLamado por el daemon para cancelar una orden 
    @http.route('/payment/electrum/cancel', type='http', auth="none", methods=['POST'])
    def electrum_cancel(self, **post):
	_logger.info('Beginning electrum_cancel') # debug
        cr, uid, context = request.cr, SUPERUSER_ID, request.context
        data_raw = request.httprequest.get_data()	
	data_decoded = urlparse.parse_qs(data_raw)
	_logger.info('Data decoded : %s' %data_decoded)
        data_post = {
            'payment_status': 'Expired',
	    'cancelling_reason' : 'Funds has not arrive at time',
	    'item_number' : data_decoded['item_number']	
         }	
	_logger.info('data posted to : %s' %data_post)
        request.registry['payment.transaction'].form_feedback(cr, uid, data_post, 'electrum', context)

	return 'OK'

    @http.route('/payment/electrum/form_validate', type='http', auth='none')
    def electrum_form_feedback(self, **post):
        cr, uid, context = request.cr, SUPERUSER_ID, request.context
        _logger.info('Beginning form_feedback with post data %s', pprint.pformat(post))  # debug
#        request.registry['payment.transaction'].form_feedback(cr, uid, post, 'electrum', context)

        return werkzeug.utils.redirect(post.pop('return_url', '/'))

    # LLamado por Odoo tras elegir Electrum como método de pago 
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
        except socket.error, (value,message): 
            _logger.warning("ERROR: Can not connect with the Daemon %s:" %message)
            return_url = self._get_return_url(**post)
            return werkzeug.utils.redirect(return_url)
        try:
	    # Here we go
            address = f(amount, self.confirmations, self.expires_in, self.merchant_password, reference)
        except socket.error, (value,message): 
            _logger.warning("ERROR: Can not connect with the Daemon %s:" %message)
            return_url = self._get_return_url(**post)
            return werkzeug.utils.redirect(return_url)
    
        _logger.info('Faircoin address received %s' % address) # debug
         


	msg = "<h1>Faircoin payment</h1><br><br><p>Please complete the faircoin transaction as follows:</p><br><br><b>'address'</b>: %s <br><b>'amount'</b> : %s," %(address,amount)
        # ToDo: Render the qr code
	# Empty the cart
	#order = request.website.sale_get_order()
        #if order:
            #for line in order.website_order_line:
       
 	
        request.registry['payment.transaction'].form_feedback(cr, uid, post, 'electrum', context)
#        return werkzeug.utils.redirect(post.pop('return_url', '/payment/electrum/feedback/'))
	return msg

	# FixMe. Con plantilla debe retornar algo así, pero por alguna razón no funciona. Ver views/payment_form.xml
	return http.request.render('payment_electrum.payment_form', {
                'amount' : amount,
                'address' : address
		})

