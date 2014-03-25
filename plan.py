from decimal import Decimal
from trytond.model import ModelSQL, ModelView, fields
from trytond.pool import Pool, PoolMeta
from trytond.pyson import Eval, Id, If, Bool
from trytond.transaction import Transaction
from trytond.wizard import Wizard, StateView, StateAction, Button

__all__ = ['PlanOperationLine', 'Plan', 'CreateRouteStart', 'CreateRoute']
__metaclass__ = PoolMeta

_ZERO = Decimal('0.0')
DIGITS = (16, 5)


class PlanOperationLine(ModelSQL, ModelView):
    'Product Cost Plan Operation Line'
    __name__ = 'product.cost.plan.operation_line'

    plan = fields.Many2One('product.cost.plan', 'Plan', required=True,
        ondelete='CASCADE')
    sequence = fields.Integer('Sequence')
    parent = fields.Many2One('product.cost.plan.operation_line', 'Parent')
    children = fields.One2Many('product.cost.plan.operation_line', 'parent',
        'Children')
    work_center = fields.Many2One('production.work_center', 'Work Center')
    work_center_category = fields.Many2One('production.work_center.category',
        'Work Center Category')
    operation_type = fields.Many2One('production.operation.type',
        'Operation Type')
    time = fields.Float('Time', required=True,
        digits=(16, Eval('time_uom_digits', 2)), depends=['time_uom_digits'])
    time_uom = fields.Many2One('product.uom', 'Time UOM', required=True,
        domain=[
            ('category', '=', Id('product', 'uom_cat_time')),
            ], on_change_with=['work_center', 'work_center_category'])
    time_uom_digits = fields.Function(fields.Integer('Time UOM Digits',
            on_change_with=['uom']), 'on_change_with_time_uom_digits')
    children_quantity = fields.Float('Children Quantity')
    quantity = fields.Float('Quantity', states={
            'required': Eval('calculation') == 'standard',
            'invisible': Eval('calculation') != 'standard',
            },
        digits=(16, Eval('quantity_uom_digits', 2)),
        depends=['quantity_uom_digits', 'calculation'],
        help='Quantity of the production product processed by the specified '
        'time.')
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
    cost = fields.Function(fields.Numeric('Cost', digits=DIGITS,
            on_change_with=['time', 'time_uom', 'calculation', 'quantity',
                'quantity_uom', 'cost_price', 'work_center',
                'work_center_category', '_parent_plan.uom', 'children',
                'children_quantity']),
        'on_change_with_cost')

    @classmethod
    def __setup__(cls):
        super(PlanOperationLine, cls).__setup__()
        cls._order.insert(0, ('sequence', 'ASC'))

    @staticmethod
    def default_calculation():
        return 'standard'

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
        for child in self.children:
            cost += Decimal(str(self.children_quantity or 0)) * child.cost
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
    operations_tree = fields.Function(fields.One2Many(
            'product.cost.plan.operation_line', 'plan', 'Operation Lines',
            on_change=['costs', 'operations_tree', 'quantity']),
        'get_operations_tree', setter='set_operations_tree')
    operation_cost = fields.Function(fields.Numeric('Operation Cost',
            on_change_with=['operations_tree', 'quantity'], digits=DIGITS),
        'on_change_with_operation_cost')

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

    def get_operations_tree(self, name):
        return [x.id for x in self.operations if not x.parent]

    @classmethod
    def set_operations_tree(cls, lines, name, value):
        cls.write(lines, {
                'operations': value,
                })

    def on_change_route(self):
        return self.update_operations()

    def on_change_with_operation_cost(self, name=None):
        if not self.quantity:
            return Decimal('0.0')
        cost = Decimal('0.0')
        for operation in self.operations_tree:
            cost += operation.cost or Decimal('0.0')
        cost = cost / Decimal(str(self.quantity))
        digits = self.__class__.operation_cost.digits[1]
        return cost.quantize(Decimal(str(10 ** -digits)))

    def on_change_operations(self):
        self.operation_cost = sum(o.cost for o in self.operations if o.cost)
        return self.update_cost_type('product_cost_plan_operation',
            'operations', self.operation_cost)

    def on_change_operations_tree(self):
        self.operation_cost = self.on_change_with_operation_cost()
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


class CreateRouteStart(ModelView):
    'Create Route Start'
    __name__ = 'product.cost.plan.create_route.start'

    name = fields.Char('Name', required=True)
    uom = fields.Many2One('product.uom', 'UOM', required=True)
    operations = fields.One2Many('production.route.operation', 'route',
        'Operations')


class CreateRoute(Wizard):
    'Create Route'
    __name__ = 'product.cost.plan.create_route'

    start = StateView('product.cost.plan.create_route.start',
        'product_cost_plan_operation.create_route_start_view_form', [
            Button('Cancel', 'end', 'tryton-cancel'),
            Button('Ok', 'route', 'tryton-ok', True),
            ])
    route = StateAction('production_route.act_production_route')

    def default_start(self, fields):
        pool = Pool()
        CostPlan = pool.get('product.cost.plan')

        operations = []
        plan = CostPlan(Transaction().context.get('active_id'))
        for line in plan.operations:
            operations.append(self._get_operation_line(line))

        return {'operations': operations, 'uom': plan.uom.id}

    def do_route(self, action):
        route = Pool().get('production.route')

        route = route()
        route.name = self.start.name
        route.uom = self.start.uom
        route.operations = self.start.operations
        route.save()
        data = {'res_id': [route.id]}
        action['views'].reverse()
        return action, data

    def _get_operation_line(self, line):
        'Returns the operation to create from a cost plan operation line'
        return {
            'operation_type': (line.operation_type.id if line.operation_type
                else None),
            'work_center': (line.work_center.id if line.work_center
                else None),
            'work_center_category': (line.work_center_category.id
                if line.work_center_category else None),
            'time': line.time,
            'time_uom': line.time_uom.id,
            'calculation': line.calculation,
            'quantity': line.quantity,
            'quantity_uom': (line.quantity_uom.id if line.quantity_uom
                else None),
            }
