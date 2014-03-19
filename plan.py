from decimal import Decimal
from trytond.model import ModelSQL, ModelView, fields
from trytond.pool import Pool, PoolMeta
from trytond.pyson import Eval, Id, If, Bool

__all__ = ['PlanOperationLine', 'Plan']
__metaclass__ = PoolMeta

_ZERO = Decimal('0.0')


class PlanOperationLine(ModelSQL, ModelView):
    'Product Cost Plan Operation Line'
    __name__ = 'product.cost.plan.operation_line'

    plan = fields.Many2One('product.cost.plan', 'Plan', required=True,
        ondelete='CASCADE')
    sequence = fields.Integer('Sequence')
    work_center = fields.Many2One('production.work_center', 'Work Center')
    work_center_category = fields.Many2One('production.work_center.category',
        'Work Center Category')
    operation_type = fields.Many2One('production.operation.type',
        'Operation Type')
    time = fields.Float('Quantity', required=True,
        digits=(16, Eval('time_uom_digits', 2)), depends=['time_uom_digits'])
    time_uom = fields.Many2One('product.uom', 'Uom', required=True, domain=[
            ('category', '=', Id('product', 'uom_cat_time')),
            ], on_change_with=['work_center', 'work_center_category'])
    time_uom_digits = fields.Function(fields.Integer('Time UOM Digits',
            on_change_with=['uom']), 'on_change_with_time_uom_digits')
    quantity = fields.Float('Quantity', states={
            'required': Eval('calculation') == 'standard',
            'invisible': Eval('calculation') != 'standard',
            },
        digits=(16, Eval('quantity_uom_digits', 2)),
        depends=['quantity_uom_digits', 'calculation'],
        help='Quantity of the production product processed by the specified '
        'time.' )
    quantity_uom = fields.Many2One('product.uom', 'Quantity UOM', states={
            'required': Eval('calculation') == 'standard',
            'invisible': Eval('calculation') != 'standard',
            }, domain=[
            If(Bool(Eval('quantity_uom_category', 0)),
            ('category', '=', Eval('quantity_uom_category')),
            (),
            )], depends=['quantity_uom_category'])
    calculation = fields.Selection([
            ('standard', 'Standard'),
            ('fixed', 'Fixed'),
            ], 'Calculation', required=True, help='Use Standard to multiply '
        'the amount of time by the number of units produced. Use Fixed to use '
        'the indicated time in the production without considering the '
        'quantities produced. The latter is useful for a setup or cleaning '
        'operation, for example.')
    quantity_uom_digits = fields.Function(fields.Integer('Quantity UOM Digits',
            on_change_with=['quantity_uom']),
        'on_change_with_quantity_uom_digits')
    quantity_uom_category = fields.Function(fields.Many2One(
            'product.uom.category', 'Quantity UOM Category'),
        'get_quantity_uom_category')
    cost = fields.Function(fields.Numeric('Cost', digits=(16, 4),
            on_change_with=['time', 'time_uom', 'calculation', 'quantity',
                'quantity_uom', 'cost_price', 'work_center',
                'work_center_category', '_parent_plan.uom']),
        'on_change_with_cost')

    @classmethod
    def __setup__(cls):
        super(PlanOperationLine, cls).__setup__()
        cls._order.insert(0, ('sequence', 'ASC'))

    @staticmethod
    def order_sequence(tables):
        table, _ = tables[None]
        return [table.sequence == None, table.sequence]

    def on_change_with_time_uom(self):
        if self.work_center:
            return self.work_center.uom.id
        if self.work_center_category:
            return self.work_center_category.uom.id

    def on_change_with_time_uom_digits(self, name=None):
        if self.time_uom:
            return self.time_uom.digits
        return 2

    def on_change_with_cost(self, name=None):
        pool = Pool()
        Uom = pool.get('product.uom')
        wc = self.work_center or self.work_center_category
        if not wc or not self.time:
            return _ZERO
        qty = 1
        time = Uom.compute_qty(self.time_uom, self.time, wc.uom, round=False)
        if self.calculation == 'standard':
            if not self.quantity:
                return None
            quantity = Uom.compute_qty(self.quantity_uom, self.quantity,
                self.plan.uom, round=False)
            time *= (qty / quantity)
        cost = Decimal(str(time)) * wc.cost_price
        cost /= qty
        digits = self.__class__.cost.digits[1]
        return cost.quantize(Decimal(str(10 ** -digits)))

    def get_quantity_uom_category(self, name):
        if self.plan and self.plan.uom:
            return self.plan.uom.category.id

    def on_change_with_quantity_uom_digits(self, name=None):
        if self.quantity_uom:
            return self.quantity_uom.digits
        return 2


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
            values = {}
            for field in ('work_center', 'work_center_category', 'time_uom',
                    'quantity_uom', 'quantity_uom_category', 'operation_type',
                    'quantity_uom_digits', 'time', 'quantity', 'calculation'):
                value = getattr(operation, field)
                if value:
                    if isinstance(value, ModelSQL):
                        values[field] = value.id
                    else:
                        values[field] = value
            operations['add'].append(values)
        return changes

    def on_change_route(self):
        return self.update_operations()

    def on_change_with_operation_cost(self, name=None):
        cost = Decimal('0.0')
        for operation in self.operations:
            cost += operation.cost or Decimal('0.0')
        return cost

    def on_change_operations(self):
        self.operation_cost = sum(o.cost for o in self.operations if o.cost)
        return self.update_cost_type('product_cost_plan_operation',
            'operations', self.operation_cost)

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
