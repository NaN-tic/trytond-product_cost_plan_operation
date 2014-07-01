from decimal import Decimal
from trytond.model import ModelSQL, ModelView, fields
from trytond.pool import Pool, PoolMeta
from trytond.pyson import Eval, Bool, Id
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
    name = fields.Char('Name')
    time = fields.Float('Time', required=True,
        digits=(16, Eval('time_uom_digits', 2)), depends=['time_uom_digits'])
    time_uom = fields.Many2One('product.uom', 'Time UOM', required=True,
        domain=[
            ('category', '=', Id('product', 'uom_cat_time')),
            ])
    time_uom_digits = fields.Function(fields.Integer('Time UOM Digits'),
        'on_change_with_time_uom_digits')
    children_quantity = fields.Float('Children Quantity')
    quantity = fields.Float('Quantity',
        states={
            'required': Eval('calculation') == 'standard',
            'invisible': Eval('calculation') != 'standard',
            },
        digits=(16, Eval('quantity_uom_digits', 2)),
        depends=['quantity_uom_digits', 'calculation'],
        help='Quantity of the production product processed by the specified '
        'time.')
    quantity_uom = fields.Many2One('product.uom', 'Quantity UOM',
        states={
            'required': Eval('calculation') == 'standard',
            'invisible': Eval('calculation') != 'standard',
            },
        domain=[
            ('category', '=', Eval('quantity_uom_category')),
            ],
        depends=['quantity_uom_category'])
    calculation = fields.Selection([
            ('standard', 'Standard'),
            ('fixed', 'Fixed'),
            ], 'Calculation', required=True, help='Use Standard to multiply '
        'the amount of time by the number of units produced. Use Fixed to use '
        'the indicated time in the production without considering the '
        'quantities produced. The latter is useful for a setup or cleaning '
        'operation, for example.')
    quantity_uom_digits = fields.Function(fields.Integer(
            'Quantity UOM Digits'),
        'on_change_with_quantity_uom_digits')
    quantity_uom_category = fields.Function(fields.Many2One(
            'product.uom.category', 'Quantity UOM Category'),
        'on_change_with_quantity_uom_category')
    cost = fields.Function(fields.Numeric('Cost', digits=DIGITS),
        'on_change_with_cost')
    total_unit = fields.Function(fields.Numeric('Total Unit Cost',
            digits=DIGITS),
        'on_change_with_total_unit')

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

    @fields.depends('work_center', 'work_center_category')
    def on_change_with_time_uom(self):
        if self.work_center:
            return self.work_center.uom.id
        if self.work_center_category:
            return self.work_center_category.uom.id

    @fields.depends('time_uom')
    def on_change_with_time_uom_digits(self, name=None):
        if self.time_uom:
            return self.time_uom.digits
        return 2

    @fields.depends('work_center', 'work_center_category', 'time')
    def on_change_with_cost_price(self, name=None):
        wc = self.work_center or self.work_center_category
        if not wc or not self.time:
            return _ZERO
        return wc.cost_price

    @fields.depends('time', 'time_uom', 'calculation', 'quantity',
        'quantity_uom', 'cost_price', 'work_center', 'work_center_category',
        '_parent_plan.uom', 'children', 'children_quantity',
        '_parent_plan.production_quantity')
    def on_change_with_cost(self, name=None):
        pool = Pool()
        Uom = pool.get('product.uom')
        wc = self.work_center or self.work_center_category
        production_quantity = (self.plan.production_quantity if self.plan
            else None)
        cost = _ZERO
        if wc and self.time and production_quantity:
            time = Uom.compute_qty(self.time_uom, self.time, wc.uom,
                round=False)
            if self.calculation == 'standard':
                if not self.quantity:
                    return None
                quantity = Uom.compute_qty(self.quantity_uom, self.quantity,
                    self.plan.uom, round=False)
                time *= (production_quantity / quantity)
            cost = Decimal(str(time)) * wc.cost_price
            cost /= Decimal(str(production_quantity))
        for child in self.children:
            cost += Decimal(str(self.children_quantity or 0)) * (child.cost
                or _ZERO)
        digits = self.__class__.cost.digits[1]
        return cost.quantize(Decimal(str(10 ** -digits)))

    @fields.depends('time', 'time_uom', 'calculation', 'quantity',
        'quantity_uom', 'cost_price', 'work_center', 'work_center_category',
        '_parent_plan.uom', 'children', 'children_quantity',
        '_parent_plan.quantity', '_parent_plan.production_quantity')
    def on_change_with_total_unit(self, name=None):
        total = self.on_change_with_cost(None)
        if total and self.plan and self.plan.quantity:
            total /= Decimal(str(self.plan.quantity))
        else:
            total = Decimal('0.0')
        digits = self.__class__.total_unit.digits[1]
        return total.quantize(Decimal(str(10 ** -digits)))

    @fields.depends('quantity_uom', 'plan')
    def on_change_with_quantity_uom(self):
        if self.quantity_uom:
            return self.quantity_uom.id
        if self.plan and self.plan.uom:
            return self.plan.uom.id

    @fields.depends('plan')
    def on_change_with_quantity_uom_category(self, name=None):
        if self.plan and self.plan.uom:
            return self.plan.uom.category.id

    @fields.depends('quantity_uom')
    def on_change_with_quantity_uom_digits(self, name=None):
        if self.quantity_uom:
            return self.quantity_uom.digits
        return 2


