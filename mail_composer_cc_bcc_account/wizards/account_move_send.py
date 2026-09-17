# Copyright 2024 Camptocamp
# Copyright 2026 Scalizer (v19 port)
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import Command, api, fields, models, tools


class AccountMoveSendWizard(models.TransientModel):
    """Add CC/BCC recipients on the single-invoice sending wizard.

    In Odoo 17 the wizard was ``account.move.send``. In v19 it has been split
    into an AbstractModel (shared logic) and a TransientModel (the actual
    wizard, ``account.move.send.wizard``). We inherit the latter to declare
    the extra fields and adapt the compute/default.
    """

    _inherit = "account.move.send.wizard"

    partner_cc_ids = fields.Many2many(
        "res.partner",
        "account_move_send_res_partner_cc_rel",
        "wizard_id",
        "partner_id",
        string="Cc",
        compute="_compute_mail_partner_cc_bcc_ids",
        store=True,
        readonly=False,
    )
    partner_bcc_ids = fields.Many2many(
        "res.partner",
        "account_move_send_res_partner_bcc_rel",
        "wizard_id",
        "partner_id",
        string="Bcc",
        compute="_compute_mail_partner_cc_bcc_ids",
        store=True,
        readonly=False,
    )

    def _get_partner_ids_from_mail(self, move, emails):
        partners = self.env["res.partner"].with_company(move.company_id)
        for mail_data in tools.email_split(emails or ""):
            partners |= partners.find_or_create(mail_data)
        return partners

    @api.model
    def default_get(self, fields_list):
        # Seed cc/bcc from the current company's default partner lists
        # (fields declared by mail_composer_cc_bcc on res.company).
        company = self.env.company
        res = super().default_get(fields_list)
        partner_cc = company.default_partner_cc_ids
        if partner_cc:
            res["partner_cc_ids"] = [Command.set(partner_cc.ids)]
        partner_bcc = company.default_partner_bcc_ids
        if partner_bcc:
            res["partner_bcc_ids"] = [Command.set(partner_bcc.ids)]
        return res

    @api.depends("template_id")
    def _compute_mail_partner_cc_bcc_ids(self):
        # [MIG v19]: In v17 this compute was gated on ``mode == 'invoice_single'``
        # and used ``mail_template_id`` / ``move_ids``. In v19 the wizard is
        # always single-invoice (batch has its own wizard) and the field name
        # is ``template_id`` / ``move_id``.
        for wizard in self:
            template = wizard.template_id
            move = wizard.move_id
            if template and move:
                wizard.partner_cc_ids = self._get_partner_ids_from_mail(
                    move, template.email_cc
                )
                wizard.partner_bcc_ids = self._get_partner_ids_from_mail(
                    move, template.email_bcc
                )
            else:
                wizard.partner_cc_ids = None
                wizard.partner_bcc_ids = None

    def action_send_and_print(self, allow_fallback_pdf=False):
        # Propagate cc/bcc to the shared AbstractModel via context so
        # mail.thread._message_create (extended by this module) can attach
        # them to the created ``mail.message``.
        wizard = self.with_context(
            partner_cc_ids=self.partner_cc_ids,
            partner_bcc_ids=self.partner_bcc_ids,
        )
        return super(AccountMoveSendWizard, wizard).action_send_and_print(
            allow_fallback_pdf=allow_fallback_pdf,
        )
