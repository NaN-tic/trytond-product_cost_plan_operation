
class PlanOperationLine:
    __name__ = 'product.cost.plan.operation_line'
    plan = fields.Many2One('product.cost.plan', 'Plan', required=True)
    product = fields.Many2One('product.product', 'Product', required=True)
    quantity = fields.Float('Quantity', required=True)
    product_cost_price = fields.Numeric('Product Cost Price', required=True)
    cost_price = fields.Numeric('Cost Price', required=True)


class Plan:
    __name__ = 'product.cost.plan'
    operations = fields.One2Many('product.cost.plan.operation_line', 'plan',
        'Operation Lines')

    def get_cost(

    @classmethod
    def get_margins(cls, plans, names):
        res = {}
        for plan in plans:
            # TODO:
            pass
        return res

    @classmethod
    @ModelView.button
    @Workflow.transition('confirmed')
    def confirm(cls, productions):
         '''
         Create margins lines
         '''
         pass


# Mòdul: product_cost_plan_teb

class Plan:
    __name__ = 'product.cost.plan'
    party = fields.Many2One('party.party', 'Party')
    payment_term = fields.Many2One('account.invoice.payment_term',
        'Payment Term', on_change_with=['party'])
    commission = fields.Float('Commission %', required=True)
    # TODO: Add here??
    pallet = fields.Boolean('TEB Pallet?')
    pallet_quantity = fields.fields.Float('Quantity per Pallet')

    @staticmethod
    def default_commission():
        return 0.0

    def on_change_with_payment_term(self):
        return (self.party.customer_payment_term.id
            if self.party and self.party.customer_payment_term else None)

    @classmethod
    @ModelView.button
    @Workflow.transition('confirmed')
    def confirm(cls, productions):
         '''
         Create:
         - payment term cost/margin
         - commission cost/margin
         - pallet cost/margin
         '''
         pass


# TODO: Comptabilitat analítica, despeses estructurals, transport
