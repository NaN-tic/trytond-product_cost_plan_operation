# The COPYRIGHT file at the top level of this repository contains the full
# copyright notices and license terms.
from decimal import Decimal
import math

from trytond.config import config
from trytond.model import ModelSQL, ModelView, fields
from trytond.pool import Pool, PoolMeta
from trytond.pyson import Eval, Id, If
from trytond.transaction import Transaction
from trytond.wizard import Wizard, StateView, StateAction, Button
from trytond.exceptions import UserWarning, UserError
from trytond.i18n import gettext

__all__ = ['PlanOperationLine', 'RoutingStep', 'Plan',
    'CreateRouteStart', 'CreateRoute']


DIGITS = (16, config.getint('product', 'price_decimal', default=4))
_ZERO = Decimal(0)


class PlanOperationLine(ModelSQL, ModelView):
    'Product Cost Plan Operation Line'
    __name__ = 'product.cost.plan.operation_line'

    plan = fields.Many2One('product.cost.plan', 'Plan', required=True,
        ondelete='CASCADE')
    sequence = fields.Integer('Sequence')
    name = fields.Char('Name')
    operation_type = fields.Many2One('production.operation.type',
        'Operation Type')
    work_center_category = fields.Many2One('production.work_center.category',
        'Work Center Category')
    calculation = fields.Selection([
            ('standard', 'Standard'),
            ('fixed', 'Fixed'),
            ], 'Calculation', required=True,
        help='Use Standard to multiply the amount of time by the number of '
        'units produced. Use Fixed to use the indicated time in the '
        'production without considering the quantities produced. The latter '
        'is useful for a setup or cleaning operation, for example.')
    time_uom = fields.Many2One('product.uom', 'Time UOM', required=True,
        domain=[
            ('category', '=', Id('product', 'uom_cat_time')),
            ])
    time_uom_digits = fields.Function(fields.Integer('Time UOM Digits'),
        'on_change_with_time_uom_digits')
    time = fields.Float('Time', required=True,
        digits=(16, Eval('time_uom_digits', 2)))
    quantity_uom = fields.Many2One('product.uom', 'Quantity UOM', domain=[
            ('category', '=',
                Eval('_parent_plan', {}).get('product_uom_category', -1)),
            ],
        states={
            'required': Eval('calculation') == 'standard',
            'invisible': Eval('calculation') != 'standard',
            })
    quantity_uom_digits = fields.Function(fields.Integer(
            'Quantity UOM Digits'),
        'on_change_with_quantity_uom_digits')
    quantity = fields.Float('Quantity',
        digits=(16, Eval('quantity_uom_digits', 2)),
        states={
            'required': Eval('calculation') == 'standard',
            'invisible': Eval('calculation') != 'standard',
            },
        depends=['quantity_uom_digits', 'calculation'],
        help='Quantity of the production product processed by the specified '
        'time.')
    unit_cost = fields.Function(fields.Numeric('Unit Cost',
            digits=DIGITS,
            help="The cost of this operation for each unit of plan's "
            "product."),
        'get_unit_cost')
    total_cost = fields.Function(fields.Numeric('Total Cost',
            digits=DIGITS,
            help="The cost of this operation for total plan's quantity."),
        'get_total_cost')

    @classmethod
    def __setup__(cls):
        super(PlanOperationLine, cls).__setup__()
        cls._order.insert(0, ('sequence', 'ASC'))

    @staticmethod
    def order_sequence(tables):
        table, _ = tables[None]
        return [table.sequence == None, table.sequence]

    @staticmethod
    def default_calculation():
        return 'standard'

    @staticmethod
    def default_time_uom():
        pool = Pool()
        ModelData = pool.get('ir.model.data')
        return ModelData.get_id('product', 'uom_hour')

    @fields.depends('work_center_category')
    def on_change_with_time_uom(self):
        if self.work_center_category:
            return self.work_center_category.uom.id

    @fields.depends('time_uom')
    def on_change_with_time_uom_digits(self, name=None):
        if self.time_uom:
            return self.time_uom.digits
        return 2

    @staticmethod
    def default_quantity_uom():
        context = Transaction().context
        return context.get('plan_uom', None)

    @fields.depends('plan', '_parent_plan.uom')
    def on_change_with_quantity_uom(self):
        if self.plan and self.plan.uom:
            return self.plan.uom.category.id

    @fields.depends('quantity_uom')
    def on_change_with_quantity_uom_digits(self, name=None):
        if self.quantity_uom:
            return self.quantity_uom.digits
        return 2

    def get_unit_cost(self, name=None):
        unit_cost = self.total_cost
        if unit_cost and self.plan and self.plan.quantity:
            unit_cost /= Decimal(str(self.plan.quantity))
        digits = self.__class__.unit_cost.digits[1]
        return unit_cost.quantize(Decimal(str(10 ** -digits)))

    def get_total_cost(self, name=None, round=True):
        pool = Pool()
        Uom = pool.get('product.uom')

        total_cost = _ZERO
        if not self.work_center_category or not self.time:
            return total_cost

        if not self.plan or not self.plan.quantity:
            return Decimal('0')
        if self.calculation == 'standard' and not self.quantity:
            return Decimal('0')
        elif (self.calculation == 'fixed' and
                not self.plan.production_quantity):
            return Decimal('0')

        time = Uom.compute_qty(self.time_uom, self.time,
            self.work_center_category.uom, round=False)
        if self.calculation == 'standard':
            quantity = (self.plan.quantity /
                Uom.compute_qty(self.quantity_uom, self.quantity,
                    self.plan.uom, round=False))
        else:
            quantity = math.ceil(self.plan.quantity
                / self.plan.production_quantity)

        total_cost = (Decimal(str(quantity)) * Decimal(str(time))
            * self.work_center_category.cost_price)

        if not round:
            return total_cost
        digits = self.__class__.total_cost.digits[1]
        return total_cost.quantize(Decimal(str(10 ** -digits)))


