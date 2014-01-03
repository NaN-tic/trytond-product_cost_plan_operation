from decimal import Decimal
from trytond.model import ModelSQL, ModelView, fields
from trytond.pool import Pool, PoolMeta
from trytond.pyson import Eval

__all__ = ['PlanOperationLine', 'Plan']
__metaclass__ = PoolMeta


class PlanOperationLine(ModelSQL, ModelView):
    'Product Cost Plan Operation Line'
    __name__ = 'product.cost.plan.operation_line'

    plan = fields.Many2One('product.cost.plan', 'Plan', required=True)
    work_center = fields.Many2One('production.work_center', 'Work Center',
        required=True)
    route_operation = fields.Many2One('production.route.operation',
        'Route Operation')
    uom_category = fields.Function(fields.Many2One(
            'product.uom.category', 'Uom Category', on_change_with=[
                'work_center']),
        'on_change_with_uom_category')
    uom = fields.Many2One('product.uom', 'Uom', required=True, domain=[
            ('category', '=', Eval('uom_category')),
            ], depends=['uom_category'], on_change_with=['work_center'])
    unit_digits = fields.Function(fields.Integer('Unit Digits',
            on_change_with=['uom']), 'on_change_with_unit_digits')
    quantity = fields.Float('Quantity', required=True,
        digits=(16, Eval('unit_digits', 2)), depends=['unit_digits'])
    cost = fields.Function(fields.Numeric('Cost', on_change_with=['quantity',
                'cost_price', 'uom', 'work_center']), 'on_change_with_cost')

    def on_change_with_uom_category(self, name=None):
        if self.work_center:
            return self.work_center.uom.category.id

    def on_change_with_uom(self):
        if self.work_center:
            return self.work_center.uom.id

    def on_change_with_unit_digits(self, name=None):
        if self.uom:
            return self.uom.digits
        return 2

    def on_change_with_cost(self, name=None):
        pool = Pool()
        Uom = pool.get('product.uom')
        quantity = Uom.compute_qty(self.uom, self.quantity,
            self.work_center.uom)
        return Decimal(str(quantity)) * self.work_center.cost_price


class Plan:
    __name__ = 'product.cost.plan'

    route = fields.Many2One('production.route', 'Route',
        on_change=['route', 'operations'], states={
            'readonly': Eval('state') != 'draft',
            }, depends=['state'])
    operations = fields.One2Many('product.cost.plan.operation_line', 'plan',
        'Operation Lines', states={
            'readonly': Eval('state') != 'draft',
            }, depends=['state'])
    operation_cost = fields.Function(fields.Numeric('Operation Cost',
            on_change_with=['operations']), 'on_change_with_operation_cost')

    def update_operations(self):
        pool = Pool()
        WorkCenter = pool.get('production.work_center')
        if not self.route:
            return {}
        operations = {
            'remove': [x.id for x in self.operations],
            'add': [],
            }
        changes = {
            'operations': operations,
            }
        for operation in self.route.operations:
            work_center = None
            if operation.work_center:
                work_center = operation.work_center
            elif operation.work_center_category:
                centers = WorkCenter.search([
                        ('category', '=', operation.work_center_category),
                        ], limit=1)
                if centers:
                    work_center, = centers

            if not work_center:
                self.raise_user_error('no_work_center', operation.rec_name)

            operations['add'].append({
                    'work_center': work_center.id,
                    'route_operation': operation.id,
                    'uom': work_center.uom.id,
                    'quantity': 0.0,
                    })
        return changes

    def on_change_route(self):
        return self.update_operations()

    def on_change_with_total_cost(self, name=None):
        cost = super(Plan, self).on_change_with_total_cost(name)
        return cost + self.operation_cost

    def on_change_with_operation_cost(self, name=None):
        cost = Decimal('0.0')
        for operation in self.operations:
            cost += operation.cost
        return cost
