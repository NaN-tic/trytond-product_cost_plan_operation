# The COPYRIGHT file at the top level of this repository contains the full
# copyright notices and license terms.
from trytond.pool import Pool
from . import plan


def register():
    Pool.register(
        plan.PlanOperationLine,
        plan.Plan,
        plan.CreateRouteStart,
        module='product_cost_plan_operation', type_='model')
    Pool.register(
        plan.CreateRoute,
        module='product_cost_plan_operation', type_='wizard')
