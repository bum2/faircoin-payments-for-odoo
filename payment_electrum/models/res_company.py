# -*- coding: utf-8 -*-

from openerp.osv import fields, osv


class ResCompany(osv.Model):
    _inherit = "res.company"

    def _get_electrum_account(self, cr, uid, ids, name, arg, context=None):
        Acquirer = self.pool['payment.acquirer']
        company_id = self.pool['res.users'].browse(cr, uid, uid, context=context).company_id.id
        electrum_ids = Acquirer.search(cr, uid, [
            ('website_published', '=', True),
            ('name', 'ilike', 'electrum'),
            ('company_id', '=', company_id),
        ], limit=1, context=context)
        if electrum_ids:
            electrum = Acquirer.browse(cr, uid, electrum_ids[0], context=context)
            return dict.fromkeys(ids, electrum.electrum_email_account)
        return dict.fromkeys(ids, False)

    def _set_electrum_account(self, cr, uid, id, name, value, arg, context=None):
        Acquirer = self.pool['payment.acquirer']
        company_id = self.pool['res.users'].browse(cr, uid, uid, context=context).company_id.id
        electrum_account = self.browse(cr, uid, id, context=context).electrum_account
        electrum_ids = Acquirer.search(cr, uid, [
            ('website_published', '=', True),
            ('electrum_email_account', '=', electrum_account),
            ('company_id', '=', company_id),
        ], context=context)
        if electrum_ids:
            Acquirer.write(cr, uid, electrum_ids, {'electrum_email_account': value}, context=context)
        return True

    _columns = {
        'electrum_account': fields.function(
            _get_electrum_account,
            fnct_inv=_set_electrum_account,
            nodrop=True,
            type='char', string='Electrum Account',
            help="Electrum username (usually email) for receiving online payments."
        ),
    }