class RoutingStep(metaclass=PoolMeta):
    __name__ = 'production.routing.step'

    operation_type = fields.Many2One('production.operation.type',
        'Operation Type')
    work_center_category = fields.Many2One('production.work_center.category',
        'Work Center Category')
    calculation = fields.Selection([
            ('standard', 'Standard'),
            ('fixed', 'Fixed'),
            ], 'Calculation',
        help='Use Standard to multiply the amount of time by the number of '
        'units produced. Use Fixed to use the indicated time in the '
        'production without considering the quantities produced. The latter '
        'is useful for a setup or cleaning operation, for example.')
    time_uom = fields.Many2One('product.uom', 'Time UOM',
        domain=[
            ('category', '=', Id('product', 'uom_cat_time')),
            ])
    time_uom_digits = fields.Function(fields.Integer('Time UOM Digits'),
        'on_change_with_time_uom_digits')
    time = fields.Float('Time',
        digits=(16, Eval('time_uom_digits', 2)))
    quantity_uom = fields.Many2One('product.uom', 'Quantity UOM', domain=[],
        states={
            'invisible': Eval('calculation') != 'standard',
            })
    quantity_uom_digits = fields.Function(fields.Integer(
            'Quantity UOM Digits'),
        'on_change_with_quantity_uom_digits')
    quantity = fields.Float('Quantity',
        digits=(16, Eval('quantity_uom_digits', 2)),
        states={
            'invisible': Eval('calculation') != 'standard',
            },
        depends=['quantity_uom_digits', 'calculation'],
        help='Quantity of the production product processed by the specified '
        'time.')

    @staticmethod
    def default_calculation():
        return 'standard'

    @staticmethod
    def default_time_uom():
        pool = Pool()
        ModelData = pool.get('ir.model.data')
        return ModelData.get_id('product', 'uom_hour')

    @fields.depends('work_center_category')
    def on_change_with_time_uom(self):
        if self.work_center_category:
            return self.work_center_category.uom.id

    @fields.depends('time_uom')
    def on_change_with_time_uom_digits(self, name=None):
        if self.time_uom:
            return self.time_uom.digits
        return 2

    @fields.depends('quantity_uom')
    def on_change_with_quantity_uom_digits(self, name=None):
        if self.quantity_uom:
            return self.quantity_uom.digits
        return 2


