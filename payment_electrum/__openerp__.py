# -*- coding: utf-8 -*-

{
    'name': 'Faircoin-electrum Payment Acquirer',
    'category': 'Hidden',
    'summary': 'Faircoin Payment Acquirer based on electrum wallet',
    'version': '0.1',
    'description': """This module permits Faircoin Payment in odoo. It is based on electrum wallet and needs the merchant.py daemon running in the background""",
    'author': 'santi ddt',
    'depends': ['payment','website'],
    'data': [
        'views/electrum.xml',
        'views/payment_acquirer.xml',
        'views/res_config_view.xml',
	'views/payment_form.xml',
        'data/electrum.xml',
    ],
    'installable': True,
}