class Plan:
    __name__ = 'product.cost.plan'

    route = fields.Many2One('production.route', 'Route', domain=[
            ('uom', '=', Eval('uom'))
            ], depends=['uom'])
    operations = fields.One2Many('product.cost.plan.operation_line', 'plan',
        'Operation Lines')
    operations_tree = fields.Function(fields.One2Many(
            'product.cost.plan.operation_line', 'plan', 'Operation Lines',
            domain=[
                ('parent', '=', None),
                ],
            states={
                'readonly': ~Bool(Eval('costs', [0])),
                },
            depends=['costs']),
        'get_operations_tree', setter='set_operations_tree')
    operation_cost = fields.Function(fields.Numeric('Operation Cost',
            digits=DIGITS),
        'on_change_with_operation_cost')
    production_quantity = fields.Float('Production Quantity', required=True)

    @classmethod
    def __setup__(cls):
        super(Plan, cls).__setup__()
        cls._error_messages.update({
                'route_already_exists': ('A route already exists for cost plan'
                    ' "%s".'),
                'product_already_has_route': ('Product "%s" already has a '
                    'route assigned.'),
                })

    @classmethod
    @ModelView.button
    def compute(cls, plans):
        to_create = []
        to_delete = []
        for plan in plans:
            if not plan.route:
                continue
            OperationLine = Pool().get('product.cost.plan.operation_line')
            to_delete.extend(plan.operations)
            for operation in plan.route.operations:
                line = OperationLine()
                for field in ('work_center', 'work_center_category',
                        'time_uom', 'quantity_uom', 'quantity_uom_category',
                        'operation_type', 'quantity_uom_digits', 'time',
                        'quantity', 'calculation'):
                    setattr(line, field, getattr(operation, field))
                line.plan = plan
                to_create.append(line._save_values)
        if to_delete:
            OperationLine.delete(to_delete)
        if to_create:
            OperationLine.create(to_create)
        # Super must be executed at the end because it updates the costs
        super(Plan, cls).compute(plans)

    def get_operations_tree(self, name):
        return [x.id for x in self.operations if not x.parent]

    @classmethod
    def set_operations_tree(cls, lines, name, value):
        cls.write(lines, {
                'operations': value,
                })

    @fields.depends('quantity')
    def on_change_with_production_quantity(self):
        return self.quantity

    @fields.depends('quantity', 'operations_tree')
    def on_change_with_operation_cost(self, name=None):
        if not self.quantity:
            return Decimal('0.0')
        cost = Decimal('0.0')
        for operation in self.operations_tree:
            cost += operation.cost or Decimal('0.0')
        cost = cost / Decimal(str(self.quantity))
        digits = self.__class__.operation_cost.digits[1]
        return cost.quantize(Decimal(str(10 ** -digits)))

    @fields.depends('operations', 'quantity')
    def on_change_operations(self):
        self.operation_cost = sum(o.cost for o in self.operations if o.cost)
        return self.update_cost_type('product_cost_plan_operation',
            'operations', self.operation_cost)

    @fields.depends('operations_tree', 'operations_tree', 'quantity')
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

    def create_route(self, name):
        pool = Pool()
        Route = pool.get('production.route')
        ProductBOM = pool.get('product.product-production.bom')
        if self.route:
            self.raise_user_error('route_already_exists', self.rec_name)

        route = Route()
        route.name = name
        route.uom = self.uom
        route.operations = self._get_route_operations()
        route.save()
        self.route = route
        self.save()

        ProductBOM()
        if self.product.boms:
            product_bom = self.product.boms[0]
            if product_bom.route:
                self.raise_user_error('product_already_has_route',
                    self.product.rec_name)
        else:
            product_bom = ProductBOM()
        product_bom.product = self.product
        product_bom.route = route
        product_bom.save()
        return route

    def _get_route_operations(self):
        operations = []
        for line in self.operations:
            operations.append(self._get_operation_line(line))
        return operations

    def _get_operation_line(self, line):
        'Returns the operation to create from a cost plan operation line'
        Operation = Pool().get('production.route.operation')
        operation = Operation()
        operation.operation_type = line.operation_type
        operation.work_center = line.work_center
        operation.work_center_category = line.work_center_category
        operation.time = line.time
        operation.time_uom = line.time_uom
        operation.calculation = line.calculation
        operation.quantity = line.quantity
        operation.quantity_uom = line.quantity_uom
        return operation


class CreateRouteStart(ModelView):
    'Create Route Start'
    __name__ = 'product.cost.plan.create_route.start'

    name = fields.Char('Name', required=True)


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
        CostPlan = Pool().get('product.cost.plan')
        plan = CostPlan(Transaction().context.get('active_id'))
        return {
            'name': plan.product.rec_name,
            }

    def do_route(self, action):
        CostPlan = Pool().get('product.cost.plan')
        plan = CostPlan(Transaction().context.get('active_id'))
        route = plan.create_route(self.start.name)
        data = {
            'res_id': [route.id],
            }
        action['views'].reverse()
        return action, data