class Plan(metaclass=PoolMeta):
    __name__ = 'product.cost.plan'

    route = fields.Many2One('production.routing', 'Routing', domain=[
            If(Eval('bom'),
                ('boms', '=', Eval('bom', 0)),
                ()),
            ])
    operations = fields.One2Many('product.cost.plan.operation_line', 'plan',
        'Operation Lines', context={
            'plan_uom': Eval('uom'),
            })
    production_quantity = fields.Float('Production Quantity',
        digits=(16, Eval('uom_digits', 2)), required=True,
        depends=['uom_digits'])
    operations_cost = fields.Function(fields.Numeric('Unit Operation Costs',
            digits=DIGITS),
        'get_operations_cost')

    @classmethod
    def __setup__(cls):
        super(Plan, cls).__setup__()
        cls.uom.states['readonly'] = (cls.uom.states['readonly']
            | Eval('operations', [0]))

    @fields.depends('quantity')
    def on_change_with_production_quantity(self):
        return self.quantity

    def get_operations_cost(self, name):
        if not self.quantity:
            return Decimal(0)
        cost = sum(o.get_total_cost(None, round=False)
            for o in self.operations)
        cost /= Decimal(str(self.quantity))
        digits = self.__class__.operations_cost.digits[1]
        return cost.quantize(Decimal(str(10 ** -digits)))

    @classmethod
    def clean(cls, plans):
        pool = Pool()
        OperationLine = pool.get('product.cost.plan.operation_line')

        super(Plan, cls).clean(plans)

        operation_lines = OperationLine.search([
                ('plan', 'in', [p.id for p in plans]),
                ])
        if operation_lines:
            OperationLine.delete(operation_lines)

    @classmethod
    def compute(cls, plans):
        OperationLine = Pool().get('product.cost.plan.operation_line')

        super(Plan, cls).compute(plans)

        to_create = []
        for plan in plans:
            if not plan.route:
                continue
            for step in plan.route.steps:
                line = OperationLine()
                line.sequence = step.sequence
                line.operation_type = step.operation_type
                line.work_center_category = step.work_center_category
                line.calculation = (step.calculation
                    or OperationLine.default_calculation())
                line.time_uom = (step.time_uom
                    or OperationLine.default_time_uom())
                line.time = step.time or 0
                line.quantity_uom = step.quantity_uom
                line.quantity_uom_digits = step.quantity_uom_digits
                line.quantity = step.quantity
                line.plan = plan
                to_create.append(line._save_values())
        if to_create:
            OperationLine.create(to_create)

    def create_route(self, name):
        pool = Pool()
        Route = pool.get('production.routing')
        ProductBOM = pool.get('product.product-production.bom')
        RoutingOperation = pool.get('production.routing.operation')
        RoutingStep = pool.get('production.routing.step')
        Warning = pool.get('res.user.warning')
        key = 'route_already_exists%s'%self.id
        if not self.product:
            raise UserError(gettext('product_cost_plan_margin.lacks_the_product',
                cost_plan=self.rec_name))
        if self.route and Warning.check(key):
            raise UserWarning(key,
                gettext('product_cost_plan_margin.route_already_exists',
                    product=self.rec_name))

        route = Route()
        route.name = name
        if self.bom:
            route.boms = [self.bom]
        route.steps = self._get_route_steps(
            RoutingOperation, RoutingStep)
        route.save()
        self.route = route
        self.save()

        if self.product.boms:
            product_bom = self.product.boms[0]
        else:
            product_bom = ProductBOM()
        product_bom.product = self.product
        product_bom.routing = route
        product_bom.save()
        return route

    def _get_route_steps(self, RoutingOperation, RoutingStep):
        steps = []
        for line in self.operations:
            steps.append(self._get_route_step(
                    line, RoutingOperation, RoutingStep))
        return steps

    def _get_route_step(self, line, RoutingOperation, RoutingStep):
        'Returns the routing step to create from a cost plan operation line'
        operation_name = None
        if line.operation_type:
            operation_name = line.operation_type.rec_name
        if not operation_name:
            operation_name = line.name or self.rec_name
        operations = RoutingOperation.search([
                ('name', '=', operation_name),
                ], limit=1)
        if operations:
            operation, = operations
        else:
            operation = RoutingOperation(name=operation_name)
            operation.save()
        step = RoutingStep()
        step.sequence = line.sequence
        step.operation = operation
        step.operation_type = line.operation_type
        step.work_center_category = line.work_center_category
        step.time = line.time
        step.time_uom = line.time_uom
        step.calculation = line.calculation
        step.quantity = line.quantity
        step.quantity_uom = line.quantity_uom
        return step

    @classmethod
    def copy(cls, plans, default=None):
        if default is None:
            default = {}
        else:
            default = default.copy()
        default['route'] = None
        return super(Plan, cls).copy(plans, default=default)

    def _copy_plan(self, default):
        OperationLine = Pool().get('product.cost.plan.operation_line')

        default['operations'] = None
        new_plan = super(Plan, self)._copy_plan(default=default)
        OperationLine.copy(self.operations, default={
                'plan': new_plan.id,
                })
        return new_plan


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
    route = StateAction('production_routing.act_routing_list')

    def default_start(self, fields):
        CostPlan = Pool().get('product.cost.plan')
        plan = CostPlan(Transaction().context.get('active_id'))
        return {
            'name': plan.rec_name,
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
