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
        'Route Operation', on_change=['route_operation'])
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

    def on_change_route_operation(self):
        res = {}
        route = self.route_operation
        if not route:
            return res
        if route.work_center:
            res['work_center'] = route.work_center.id
        if route.work_center_category:
            res['work_center_category'] = route.work_center_category.id
        if route.uom:
            res['uom'] = route.uom.id
        if route.quantity:
            res['quantity'] = route.quantity
        return res

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
        if not wc:
            return Decimal('0.0')
        quantity = Uom.compute_qty(self.uom, self.quantity,
            wc.uom)
        return Decimal(str(quantity)) * wc.cost_price


class Plan:
    __name__ = 'product.cost.plan'

    route = fields.Many2One('production.route', 'Route',
        on_change=['route', 'operations', 'bom', 'product', 'quantity'],
        states={
            'readonly': Eval('state') != 'draft',
            },
        depends=['state'])
    operations = fields.One2Many('product.cost.plan.operation_line', 'plan',
        'Operation Lines', on_change=['costs', 'operations'])
    operation_cost = fields.Function(fields.Numeric('Operation Cost',
            on_change_with=['operations']), 'on_change_with_operation_cost')

    @classmethod
    def __setup__(cls):
        super(Plan, cls).__setup__()
        if not cls.quantity.on_change:
            cls.quantity.on_change = []
        for name in cls.route.on_change:
            if not name in cls.quantity.on_change:
                cls.quantity.on_change.append(name)

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
        if self.bom and self.bom.route and self.bom.route == self.route:
            factor = self.bom.compute_factor(self.product, self.quantity or 0,
                self.product.default_uom)
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
                    'quantity': operation.quantity * factor,
                    })
        return changes

    def on_change_route(self):
        return self.update_operations()

    def on_change_quantity(self):
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
