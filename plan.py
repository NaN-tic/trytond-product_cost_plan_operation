from decimal import Decimal
from trytond.model import ModelSQL, ModelView, fields
from trytond.pool import Pool, PoolMeta
from trytond.pyson import Eval, Id

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
        'Route Operation', on_change=['route_operation'])
    time = fields.Float('Quantity', required=True,
        digits=(16, Eval('unit_digits', 2)), depends=['unit_digits'])
    time_uom = fields.Many2One('product.uom', 'Uom', required=True, domain=[
            ('category', '=', Id('product', 'uom_cat_time')),
            ], on_change_with=['work_center', 'work_center_category'])
    time_uom_digits = fields.Function(fields.Integer('Time UOM Digits',
            on_change_with=['uom']), 'on_change_with_time_uom_digits')
    cost = fields.Function(fields.Numeric('Cost', on_change_with=['time',
                'cost_price', 'time_uom', 'work_center',
                'work_center_category']), 'on_change_with_cost')

    def on_change_route_operation(self):
        res = {}
        route = self.route_operation
        if not route:
            return res
        if route.work_center:
            res['work_center'] = route.work_center.id
        if route.work_center_category:
            res['work_center_category'] = route.work_center_category.id
        if route.time_uom:
            res['time_uom'] = route.time_uom.id
        if route.time:
            res['time'] = route.time
        return res

    def on_change_with_time_uom(self):
        if self.work_center:
            return self.work_center.uom.id
        if self.work_center_category:
            return self.work_center_category.uom.id

    def on_change_with_uom_digits(self, name=None):
        if self.time_uom:
            return self.time_uom.digits
        return 2

    def on_change_with_cost(self, name=None):
        pool = Pool()
        Uom = pool.get('product.uom')
        wc = self.work_center or self.work_center_category
        if not wc:
            return Decimal('0.0')
        time = Uom.compute_qty(self.time_uom, self.time,
            wc.uom)
        return Decimal(str(time)) * wc.cost_price


class Plan:
    __name__ = 'product.cost.plan'

    route = fields.Many2One('production.route', 'Route',
        on_change=['route', 'operations', 'bom', 'product'],
        states={
            'readonly': Eval('state') != 'draft',
            },
        depends=['state'])
    operations = fields.One2Many('product.cost.plan.operation_line', 'plan',
        'Operation Lines', on_change=['costs', 'operations'])
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
        factor = 1.0
        #if self.bom and self.bom.route and self.bom.route == self.route:
            #factor = self.bom.compute_factor(self.product, 1,
                #self.product.default_uom)
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
                    'time_uom': operation.time_uom.id,
                    'time': operation.time * factor,
                    })
        return changes

    def on_change_route(self):
        return self.update_operations()

    def on_change_with_operation_cost(self, name=None):
        cost = Decimal('0.0')
        for operation in self.operations:
            cost += operation.cost or Decimal('0.0')
        return cost

    def on_change_operations(self):
        pool = Pool()
        CostType = pool.get('product.cost.plan.cost.type')
        ModelData = pool.get('ir.model.data')

        type_ = CostType(ModelData.get_id('product_cost_plan_operation',
                'operations'))
        self.operation_cost = sum(o.cost for o in self.operations if o.cost)
        return self.update_cost_type(type_, self.operation_cost)

    @classmethod
    def get_cost_types(cls):
        """
        Returns a list of values with the cost types and the field to get
        their cost.
        """
        pool = Pool()
        CostType = pool.get('product.cost.plan.cost.type')
        ModelData = pool.get('ir.model.data')
        ret = super(Plan, cls).get_cost_types()
        type_ = CostType(ModelData.get_id('product_cost_plan_operation',
            'operations'))
        ret.append((type_, 'operation_cost'))
        return ret
