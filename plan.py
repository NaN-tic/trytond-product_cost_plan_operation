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
    work_center = fields.Many2One('production.work_center', 'Work Center')
    work_center_category = fields.Many2One('production.work_center.category',
        'Work Center Category')
    route_operation = fields.Many2One('production.route.operation',
        'Route Operation')
    uom_category = fields.Function(fields.Many2One(
            'product.uom.category', 'Uom Category', on_change_with=[
                'work_center', 'work_center_category']),
        'on_change_with_uom_category')
    uom = fields.Many2One('product.uom', 'Uom', required=True, domain=[
            ('category', '=', Eval('uom_category')),
            ], depends=['uom_category'], on_change_with=['work_center',
            'work_center_category'])
    unit_digits = fields.Function(fields.Integer('Unit Digits',
            on_change_with=['uom']), 'on_change_with_unit_digits')
    quantity = fields.Float('Quantity', required=True,
        digits=(16, Eval('unit_digits', 2)), depends=['unit_digits'])
    cost = fields.Function(fields.Numeric('Cost', on_change_with=['quantity',
                'cost_price', 'uom', 'work_center', 'work_center_category']),
                'on_change_with_cost')

    def on_change_with_uom_category(self, name=None):
        if self.work_center:
            return self.work_center.uom.category.id
        elif self.work_center_category:
            return self.work_center_category.uom.category.id

    def on_change_with_uom(self):
        if self.work_center:
            return self.work_center.uom.id
        if self.work_center_category:
            return self.work_center_category.uom.id

    def on_change_with_unit_digits(self, name=None):
        if self.uom:
            return self.uom.digits
        return 2

    def on_change_with_cost(self, name=None):
        pool = Pool()
        Uom = pool.get('product.uom')
        wc = self.work_center or self.work_center_category
        quantity = Uom.compute_qty(self.uom, self.quantity,
            wc.uom)
        return Decimal(str(quantity)) * wc.cost_price


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
            work_center_category = None
            if operation.work_center:
                work_center = operation.work_center
            elif operation.work_center_category:
                work_center_category = operation.work_center_category

            wc = work_center or work_center_category
            operations['add'].append({
                    'work_center': work_center and work_center.id or None,
                    'work_center_category': work_center_category and
                        work_center_category.id or None,
                    'route_operation': operation.id,
                    'uom': wc.uom.id,
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
            cost += operation.cost or Decimal('0.0')
        return cost
